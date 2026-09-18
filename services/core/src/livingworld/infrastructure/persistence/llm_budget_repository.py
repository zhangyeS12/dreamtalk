"""SQLite-backed all-budget admission and accounting share one write transaction."""

from decimal import Decimal, localcontext

from sqlalchemy import and_, select

from livingworld.application.llm import (
    InvocationId,
    LLMContractError,
    LLMPurpose,
    ModelRef,
    ProviderId,
)
from livingworld.application.llm_accounting import AttemptFacts
from livingworld.application.llm_budget import (
    BoundGuarantee,
    BudgetAdmissionError,
    BudgetDiagnostic,
    BudgetId,
    BudgetIntegrityError,
    BudgetMode,
    BudgetPolicy,
    BudgetReason,
    BudgetReservation,
    BudgetView,
    ReservationStatus,
)
from livingworld.application.llm_preflight import MoneyUpperBound, PreflightPricingEngine
from livingworld.application.llm_pricing import CostStatus, InMemoryPricingCatalog, Money
from livingworld.domain.errors import ConcurrencyConflictError
from livingworld.domain.values import Revision
from livingworld.infrastructure.persistence.llm_models import (
    LLMAttemptRow,
    LLMBudgetReservationRow,
    LLMBudgetRow,
)
from livingworld.infrastructure.persistence.llm_repository import (
    SqlAlchemyUsageLedger,
    _decode,
    _encode,
    _start,
)

HELD = {
    ReservationStatus.HELD,
    ReservationStatus.HELD_UNCERTAIN,
    ReservationStatus.BOUND_VIOLATION,
    ReservationStatus.INTEGRITY_DEGRADED,
}
DEGRADED = {ReservationStatus.BOUND_VIOLATION, ReservationStatus.INTEGRITY_DEGRADED}


def _policy(row):
    provider = ProviderId(row.provider_id) if row.provider_id else None
    return BudgetPolicy(
        budget_id=BudgetId(row.budget_id),
        enabled=row.enabled,
        mode=BudgetMode(row.mode),
        limit=Money(row.currency, row.limit_amount),
        start_utc=row.start_utc,
        end_utc=row.end_utc,
        purpose=LLMPurpose(row.purpose) if row.purpose else None,
        provider=provider,
        model=ModelRef(provider, row.model_id) if row.model_id else None,
        revision=Revision(row.revision),
        created_at_utc=row.created_at_utc,
        updated_at_utc=row.updated_at_utc,
    )


def _scope(policy):
    predicates = [
        LLMAttemptRow.started_at_utc >= policy.start_utc,
        LLMAttemptRow.started_at_utc < policy.end_utc,
    ]
    if policy.purpose is not None:
        predicates.append(LLMAttemptRow.purpose == policy.purpose.value)
    provider = policy.provider or (policy.model.provider_id if policy.model else None)
    if provider is not None:
        predicates.append(LLMAttemptRow.provider_id == provider.value)
    if policy.model is not None:
        # Permanently distinct from accounting's requested OR reported analytics.
        predicates.append(LLMAttemptRow.requested_model == policy.model.model_id)
    return predicates


def _scopes_overlap(left, right):
    # A new policy ID/window is not evidence that a broken bound became trustworthy.
    return all(
        a is None or b is None or a == b
        for a, b in (
            (left.purpose, right.purpose),
            (left.provider, right.provider),
            (left.model, right.model),
        )
    )


def _trusted_reservation(row, start):
    evidence, accepted = _decode(row.bound_evidence), _decode(row.policy_snapshot)
    return (
        isinstance(evidence, MoneyUpperBound)
        and evidence.usage.guarantee is BoundGuarantee.HARD_UPPER_BOUND
        and evidence.requested == start.requested_model
        and evidence.at_utc == start.started_at_utc
        and evidence.money == Money(row.currency, row.reserved_amount)
        and isinstance(accepted, BudgetPolicy)
        and accepted.mode is BudgetMode.HARD
        and accepted.budget_id.value == row.budget_id
        and accepted.matches(start)
        and accepted.limit.currency == row.currency
    )


