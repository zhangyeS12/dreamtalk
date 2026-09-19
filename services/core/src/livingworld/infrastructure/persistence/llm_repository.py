"""Transactional start/finalize ledger; immutable historical pricing snapshots."""

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from sqlalchemy import or_, select

from livingworld.application.llm import (
    DispatchState,
    FinishReason,
    InvocationId,
    LLMContractError,
    LLMErrorCode,
    LLMPurpose,
    LLMUsage,
    ModelRef,
    ProviderId,
    ReasoningTokenRelation,
    StreamOutcome,
)
from livingworld.application.llm_accounting import (
    AccountingDiagnostic,
    AttemptFacts,
    AttemptOutcome,
    AttemptRecord,
    AttemptStart,
    LedgerQuery,
    UsageCompleteness,
)
from livingworld.application.llm_budget import (
    BoundGuarantee,
    BudgetId,
    BudgetMode,
    BudgetPolicy,
    UsageUpperBound,
)
from livingworld.application.llm_preflight import MoneyUpperBound
from livingworld.application.llm_pricing import (
    CostStatus,
    InMemoryPricingCatalog,
    Meter,
    Money,
    PriceLineItem,
    PriceQuote,
    PriceSnapshot,
    PricingEngine,
    PricingSchedule,
    PricingVariant,
    RateLine,
    UTCWindow,
)
from livingworld.domain.values import Revision
from livingworld.infrastructure.logging import StructuredLogger
from livingworld.infrastructure.persistence.llm_models import LLMAttemptRow

_TYPES = {
    cls.__name__: cls
    for cls in (
        InvocationId,
        LLMPurpose,
        ModelRef,
        ProviderId,
        LLMUsage,
        AttemptStart,
        AttemptFacts,
        Money,
        PriceLineItem,
        PriceSnapshot,
        PricingSchedule,
        PricingVariant,
        RateLine,
        UTCWindow,
        BudgetId,
        BudgetPolicy,
        UsageUpperBound,
        MoneyUpperBound,
        Revision,
    )
}
_ENUMS = {
    cls.__name__: cls
    for cls in (
        DispatchState,
        FinishReason,
        LLMErrorCode,
        StreamOutcome,
        AttemptOutcome,
        UsageCompleteness,
        CostStatus,
        Meter,
        BudgetMode,
        BoundGuarantee,
        ReasoningTokenRelation,
    )
}


def _encode(value):
    """Closed typed codec. It cannot serialize requests, responses or credentials."""
    if value is None or type(value) in (str, int, bool):
        return value
    if isinstance(value, Enum) and type(value).__name__ in _ENUMS:
        return {"type": type(value).__name__, "value": value.value}
    if isinstance(value, (datetime, Decimal, UUID)):
        return {
            "type": type(value).__name__,
            "value": value.isoformat() if isinstance(value, datetime) else str(value),
        }
    if is_dataclass(value) and _TYPES.get(type(value).__name__) is type(value):
        return {
            "type": type(value).__name__,
            "fields": {f.name: _encode(getattr(value, f.name)) for f in fields(value)},
        }
    if type(value) is tuple:
        return {"type": "tuple", "items": [_encode(v) for v in value]}
    if isinstance(value, Mapping):
        return {"type": "mapping", "items": {k: _encode(v) for k, v in value.items()}}
    raise LLMContractError("unsupported_accounting_value")


def _decode(value):
    if value is None or type(value) in (str, int, bool):
        return value
    if type(value) is not dict:
        raise LLMContractError("corrupt_accounting_record")
    tag = value.get("type")
    if tag in _TYPES:
        return _TYPES[tag](**{k: _decode(v) for k, v in value["fields"].items()})
    if tag in _ENUMS:
        return _ENUMS[tag](value["value"])
    if tag == "datetime":
        return datetime.fromisoformat(value["value"])
    if tag == "Decimal":
        return Decimal(value["value"])
    if tag == "UUID":
        return UUID(value["value"])
    if tag == "tuple":
        return tuple(_decode(v) for v in value["items"])
    if tag == "mapping":
        return {k: _decode(v) for k, v in value["items"].items()}
    raise LLMContractError("corrupt_accounting_record")


def _start(row):
    return AttemptStart(
        InvocationId(row.invocation_id),
        row.attempt_ordinal,
        LLMPurpose(row.purpose),
        ModelRef(ProviderId(row.provider_id), row.requested_model),
        row.started_at_utc,
    )