class SqlAlchemyBudgetGuard(SqlAlchemyUsageLedger):
    """Opt-in accounting capability with atomic policy enforcement; no provider IO."""

    def __init__(self, sessions, *, bounder, diagnostics, catalog=None, envelopes=()):
        if not callable(diagnostics):
            raise LLMContractError("budget_requires_diagnostics")
        catalog = catalog if catalog is not None else InMemoryPricingCatalog()
        super().__init__(sessions, catalog=catalog)
        self._bounder, self._diagnostics = bounder, diagnostics
        self._preflight = PreflightPricingEngine(catalog, envelopes=envelopes)

    def _report(self, start, event, budget_id=None):
        try:
            self._diagnostics(
                BudgetDiagnostic(start.invocation_id, start.attempt_ordinal, event, budget_id)
            )
        except Exception:
            pass  # Diagnostics are non-raising and cannot replace a provider outcome.

    async def start(self, record):
        raise LLMContractError("budget_accounting_requires_admission")

    async def admit(self, start, request):
        if (
            start.invocation_id != request.invocation_id
            or start.requested_model != request.model
            or start.purpose != request.purpose
        ):
            raise LLMContractError("conflicting_budget_attempt")
        denial = None
        warnings = []
        async with self._sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            # Re-delivery is observer idempotency, not permission to replay generation.
            existing = await session.get(
                LLMAttemptRow, (start.invocation_id.value, start.attempt_ordinal)
            )
            if existing is not None:
                raise LLMContractError("budget_attempt_already_started")
            policies = tuple(
                _policy(row)
                for row in (
                    await session.scalars(
                        select(LLMBudgetRow).where(LLMBudgetRow.enabled.is_(True))
                    )
                ).all()
            )
            policies = tuple(
                p for p in policies if p.mode is not BudgetMode.OFF and p.matches(start)
            )
            bound = None
            if policies:
                try:
                    usage = self._bounder.bound(request)
                    bound = self._preflight.bound(
                        requested=request.model, usage=usage, at=start.started_at_utc
                    )
                except Exception:
                    pass  # Configuration exceptions are not safe public diagnostics.
            for policy in policies:
                view = await self._view_in_session(session, policy)
                with localcontext() as context:
                    context.prec = 100
                    reason = (
                        BudgetReason.INTEGRITY_DEGRADED
                        if view.integrity_degraded
                        else BudgetReason.STATE_UNCERTAIN
                        if view.has_unbounded_exposure
                        else BudgetReason.CURRENCY_UNSUPPORTED
                        if view.currency_unsupported
                        else BudgetReason.UNVERIFIABLE
                        if bound is None
                        or (bound.usage.guarantee is not BoundGuarantee.HARD_UPPER_BOUND)
                        else BudgetReason.CURRENCY_UNSUPPORTED
                        if bound.money.currency != policy.limit.currency
                        else BudgetReason.EXCEEDED
                        if view.known_estimated_spend.amount + view.held.amount + bound.money.amount
                        > policy.limit.amount
                        else None
                    )
                if reason is not None:
                    if policy.mode is BudgetMode.HARD:
                        denial = BudgetAdmissionError(reason, policy.budget_id)
                        break
                    warnings.append((reason.value, policy.budget_id))
            if denial is None:
                await self._start_in_session(session, start)
                await session.flush()  # Parent START precedes reservation FK inserts.
                for policy in policies:
                    if policy.mode is BudgetMode.HARD:
                        session.add(
                            LLMBudgetReservationRow(
                                budget_id=policy.budget_id.value,
                                invocation_id=start.invocation_id.value,
                                attempt_ordinal=start.attempt_ordinal,
                                currency=bound.money.currency,
                                reserved_amount=bound.money.amount,
                                status=ReservationStatus.HELD.value,
                                created_at_utc=start.started_at_utc,
                                updated_at_utc=start.started_at_utc,
                                policy_snapshot=_encode(policy),
                                bound_evidence=_encode(bound),
                            )
                        )
                await session.flush()
        if denial is not None:
            self._report(start, denial.reason.value, denial.budget_id)
            raise denial
        for event, budget_id in warnings:
            self._report(start, event, budget_id)

    async def put_policy(self, policy, expected_revision):
        if not isinstance(policy, BudgetPolicy):
            raise LLMContractError("invalid_budget_policy")
        async with self._sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            row = await session.get(LLMBudgetRow, policy.budget_id.value)
            if expected_revision is None:
                if row is not None or policy.revision != Revision():
                    raise ConcurrencyConflictError("Budget expected existence/revision mismatch")
                row = LLMBudgetRow(budget_id=policy.budget_id.value)
                session.add(row)
            elif (
                not isinstance(expected_revision, Revision)
                or row is None
                or row.revision != expected_revision.value
                or policy.revision != expected_revision.advance(expected_revision)
            ):
                raise ConcurrencyConflictError("Budget expected existence/revision mismatch")
            elif (
                policy.created_at_utc != row.created_at_utc
                or policy.updated_at_utc < row.updated_at_utc
            ):
                raise LLMContractError("conflicting_budget_audit_time")
            row.enabled, row.mode = policy.enabled, policy.mode.value
            row.currency, row.limit_amount = policy.limit.currency, policy.limit.amount
            row.start_utc, row.end_utc = policy.start_utc, policy.end_utc
            row.purpose = policy.purpose.value if policy.purpose else None
            provider = policy.provider or (policy.model.provider_id if policy.model else None)
            row.provider_id = provider.value if provider else None
            row.model_id = policy.model.model_id if policy.model else None
            row.revision = policy.revision.value
            row.created_at_utc, row.updated_at_utc = policy.created_at_utc, policy.updated_at_utc

    async def view(self, budget_id):
        async with self._sessions() as session:
            row = await session.get(LLMBudgetRow, budget_id.value)
            if row is None:
                raise LLMContractError("budget_missing")
            return await self._view_in_session(session, _policy(row))

    async def _view_in_session(self, session, policy):
        rows = (await session.scalars(select(LLMAttemptRow).where(*_scope(policy)))).all()
        reservations = (
            await session.scalars(
                select(LLMBudgetReservationRow)
                .join(
                    LLMAttemptRow,
                    and_(
                        LLMBudgetReservationRow.invocation_id == LLMAttemptRow.invocation_id,
                        LLMBudgetReservationRow.attempt_ordinal == LLMAttemptRow.attempt_ordinal,
                    ),
                )
                .where(*_scope(policy))
            )
        ).all()
        by_attempt = {}
        for reservation in reservations:
            by_attempt.setdefault(
                (reservation.invocation_id, reservation.attempt_ordinal), []
            ).append(reservation)
        violations = (
            await session.scalars(
                select(LLMBudgetReservationRow).where(
                    LLMBudgetReservationRow.status.in_([s.value for s in DEGRADED])
                )
            )
        ).all()
        degraded = any(
            r.budget_id == policy.budget_id.value
            or _scopes_overlap(_decode(r.policy_snapshot), policy)
            for r in violations
        )
        known = held = Decimal("0")
        unknown = currency = False
        with localcontext() as context:
            context.prec = 100
            for row in rows:
                priced = row.cost_status == CostStatus.PRICED.value
                unexposed = row.cost_status == CostStatus.NOT_DISPATCHED.value
                if priced:
                    if row.currency == policy.limit.currency:
                        known += row.estimated_cost
                    else:
                        currency = True
                attempts = by_attempt.get((row.invocation_id, row.attempt_ordinal), [])
                holds = []
                for r in attempts:
                    status = ReservationStatus(r.status)
                    degraded |= status in DEGRADED
                    trustworthy = _trusted_reservation(r, _start(row))
                    degraded |= not trustworthy
                    if priced and (
                        r.currency != row.currency or row.estimated_cost > r.reserved_amount
                    ):
                        degraded = True
                    if status is ReservationStatus.SETTLED and (
                        not priced or r.settled_amount != row.estimated_cost
                    ):
                        degraded = True
                    if status is ReservationStatus.RELEASED and not unexposed:
                        degraded = True
                    if status in HELD:
                        if trustworthy and r.currency == policy.limit.currency:
                            holds.append(r.reserved_amount)
                        elif r.currency != policy.limit.currency:
                            currency = True
                        # Known terminal cost but a stale held row proves incomplete reconciliation.
                        if priced or unexposed:
                            degraded = True
                # One physical exposure, even when several hard policies reserved it.
                if holds:
                    held += max(holds)
                elif not priced and not unexposed:
                    unknown = True
            available = max(Decimal("0"), policy.limit.amount - known - held)
        remaining = (
            None if unknown or currency or degraded else Money(policy.limit.currency, available)
        )
        return BudgetView(
            policy,
            Money(policy.limit.currency, known),
            Money(policy.limit.currency, held),
            remaining,
            unknown,
            currency,
            degraded,
        )

    async def reservations(self, budget_id):
        async with self._sessions() as session:
            rows = (
                await session.scalars(
                    select(LLMBudgetReservationRow)
                    .where(LLMBudgetReservationRow.budget_id == budget_id.value)
                    .order_by(
                        LLMBudgetReservationRow.created_at_utc,
                        LLMBudgetReservationRow.invocation_id,
                        LLMBudgetReservationRow.attempt_ordinal,
                    )
                )
            ).all()
            return tuple(
                BudgetReservation(
                    _decode(r.policy_snapshot),
                    InvocationId(r.invocation_id),
                    r.attempt_ordinal,
                    Money(r.currency, r.reserved_amount),
                    ReservationStatus(r.status),
                    r.created_at_utc,
                    r.updated_at_utc,
                    Money(r.currency, r.settled_amount) if r.settled_amount is not None else None,
                )
                for r in rows
            )

    async def finalize(self, facts):
        if not isinstance(facts, AttemptFacts):
            raise LLMContractError("invalid_attempt_facts")
        integrity = None
        failed = False
        try:
            async with self._sessions() as session, session.begin():
                await session.connection(execution_options={"livingworld_write_intent": True})
                quote = await self._finalize_in_session(session, facts)
                integrity = await self._settle_in_session(session, facts, quote)
                await session.flush()
        except Exception:
            failed = True
        if failed:
            self._report(facts.start, "budget_finalization_incomplete")
            raise BudgetIntegrityError()
        if integrity:
            self._report(facts.start, integrity)
            raise BudgetIntegrityError(integrity)

    async def _settle_in_session(self, session, facts, quote):
        start = facts.start
        rows = (
            await session.scalars(
                select(LLMBudgetReservationRow).where(
                    LLMBudgetReservationRow.invocation_id == start.invocation_id.value,
                    LLMBudgetReservationRow.attempt_ordinal == start.attempt_ordinal,
                )
            )
        ).all()
        event = None
        for row in rows:
            status = ReservationStatus(row.status)
            if not _trusted_reservation(row, start):
                row.status = ReservationStatus.INTEGRITY_DEGRADED.value
                row.settled_amount = None
                event = "budget_finalization_incomplete"
                continue
            if status in DEGRADED:
                event = (
                    "budget_bound_violation"
                    if status is ReservationStatus.BOUND_VIOLATION
                    else "budget_finalization_incomplete"
                )
                continue
            if status in {ReservationStatus.SETTLED, ReservationStatus.RELEASED}:
                continue
            row.updated_at_utc = max(start.started_at_utc, facts.finished_at_utc)
            cost = quote.estimated_cost
            if cost is not None:
                if cost.currency != row.currency:
                    row.status, event = (
                        ReservationStatus.INTEGRITY_DEGRADED.value,
                        "budget_finalization_incomplete",
                    )
                elif cost.amount > row.reserved_amount:
                    row.status, event = (
                        ReservationStatus.BOUND_VIOLATION.value,
                        "budget_bound_violation",
                    )
                else:
                    row.status = ReservationStatus.SETTLED.value
                    row.settled_amount = cost.amount
            elif quote.status is CostStatus.NOT_DISPATCHED:
                row.status = ReservationStatus.RELEASED.value
            else:
                row.status = ReservationStatus.HELD_UNCERTAIN.value
        return event


class BudgetDiagnostics:
    def __init__(self, logger):
        self.logger = logger

    def __call__(self, diagnostic):
        self.logger.emit(
            "llm_budget",
            diagnostic.event,
            level="CRITICAL"
            if diagnostic.event in {"budget_bound_violation", "budget_finalization_incomplete"}
            else "WARNING",
            trace_id=str(diagnostic.invocation_id.value),
        )