class SqlAlchemyUsageLedger:
    """Each operation has an independent operational transaction. No provider IO."""

    def __init__(self, sessions, *, catalog=None):
        self._sessions = sessions
        self._pricing = PricingEngine(catalog if catalog is not None else InMemoryPricingCatalog())

    async def start(self, record: AttemptStart):
        if not isinstance(record, AttemptStart):
            raise LLMContractError("invalid_attempt_start")
        async with self._sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            await self._start_in_session(session, record)

    async def _start_in_session(self, session, record):
        row = await session.get(LLMAttemptRow, (record.invocation_id.value, record.attempt_ordinal))
        if row is not None:
            if _start(row) != record:
                raise LLMContractError("conflicting_attempt_start")
            return
        closed = await session.scalar(
            select(LLMAttemptRow.invocation_id)
            .where(
                LLMAttemptRow.invocation_id == record.invocation_id.value,
                LLMAttemptRow.invocation_outcome.is_not(None),
            )
            .limit(1)
        )
        if closed is not None:
            raise LLMContractError("invocation_already_completed")
        session.add(
            LLMAttemptRow(
                invocation_id=record.invocation_id.value,
                attempt_ordinal=record.attempt_ordinal,
                purpose=record.purpose.value,
                provider_id=record.requested_model.provider_id.value,
                requested_model=record.requested_model.model_id,
                started_at_utc=record.started_at_utc,
                outcome=AttemptOutcome.INCOMPLETE.value,
                cost_status=CostStatus.POSSIBLY_BILLED_UNKNOWN.value,
            )
        )

    async def complete_invocation(self, invocation_id, outcome):
        if (
            not isinstance(invocation_id, InvocationId)
            or not isinstance(outcome, AttemptOutcome)
            or outcome is AttemptOutcome.INCOMPLETE
        ):
            raise LLMContractError("invalid_invocation_terminal")
        async with self._sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            row = (
                await session.scalars(
                    select(LLMAttemptRow)
                    .where(LLMAttemptRow.invocation_id == invocation_id.value)
                    .order_by(LLMAttemptRow.attempt_ordinal.desc())
                    .limit(1)
                )
            ).one_or_none()
            if row is None or row.facts is None:
                raise LLMContractError("invocation_accounting_incomplete")
            if row.invocation_outcome is not None and row.invocation_outcome != outcome.value:
                raise LLMContractError("conflicting_invocation_terminal")
            row.invocation_outcome = outcome.value

    async def finalize(self, facts: AttemptFacts):
        if not isinstance(facts, AttemptFacts):
            raise LLMContractError("invalid_attempt_facts")
        async with self._sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            await self._finalize_in_session(session, facts)

    async def _finalize_in_session(self, session, facts):
        start = facts.start
        row = await session.get(LLMAttemptRow, (start.invocation_id.value, start.attempt_ordinal))
        if row is None or _start(row) != start:
            raise LLMContractError("attempt_start_missing_or_conflicting")
        if row.facts is not None:
            if _decode(row.facts) != facts:
                raise LLMContractError("conflicting_attempt_finalization")
            return PriceQuote(
                CostStatus(row.cost_status),
                _decode(row.price_snapshot) if row.price_snapshot else None,
            )  # Never reprice.
        if facts.dispatch_state in {
            DispatchState.NOT_DISPATCHED,
            DispatchState.REJECTED_BEFORE_EXECUTION,
        }:
            quote = PriceQuote(CostStatus.NOT_DISPATCHED)
        elif facts.completeness is UsageCompleteness.UNKNOWN:
            quote = PriceQuote(
                CostStatus.POSSIBLY_BILLED_UNKNOWN
                if facts.dispatch_state is DispatchState.DISPATCHED_OR_UNKNOWN
                else CostStatus.USAGE_UNKNOWN
            )
        elif facts.completeness is UsageCompleteness.PARTIAL:
            quote = PriceQuote(CostStatus.USAGE_PARTIAL)
        else:
            quote = self._pricing.estimate(
                requested=start.requested_model,
                reported=facts.reported_model,
                at=start.started_at_utc,
                usage=facts.usage,
                processing_tier=facts.processing_tier,
            )
        row.facts = _encode(facts)
        row.finished_at_utc, row.outcome = facts.finished_at_utc, facts.outcome.value
        row.reported_model = facts.reported_model.model_id if facts.reported_model else None
        row.cost_status = quote.status.value
        if quote.snapshot:
            row.price_snapshot = _encode(quote.snapshot)
            row.currency, row.estimated_cost = (
                quote.estimated_cost.currency,
                quote.estimated_cost.amount,
            )
        return quote

    async def query(self, query: LedgerQuery):
        if not isinstance(query, LedgerQuery):
            raise LLMContractError("invalid_ledger_query")
        statement = select(LLMAttemptRow)
        for value, column in (
            (
                query.invocation_id.value if query.invocation_id else None,
                LLMAttemptRow.invocation_id,
            ),
            (query.provider_id, LLMAttemptRow.provider_id),
            (query.purpose.value if query.purpose else None, LLMAttemptRow.purpose),
        ):
            if value is not None:
                statement = statement.where(column == value)
        if query.model_id is not None:
            statement = statement.where(
                or_(
                    LLMAttemptRow.requested_model == query.model_id,
                    LLMAttemptRow.reported_model == query.model_id,
                )
            )
        if query.since_utc is not None:
            statement = statement.where(LLMAttemptRow.started_at_utc >= query.since_utc)
        if query.until_utc is not None:
            statement = statement.where(LLMAttemptRow.started_at_utc < query.until_utc)
        statement = statement.order_by(
            LLMAttemptRow.started_at_utc, LLMAttemptRow.invocation_id, LLMAttemptRow.attempt_ordinal
        )
        async with self._sessions() as session:
            rows = (await session.scalars(statement)).all()
            return tuple(
                AttemptRecord(
                    _start(row),
                    _decode(row.facts) if row.facts else None,
                    PriceQuote(
                        CostStatus(row.cost_status),
                        _decode(row.price_snapshot) if row.price_snapshot else None,
                    ),
                    AttemptOutcome(row.invocation_outcome) if row.invocation_outcome else None,
                )
                for row in rows
            )


class AccountingDiagnostics:
    """Fixed severe operational events; exception objects never reach the logger."""

    def __init__(self, logger: StructuredLogger):
        self.logger = logger

    def __call__(self, diagnostic: AccountingDiagnostic):
        self.logger.emit(
            "llm_accounting",
            diagnostic.event,
            level="CRITICAL",
            trace_id=str(diagnostic.invocation_id.value),
        )
