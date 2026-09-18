"""Offline pre-dispatch spend authorization, durable concurrency and failure safety."""

import asyncio
import json
from contextlib import aclosing
from dataclasses import replace
from datetime import timedelta, timezone
from decimal import Decimal, localcontext
from io import StringIO
from uuid import uuid4

import pytest
from alembic import command
from alembic.operations import Operations
from livingworld.application.llm import (
    DispatchState,
    FinishReason,
    InvocationId,
    LLMError,
    LLMErrorCode,
    LLMPurpose,
    LLMStreamCompletion,
    LLMUsage,
    ModelRef,
    ProviderId,
    StreamCompleted,
    StreamFailed,
    StreamStarted,
    TextDelta,
    UsageUpdate,
)
from livingworld.application.llm_accounting import (
    AccountingInfrastructureError,
    AttemptOutcome,
    LedgerQuery,
    UsageCompleteness,
)
from livingworld.application.llm_budget import (
    BoundGuarantee,
    BudgetAdmissionError,
    BudgetDiagnostic,
    BudgetId,
    BudgetMode,
    BudgetPolicy,
    BudgetReason,
    ModelLimitUsageBounder,
    ModelUsageLimits,
    ReservationStatus,
    UsageUpperBound,
)
from livingworld.application.llm_execution import ExecutingModelGateway
from livingworld.application.llm_preflight import PreflightPricingEngine, RequestedPricingEnvelope
from livingworld.application.llm_pricing import (
    InMemoryPricingCatalog,
    Meter,
    ModelAlias,
    Money,
    PricingEngine,
    PricingVariant,
    RateLine,
    UTCWindow,
)
from livingworld.domain.errors import ConcurrencyConflictError
from livingworld.domain.values import Revision
from livingworld.infrastructure.logging import StructuredLogger
from livingworld.infrastructure.persistence import Database
from livingworld.infrastructure.persistence.llm_budget_repository import BudgetDiagnostics
from livingworld.infrastructure.persistence.llm_repository import AccountingDiagnostics
from livingworld.infrastructure.persistence.migration import (
    ACCOUNTING_REVISION,
    HEAD_REVISION,
    _alembic_config,
)
from sqlalchemy import event, text
from test_llm_accounting import AT, database_run, facts, schedule, start
from test_llm_execution import ScriptedGateway, VirtualTime, failure, stream_success, success
from test_openai_compatible import CANARY, PROMPT, REASONING, RESPONSE, request

D = Decimal


def req(**changes):
    values = dict(invocation_id=InvocationId(uuid4()), max_output_tokens=30)
    values.update(changes)
    return replace(request(), **values)


def policy(**changes):
    values = dict(
        budget_id=BudgetId(uuid4()),
        enabled=True,
        mode=BudgetMode.HARD,
        limit=Money("USD", D("1.00")),
        start_utc=AT - timedelta(days=1),
        end_utc=AT + timedelta(days=1),
        created_at_utc=AT,
        updated_at_utc=AT,
    )
    values.update(changes)
    return BudgetPolicy(**values)


def catalog(model=None, rate="0.01", currency="USD"):
    return InMemoryPricingCatalog(
        (
            schedule(
                model,
                currency=currency,
                variants=(
                    PricingVariant(
                        variant_id="controlled", rates=(RateLine(Meter.OUTPUT, D(rate), 1),)
                    ),
                ),
            ),
        )
    )


def guard(db, request=None, *, prices=None, bounder=None, diagnostics=None, envelopes=()):
    request = request or req()
    return db.llm_budget_guard(
        catalog=prices or catalog(request.model),
        envelopes=envelopes,
        bounder=bounder or ModelLimitUsageBounder({request.model: ModelUsageLimits(100, 100)}),
        diagnostics=diagnostics if diagnostics is not None else lambda d: None,
    )


def execution(provider, guard, diagnostics=None):
    time = VirtualTime()
    return ExecutingModelGateway(
        provider,
        budget_guard=guard,
        clock=time.clock,
        sleep=time.sleep,
        random_unit=lambda: 0,
        wall_clock=lambda: AT,
        accounting_diagnostics=diagnostics if diagnostics is not None else lambda d: None,
    )


async def add(guard, *policies):
    for p in policies:
        await guard.put_policy(p, None)


async def counts(db):
    async with db.engine.connect() as conn:
        return tuple(
            [
                (await conn.execute(text(f"SELECT count(*) FROM {name}"))).scalar_one()
                for name in ("llm_attempts", "llm_budget_reservations")
            ]
        )


def test_hard_admission_is_durable_before_provider_and_settles_exact_estimate(tmp_path):
    async def run(db):
        r, p = req(), policy()
        g = guard(db, r)
        await add(g, p)
        original = success(r)

        class Provider:
            async def generate(self, received):
                assert received is r
                assert await counts(db) == (1, 1)
                records = await g.query(LedgerQuery())
                assert records[0].outcome is AttemptOutcome.INCOMPLETE
                view = await g.view(p.budget_id)
                assert view.held.amount == D("0.30")
                assert view.remaining.amount == D("0.70")
                return original

        assert await execution(Provider(), g).generate(r) is original
        view = await g.view(p.budget_id)
        assert view.known_estimated_spend.amount == D("0.03")
        assert view.held.amount == 0 and view.remaining.amount == D("0.97")
        reservation = (await g.reservations(p.budget_id))[0]
        assert reservation.status is ReservationStatus.SETTLED
        assert reservation.reserved.amount == D("0.30")
        assert reservation.settled.amount == D("0.03")

    asyncio.run(database_run(tmp_path, run))


def test_controlled_one_dollar_history_hold_and_new_bound_scenario(tmp_path):
    async def run(db):
        r, p = req(), policy()
        prices = catalog(r.model)
        ledger = db.llm_usage_ledger(catalog=prices)
        previous = start(req(), at=AT - timedelta(hours=1))
        await ledger.start(previous)
        await ledger.finalize(facts(previous, usage=LLMUsage(0, 40, 40)))
        g = guard(db, r, prices=prices)
        await add(g, p)  # Budget creation does not exclude older ledger activity.
        held = req(max_output_tokens=20)
        await g.admit(start(held), held)
        await g.finalize(
            facts(
                start(held),
                outcome=AttemptOutcome.FAILED,
                dispatch_state=DispatchState.DISPATCHED_OR_UNKNOWN,
                usage=None,
                completeness=UsageCompleteness.UNKNOWN,
            )
        )
        await g.admit(start(r), r)
        view = await g.view(p.budget_id)
        assert view.known_estimated_spend.amount == D("0.40")
        assert view.held.amount == D("0.50") and view.remaining.amount == D("0.10")
        next_request = req(max_output_tokens=20)
        provider = ScriptedGateway(success(next_request))
        with pytest.raises(BudgetAdmissionError) as denied:
            await execution(provider, g).generate(next_request)
        assert denied.value.reason is BudgetReason.EXCEEDED and not provider.requests
        assert await counts(db) == (3, 2)

    asyncio.run(database_run(tmp_path, run))


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize(
    "case", ["no_limits", "estimate", "unavailable", "no_price", "currency", "ambiguous_price"]
)
def test_unverifiable_hard_admission_never_dispatches(tmp_path, case, streaming):
    async def run(db):
        r, p = req(streaming=streaming), policy()
        b = ModelLimitUsageBounder({}) if case == "no_limits" else None
        if case in {"estimate", "unavailable"}:

            class Bounder:
                def bound(self, request):
                    return UsageUpperBound(
                        100,
                        30,
                        BoundGuarantee.ESTIMATE_ONLY
                        if case == "estimate"
                        else BoundGuarantee.UNAVAILABLE,
                    )

            b = Bounder()
        prices = (
            InMemoryPricingCatalog()
            if case == "no_price"
            else catalog(r.model, currency="EUR")
            if case == "currency"
            else InMemoryPricingCatalog(
                (schedule(r.model), schedule(r.model, schedule_id="duplicate"))
            )
            if case == "ambiguous_price"
            else catalog(r.model)
        )
        g = guard(db, r, bounder=b, prices=prices)
        await add(g, p)
        provider = ScriptedGateway(success(r))
        with pytest.raises(BudgetAdmissionError) as denied:
            if streaming:
                await anext(execution(provider, g).stream(r))
            else:
                await execution(provider, g).generate(r)
        assert denied.value.reason is (
            BudgetReason.CURRENCY_UNSUPPORTED if case == "currency" else BudgetReason.UNVERIFIABLE
        )
        assert not isinstance(denied.value, LLMError)
        assert denied.value.__context__ is None and not provider.requests
        assert await counts(db) == (0, 0)

    asyncio.run(database_run(tmp_path, run))


def test_multiple_hard_budgets_admit_or_deny_as_one_transaction(tmp_path):
    async def run(db):
        r = req()
        global_policy, purpose_policy = (
            policy(),
            policy(purpose=r.purpose, limit=Money("USD", D("0.20"))),
        )
        g = guard(db, r)
        await add(g, global_policy, purpose_policy)
        provider = ScriptedGateway(success(r))
        with pytest.raises(BudgetAdmissionError):
            await execution(provider, g).generate(r)
        assert not provider.requests and await counts(db) == (0, 0)
        changed = replace(purpose_policy, limit=Money("USD", D("1.00")), revision=Revision(1))
        await g.put_policy(changed, Revision())
        await execution(provider, g).generate(r)
        assert await counts(db) == (1, 2)
        for p in (global_policy, purpose_policy):
            assert (await g.view(p.budget_id)).known_estimated_spend.amount == D("0.03")

    asyncio.run(database_run(tmp_path, run))


@pytest.mark.parametrize("failure_point", ["start", "reservation"])
def test_accounting_start_and_all_reservations_roll_back_together(
    tmp_path, monkeypatch, failure_point
):
    async def run(db):
        r, p = req(), policy()
        log = StringIO()
        g = guard(db, r, diagnostics=BudgetDiagnostics(StructuredLogger(log)))
        await add(g, p)
        if failure_point == "start":
            original = g._start_in_session

            async def broken(session, record):
                await original(session, record)
                await session.flush()
                raise RuntimeError(f"SQL connection {PROMPT} {CANARY}")

            monkeypatch.setattr(g, "_start_in_session", broken)
        else:

            @event.listens_for(db.engine.sync_engine, "before_cursor_execute")
            def broken(conn, cursor, statement, parameters, context, many):
                if statement.startswith("INSERT INTO llm_budget_reservations"):
                    raise RuntimeError(f"SQL connection {RESPONSE} {CANARY}")

        provider = ScriptedGateway(success(r))
        with pytest.raises(AccountingInfrastructureError) as caught:
            await execution(provider, g, AccountingDiagnostics(StructuredLogger(log))).generate(r)
        assert not provider.requests and await counts(db) == (0, 0)
        assert caught.value.__context__ is None
        assert json.loads(log.getvalue())["event"] == "accounting_start_persistence_failed"
        assert all(c not in log.getvalue() for c in (PROMPT, RESPONSE, CANARY, "SQL", "connection"))

    asyncio.run(database_run(tmp_path, run))


def test_two_independent_database_instances_only_allow_one_concurrent_provider_call(tmp_path):
    async def run(db):
        other = Database(tmp_path)
        try:
            await other.initialize()
            one, two, p = req(max_output_tokens=80), req(max_output_tokens=80), policy()
            g1, g2 = guard(db, one), guard(other, two)
            await add(g1, p)
            started, release = asyncio.Event(), asyncio.Event()
            calls = []

            class Provider:
                async def generate(self, r):
                    calls.append(r)
                    started.set()
                    await release.wait()
                    return success(r)

            provider = Provider()
            tasks = [
                asyncio.create_task(execution(provider, g).generate(r))
                for g, r in ((g1, one), (g2, two))
            ]
            await asyncio.wait_for(started.wait(), 5)
            done, pending = await asyncio.wait(
                tasks, timeout=5, return_when=asyncio.FIRST_COMPLETED
            )
            assert len(done) == len(pending) == 1
            assert isinstance(next(iter(done)).exception(), BudgetAdmissionError)
            assert len(calls) == 1 and await counts(db) == (1, 1)
            assert (await g1.view(p.budget_id)).held.amount == D("0.80")
            release.set()
            results = await asyncio.gather(*tasks, return_exceptions=True)
            assert sum(isinstance(x, BudgetAdmissionError) for x in results) == 1
            assert len(calls) == 1
        finally:
            await other.close()

    asyncio.run(database_run(tmp_path, run))


@pytest.mark.parametrize("streaming", [False, True])
def test_retry_requires_new_admission_and_cannot_bypass_held_first_attempt(tmp_path, streaming):
    async def run(db):
        r, p = req(max_output_tokens=40, streaming=streaming), policy(limit=Money("USD", D("0.50")))
        g = guard(db, r)
        await add(g, p)
        provider = (
            ScriptedGateway([StreamFailed(failure(r))], stream_success(r))
            if streaming
            else ScriptedGateway(failure(r), success(r))
        )
        with pytest.raises(BudgetAdmissionError) as denied:
            if streaming:
                await anext(execution(provider, g).stream(r))
            else:
                await execution(provider, g).generate(r)
        assert denied.value.reason is BudgetReason.EXCEEDED
        assert len(provider.requests) == 1 and await counts(db) == (1, 1)
        row = (await g.query(LedgerQuery()))[0]
        assert (
            row.outcome is AttemptOutcome.FAILED
            and row.invocation_outcome is AttemptOutcome.LOCAL_ERROR
        )
        held = (await g.reservations(p.budget_id))[0]
        assert held.status is ReservationStatus.HELD_UNCERTAIN and held.reserved.amount == D("0.40")

    asyncio.run(database_run(tmp_path, run))


def test_proven_not_dispatched_releases_reservation_so_retry_can_fit(tmp_path):
    async def run(db):
        r, p = req(max_output_tokens=40), policy(limit=Money("USD", D("0.50")))
        g = guard(db, r)
        await add(g, p)
        provider = ScriptedGateway(
            failure(
                r,
                code=LLMErrorCode.PROVIDER_UNAVAILABLE,
                status=None,
                dispatch_state=DispatchState.NOT_DISPATCHED,
            ),
            success(r),
        )
        result = await execution(provider, g).generate(r)
        assert result is not None and len(provider.requests) == 2
        assert [r.status for r in await g.reservations(p.budget_id)] == [
            ReservationStatus.RELEASED,
            ReservationStatus.SETTLED,
        ]
        assert (await g.view(p.budget_id)).known_estimated_spend.amount == D("0.03")

    asyncio.run(database_run(tmp_path, run))


@pytest.mark.parametrize("incomplete", [False, True])
@pytest.mark.parametrize("mode", [BudgetMode.HARD, BudgetMode.SOFT])
def test_unbounded_historical_exposure_fails_hard_and_warns_soft(tmp_path, incomplete, mode):
    async def run(db):
        r, p = req(), policy(mode=mode)
        legacy = db.llm_usage_ledger()
        old = start(req())
        await legacy.start(old)
        if not incomplete:
            await legacy.finalize(
                facts(
                    old,
                    usage=None,
                    completeness=UsageCompleteness.UNKNOWN,
                    dispatch_state=DispatchState.DISPATCHED_OR_UNKNOWN,
                    outcome=AttemptOutcome.FAILED,
                )
            )
        diagnostics = []
        g = guard(db, r, diagnostics=diagnostics.append)
        await add(g, p)
        provider = ScriptedGateway(success(r))
        if mode is BudgetMode.HARD:
            with pytest.raises(BudgetAdmissionError) as denied:
                await execution(provider, g).generate(r)
            assert denied.value.reason is BudgetReason.STATE_UNCERTAIN and not provider.requests
        else:
            assert await execution(provider, g).generate(r) is not None
            assert len(provider.requests) == 1
        assert diagnostics[0].event == "budget_state_uncertain"
        assert (await g.view(p.budget_id)).has_unbounded_exposure

    asyncio.run(database_run(tmp_path, run))


def test_crash_restart_preserves_held_start_and_bounds_newly_created_overlapping_budget(tmp_path):
    async def run(db):
        old = req(max_output_tokens=40)
        old_policy = policy()
        g = guard(db, old)
        await add(g, old_policy)
        await g.admit(start(old), old)  # Simulate crash before any durable final fact.
        await db.close()
        restarted = Database(tmp_path)
        try:
            await restarted.initialize()
            r = req(max_output_tokens=30)
            new = policy(limit=Money("USD", D("0.50")))
            fresh = guard(restarted, r)
            await add(fresh, new)
            view = await fresh.view(new.budget_id)
            assert not view.has_unbounded_exposure and view.held.amount == D("0.40")
            assert view.remaining.amount == D("0.10")
            with pytest.raises(BudgetAdmissionError):
                await execution(ScriptedGateway(success(r)), fresh).generate(r)
            assert (await fresh.reservations(old_policy.budget_id))[
                0
            ].status is ReservationStatus.HELD
            assert (await fresh.query(LedgerQuery()))[0].outcome is AttemptOutcome.INCOMPLETE
        finally:
            await restarted.close()

    asyncio.run(database_run(tmp_path, run))


@pytest.mark.parametrize("issue", ["exceeded", "bound_missing", "price_missing", "currency"])
def test_soft_budget_warns_without_mutating_or_blocking_request(tmp_path, issue):
    async def run(db):
        r = req()
        p = policy(mode=BudgetMode.SOFT, limit=Money("USD", D("0.00")))
        log = StringIO()
        g = guard(
            db,
            r,
            bounder=ModelLimitUsageBounder({}) if issue == "bound_missing" else None,
            prices=InMemoryPricingCatalog()
            if issue == "price_missing"
            else catalog(r.model, currency="EUR")
            if issue == "currency"
            else None,
            diagnostics=BudgetDiagnostics(StructuredLogger(log)),
        )
        if issue == "exceeded":
            old = start(req())
            history = db.llm_usage_ledger(catalog=catalog(r.model))
            await history.start(old)
            await history.finalize(facts(old, usage=LLMUsage(0, 3, 3)))
        await add(g, p)
        provider = ScriptedGateway(success(r))
        original = provider.attempts[0]
        assert await execution(provider, g).generate(r) is original
        assert provider.requests == [r] and provider.requests[0] is r
        assert await g.reservations(p.budget_id) == ()
        warning = json.loads(log.getvalue())
        assert warning["level"] == "WARNING" and warning["event"].startswith("budget_")

    asyncio.run(database_run(tmp_path, run))


@pytest.mark.parametrize(
    "scope", ["none", "disabled", "off", "purpose", "provider", "model", "end_exclusive"]
)
def test_no_matching_budget_preserves_retry_behavior_without_calling_bounder(tmp_path, scope):
    async def run(db):
        r = req()

        class ForbiddenBounder:
            def bound(self, request):
                pytest.fail("Unmatched budget must not require a bound")

        g = guard(db, r, bounder=ForbiddenBounder())
        if scope != "none":
            p = policy(
                **(
                    {"enabled": False}
                    if scope == "disabled"
                    else {"mode": BudgetMode.OFF}
                    if scope == "off"
                    else {"purpose": LLMPurpose("different-purpose")}
                    if scope == "purpose"
                    else {"provider": ProviderId("different-provider")}
                    if scope == "provider"
                    else {"model": ModelRef(r.model.provider_id, r.model.model_id + "-different")}
                    if scope == "model"
                    else {"end_utc": AT}
                )
            )
            await add(g, p)
        provider = ScriptedGateway(failure(r), success(r))
        await execution(provider, g).generate(r)
        assert len(provider.requests) == 2 and await counts(db) == (2, 0)

    asyncio.run(database_run(tmp_path, run))


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("result", ["success", "retryable", "cancelled"])
def test_finalize_transaction_failure_preserves_original_outcome_and_holds(
    tmp_path, monkeypatch, streaming, result
):
    async def run(db):
        r, p = req(streaming=streaming), policy()
        log = StringIO()
        g = guard(db, r, diagnostics=BudgetDiagnostics(StructuredLogger(log)))
        await add(g, p)
        original_settle = g._settle_in_session

        async def broken(session, f, quote):
            await original_settle(session, f, quote)
            await session.flush()
            raise RuntimeError(f"SQL connection {CANARY} {PROMPT} {RESPONSE}")

        monkeypatch.setattr(g, "_settle_in_session", broken)
        original = success(r) if result == "success" else failure(r)
        if result == "cancelled":

            class Provider:
                calls = 0

                async def generate(self, request):
                    self.calls += 1
                    raise asyncio.CancelledError

                async def stream(self, request):
                    self.calls += 1
                    raise asyncio.CancelledError
                    yield  # Async iterator; cancellation never creates a terminal event.

            provider = Provider()
        else:
            events = stream_success(r) if result == "success" else [StreamFailed(original)]
            provider = (
                ScriptedGateway(events, stream_success(r))
                if streaming
                else ScriptedGateway(original, success(r))
            )
        ex = execution(provider, g)
        if result == "cancelled":
            with pytest.raises(asyncio.CancelledError):
                if streaming:
                    await anext(ex.stream(r))
                else:
                    await ex.generate(r)
            assert provider.calls == 1
        elif streaming:
            received = [e async for e in ex.stream(r)]
            if result == "success":
                assert received[-1] is events[-1]
            else:
                assert received[-1].failure is original
        elif result == "success":
            assert await ex.generate(r) is original
        else:
            with pytest.raises(LLMError) as caught:
                await ex.generate(r)
            assert caught.value.failure is original
        if result != "cancelled":
            assert len(provider.requests) == 1
        assert (await g.query(LedgerQuery()))[0].outcome is AttemptOutcome.INCOMPLETE
        assert (await g.reservations(p.budget_id))[0].status is ReservationStatus.HELD
        assert (await g.view(p.budget_id)).held.amount == D("0.30")
        diagnostic = json.loads(log.getvalue())
        assert (
            diagnostic["level"] == "CRITICAL"
            and diagnostic["event"] == "budget_finalization_incomplete"
        )
        assert all(c not in log.getvalue() for c in (CANARY, PROMPT, RESPONSE, "SQL", "connection"))

    asyncio.run(database_run(tmp_path, run))


def test_durable_accounting_with_stale_reservation_is_detected_and_fails_closed(tmp_path):
    async def run(db):
        r, p = req(), policy()
        g = guard(db, r)
        await add(g, p)
        await g.admit(start(r), r)
        await db.llm_usage_ledger(catalog=catalog(r.model)).finalize(
            facts(start(r), usage=LLMUsage(0, 3, 3))
        )
        view = await g.view(p.budget_id)
        assert view.integrity_degraded and view.remaining is None
        next_r = req()
        provider = ScriptedGateway(success(next_r))
        with pytest.raises(BudgetAdmissionError) as caught:
            await execution(provider, g).generate(next_r)
        assert caught.value.reason is BudgetReason.INTEGRITY_DEGRADED and not provider.requests

    asyncio.run(database_run(tmp_path, run))


def test_broken_hard_usage_bound_records_violation_without_rewriting_response(tmp_path):
    async def run(db):
        r, p = req(), policy()

        class BrokenBounder:
            def bound(self, request):
                return UsageUpperBound(100, 1)

        diagnostics = []
        g = guard(db, r, bounder=BrokenBounder(), diagnostics=diagnostics.append)
        await add(g, p)
        original = success(r)
        provider = ScriptedGateway(original)
        assert await execution(provider, g).generate(r) is original
        assert len(provider.requests) == 1
        reservation = (await g.reservations(p.budget_id))[0]
        assert reservation.status is ReservationStatus.BOUND_VIOLATION
        assert reservation.reserved.amount == D("0.01") and reservation.settled is None
        assert diagnostics[-1].event == "budget_bound_violation"
        assert (await g.view(p.budget_id)).integrity_degraded
        r2 = req()
        denied_provider = ScriptedGateway(success(r2))
        with pytest.raises(BudgetAdmissionError) as denied:
            await execution(denied_provider, g).generate(r2)
        assert (
            denied.value.reason is BudgetReason.INTEGRITY_DEGRADED and not denied_provider.requests
        )

    asyncio.run(database_run(tmp_path, run))


def test_stream_settles_only_latest_terminal_snapshot_and_never_accumulates_content(tmp_path):
    async def run(db):
        r, p = req(streaming=True), policy()
        g = guard(db, r)
        await add(g, p)
        terminal = StreamCompleted(
            LLMStreamCompletion(
                invocation_id=r.invocation_id,
                model_used=r.model,
                finish_reason=FinishReason.STOP,
                usage=LLMUsage(7, 3, 10),
            )
        )
        events = [
            StreamStarted(r.invocation_id, r.model),
            UsageUpdate(r.invocation_id, LLMUsage(7, 1, 8)),
            TextDelta(r.invocation_id, RESPONSE),
            UsageUpdate(r.invocation_id, LLMUsage(7, 2, 9)),
            terminal,
        ]
        provider = ScriptedGateway(events)
        received = []
        async with aclosing(execution(provider, g).stream(r)) as stream:
            async for e in stream:
                received.append(e)
                if isinstance(e, StreamStarted):
                    assert (await g.view(p.budget_id)).held.amount == D("0.30")
        assert received[-1] is terminal
        row = (await g.query(LedgerQuery()))[0]
        assert row.facts.usage.output_tokens == 3
        assert (await g.view(p.budget_id)).known_estimated_spend.amount == D("0.03")

    asyncio.run(database_run(tmp_path, run))


@pytest.mark.parametrize("abandoned", [False, True])
def test_interrupted_stream_retains_full_hold_without_completion_or_retry(tmp_path, abandoned):
    async def run(db):
        r, p = req(streaming=True), policy()
        g = guard(db, r)
        await add(g, p)
        events = [
            StreamStarted(r.invocation_id, r.model),
            UsageUpdate(r.invocation_id, LLMUsage(7, 2, 9)),
            StreamFailed(failure(r)),
        ]
        provider = ScriptedGateway(events)
        received = []
        async with aclosing(execution(provider, g).stream(r)) as stream:
            async for e in stream:
                received.append(e)
                if abandoned and isinstance(e, UsageUpdate):
                    break
        assert not any(isinstance(e, StreamCompleted) for e in received)
        assert len(provider.requests) == 1
        assert (await g.reservations(p.budget_id))[0].status is ReservationStatus.HELD_UNCERTAIN
        assert (await g.view(p.budget_id)).held.amount == D("0.30")
        assert (await g.query(LedgerQuery()))[0].facts.completeness is UsageCompleteness.PARTIAL

    asyncio.run(database_run(tmp_path, run))


def test_policy_cas_lowering_limit_and_disable_preserve_history(tmp_path):
    async def run(db):
        r, p = req(), policy()
        g = guard(db, r)
        await add(g, p)
        await execution(ScriptedGateway(success(r)), g).generate(r)
        original = (await g.query(LedgerQuery()))[0]
        lower = replace(p, limit=Money("USD", D("0.01")), revision=Revision(1))
        await g.put_policy(lower, Revision())
        with pytest.raises(ConcurrencyConflictError):
            await g.put_policy(lower, Revision())
        with pytest.raises(BudgetAdmissionError):
            await execution(ScriptedGateway(success(req())), g).generate(req())
        disabled = replace(lower, enabled=False, revision=Revision(2))
        await g.put_policy(disabled, Revision(1))
        r2 = req()
        await execution(ScriptedGateway(success(r2)), g).generate(r2)
        assert (await g.query(LedgerQuery(invocation_id=r.invocation_id)))[0] == original
        assert (await g.reservations(p.budget_id))[0].policy == p
        assert len(await g.reservations(p.budget_id)) == 1

    asyncio.run(database_run(tmp_path, run))


def test_utc_start_inclusive_end_exclusive_and_naive_rejected():
    r = req()
    p = policy(start_utc=AT.astimezone(timezone(timedelta(hours=8))))
    assert p.matches(start(r)) and not p.matches(start(r, at=p.end_utc))
    assert p.start_utc == AT
    with pytest.raises(ValueError, match="timezone-aware"):
        policy(start_utc=AT.replace(tzinfo=None))


def test_configured_model_limits_are_exact_and_use_trusted_caps_without_token_guessing():
    r = req()
    b = ModelLimitUsageBounder({r.model: ModelUsageLimits(4096, 100)})
    assert b.bound(r) == UsageUpperBound(4096, 30)
    assert b.bound(replace(r, max_output_tokens=101)) == UsageUpperBound(4096, 100)
    assert (
        b.bound(replace(r, model=ModelRef(r.model.provider_id, r.model.model_id + "-suffix")))
        is None
    )


def test_preflight_maximum_across_reachable_context_variants_not_cheap_or_largest_context():
    r = req()
    variants = (
        PricingVariant(
            variant_id="short-expensive",
            input_max_exclusive=10,
            rates=(RateLine(Meter.INPUT, D("2"), 1), RateLine(Meter.OUTPUT, D("0.01"), 1)),
        ),
        PricingVariant(
            variant_id="long-cheap",
            input_min=10,
            rates=(RateLine(Meter.INPUT, D("0.03"), 1), RateLine(Meter.OUTPUT, D("0.01"), 1)),
        ),
    )
    prices = InMemoryPricingCatalog((schedule(r.model, variants=variants),))
    bound = PreflightPricingEngine(prices).bound(
        requested=r.model, usage=UsageUpperBound(100, 10), at=AT
    )
    assert bound.money.amount == D("18.10")


@pytest.mark.parametrize(
    "issue", ["gap", "overlap", "missing_tier", "inactive_time", "unpriced_target"]
)
def test_preflight_incomplete_or_conflicting_pricing_is_unverifiable(issue):
    r = req()
    rate = (RateLine(Meter.OUTPUT, D("0.01"), 1),)
    variants = (
        (PricingVariant(variant_id="gap", input_min=1, rates=rate),)
        if issue == "gap"
        else (
            PricingVariant(variant_id="one", rates=rate),
            PricingVariant(variant_id="two", rates=rate),
        )
        if issue == "overlap"
        else (PricingVariant(variant_id="tier", rates=rate, processing_tier="priority"),)
        if issue == "missing_tier"
        else (PricingVariant(variant_id="time", rates=rate, utc_windows=(UTCWindow((0,), 0, 60),)),)
    )
    prices = (
        InMemoryPricingCatalog()
        if issue == "unpriced_target"
        else InMemoryPricingCatalog((schedule(r.model, variants=variants),))
    )
    assert (
        PreflightPricingEngine(prices).bound(
            requested=r.model, usage=UsageUpperBound(100, 30), at=AT
        )
        is None
    )


def test_preflight_known_tier_and_utc_context_only_use_compatible_variants():
    r = req()
    variants = (
        PricingVariant(
            variant_id="priority",
            processing_tier="priority",
            rates=(RateLine(Meter.OUTPUT, D("0.02"), 1),),
            utc_windows=(UTCWindow((4,), 60, 240),),
        ),
        PricingVariant(
            variant_id="flex",
            processing_tier="flex",
            rates=(RateLine(Meter.OUTPUT, D("0.001"), 1),),
        ),
    )
    e = RequestedPricingEnvelope(r.model, (r.model,), "priority")
    bound = PreflightPricingEngine(
        InMemoryPricingCatalog((schedule(r.model, variants=variants),)), envelopes=(e,)
    ).bound(requested=r.model, usage=UsageUpperBound(100, 30), at=AT)
    assert bound.money.amount == D("0.60")


def test_partition_and_rounding_bound_covers_reachable_actual_usage_with_low_decimal_context():
    r = req()
    variant = PricingVariant(
        variant_id="partition",
        rates=(
            RateLine(Meter.UNCACHED_INPUT, D("0.0007")),
            RateLine(Meter.CACHED_INPUT, D("0.0001")),
            RateLine(Meter.CACHE_WRITE_INPUT, D("0.0013")),
            RateLine(Meter.NON_REASONING_OUTPUT, D("0.0002")),
            RateLine(Meter.REASONING_OUTPUT, D("0.0009")),
        ),
    )
    prices = InMemoryPricingCatalog((schedule(r.model, variants=(variant,)),))
    with localcontext() as ctx:
        ctx.prec = 2
        bound = PreflightPricingEngine(prices).bound(
            requested=r.model, usage=UsageUpperBound(8, 8), at=AT
        )
        for ordinary in range(9):
            for cached in range(9 - ordinary):
                usage = LLMUsage(
                    8,
                    8,
                    16,
                    uncached_input_tokens=ordinary,
                    cached_input_tokens=cached,
                    cache_write_input_tokens=8 - ordinary - cached,
                    reasoning_output_tokens=cached,
                )
                priced = PricingEngine(prices).estimate(
                    requested=r.model, reported=r.model, at=AT, usage=usage
                )
                assert priced.estimated_cost.amount <= bound.money.amount


def alias_prices(r):
    cheap = ModelRef(r.model.provider_id, "concrete-cheap")
    expensive = ModelRef(r.model.provider_id, "concrete-expensive")
    prices = InMemoryPricingCatalog(
        (
            schedule(
                cheap,
                variants=(
                    PricingVariant(
                        variant_id="cheap", rates=(RateLine(Meter.OUTPUT, D("0.01"), 1),)
                    ),
                ),
            ),
            schedule(
                expensive,
                schedule_id="expensive",
                variants=(
                    PricingVariant(
                        variant_id="expensive", rates=(RateLine(Meter.OUTPUT, D("0.02"), 1),)
                    ),
                ),
            ),
        ),
        (ModelAlias(r.model, cheap),),
    )
    return cheap, expensive, prices


def test_unknown_alias_envelope_denied_before_dispatch_even_if_catalog_has_cheap_alias(tmp_path):
    async def run(db):
        r = req(model=ModelRef(ProviderId("configured-provider"), "alias"))
        _cheap, expensive, prices = alias_prices(r)
        g = guard(db, r, prices=prices)
        await add(g, policy(model=r.model))
        provider = ScriptedGateway(replace(success(r), model_used=expensive))
        with pytest.raises(BudgetAdmissionError) as denied:
            await execution(provider, g).generate(r)
        assert denied.value.reason is BudgetReason.UNVERIFIABLE
        assert not provider.requests and await counts(db) == (0, 0)

    asyncio.run(database_run(tmp_path, run))


@pytest.mark.parametrize("underestimated", [False, True])
def test_alias_scope_envelope_reported_pricing_and_analytics_remain_separate(
    tmp_path, underestimated
):
    async def run(db):
        r = req(model=ModelRef(ProviderId("configured-provider"), "alias"), max_output_tokens=20)
        cheap, expensive, prices = alias_prices(r)
        alias_policy, reported_policy = (
            policy(model=r.model),
            policy(model=expensive, limit=Money("USD", D("0"))),
        )
        diagnostics = []
        envelope = RequestedPricingEnvelope(
            r.model, (cheap,) if underestimated else (cheap, expensive)
        )
        g = guard(db, r, prices=prices, envelopes=(envelope,), diagnostics=diagnostics.append)
        await add(g, alias_policy, reported_policy)
        original = replace(success(r), model_used=expensive, usage=LLMUsage(0, 20, 20))
        provider = ScriptedGateway(original)
        assert await execution(provider, g).generate(r) is original
        assert len(provider.requests) == 1
        reported_view = await g.view(reported_policy.budget_id)
        assert reported_view.known_estimated_spend.amount == 0 and reported_view.held.amount == 0
        assert (
            not reported_view.has_unbounded_exposure
            and await g.reservations(reported_policy.budget_id) == ()
        )
        assert (
            len(await g.query(LedgerQuery(model_id=expensive.model_id))) == 1
        )  # Analytics OR remains.
        alias_view = await g.view(alias_policy.budget_id)
        assert alias_view.known_estimated_spend.amount == D("0.40")
        reservation = (await g.reservations(alias_policy.budget_id))[0]
        if underestimated:
            assert reservation.status is ReservationStatus.BOUND_VIOLATION
            assert (
                alias_view.integrity_degraded and diagnostics[-1].event == "budget_bound_violation"
            )
            next_r = replace(r, invocation_id=InvocationId(uuid4()))
            with pytest.raises(BudgetAdmissionError) as denied:
                await execution(ScriptedGateway(success(next_r)), g).generate(next_r)
            assert denied.value.reason is BudgetReason.INTEGRITY_DEGRADED
        else:
            assert reservation.reserved.amount == D("0.40")
            assert (
                reservation.settled.amount == D("0.40")
                and reservation.status is ReservationStatus.SETTLED
            )
            assert not alias_view.integrity_degraded and not diagnostics

    asyncio.run(database_run(tmp_path, run))


def test_raw_operational_database_and_safe_diagnostics_exclude_all_content_canaries(tmp_path):
    async def run(db):
        r = req(metadata={"prompt": PROMPT, "output": RESPONSE, "secret": CANARY})
        p = policy()
        logs = StringIO()
        g = guard(db, r, diagnostics=BudgetDiagnostics(StructuredLogger(logs)))
        await add(g, p)
        original = replace(
            success(r), usage=LLMUsage(7, 3, 10, {"content": RESPONSE, "secret": CANARY})
        )
        await execution(ScriptedGateway(original), g).generate(r)
        safe = repr(await g.view(p.budget_id)) + repr(await g.reservations(p.budget_id))
        safe += json.dumps({"event": BudgetDiagnostic(r.invocation_id, 1, "budget_exceeded").event})
        assert all(c not in safe + logs.getvalue() for c in (PROMPT, RESPONSE, REASONING, CANARY))
        await db.close()
        assert all(
            c.encode() not in db.path.read_bytes() for c in (PROMPT, RESPONSE, REASONING, CANARY)
        )

    asyncio.run(database_run(tmp_path, run))


@pytest.mark.parametrize("inject_failure", [False, True])
def test_0010_upgrade_preserves_0009_attempts_and_audit_and_ddl_failure_rolls_back(
    tmp_path, monkeypatch, inject_failure
):
    async def run():
        db = Database(tmp_path)
        try:
            async with db.engine.begin() as conn:
                await conn.run_sync(
                    lambda c: command.upgrade(_alembic_config(c), ACCOUNTING_REVISION)
                )
            ledger = db.llm_usage_ledger(catalog=catalog())
            record = start(req())
            await ledger.start(record)
            await ledger.finalize(facts(record, usage=LLMUsage(0, 3, 3)))
            previous = await ledger.query(LedgerQuery())
            async with db.engine.connect() as conn:
                audit = (await conn.execute(text("SELECT * FROM migration_history"))).all()
            if inject_failure:
                original = Operations.create_index

                def broken(self, name, *a, **kw):
                    if name == "ix_llm_reservation_attempt":
                        raise RuntimeError("controlled_budget_ddl_failure")
                    return original(self, name, *a, **kw)

                monkeypatch.setattr(Operations, "create_index", broken)
                with pytest.raises(RuntimeError, match="controlled_budget_ddl_failure"):
                    await db.initialize()
            else:
                await db.initialize()
                await db.initialize()
            assert await ledger.query(LedgerQuery()) == previous
            async with db.engine.connect() as conn:
                assert (await conn.execute(text("SELECT * FROM migration_history"))).all() == audit
                assert (
                    await conn.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar_one() == (ACCOUNTING_REVISION if inject_failure else HEAD_REVISION)
                names = (
                    (await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")))
                    .scalars()
                    .all()
                )
                assert (
                    ("llm_budgets" in names)
                    == ("llm_budget_reservations" in names)
                    == (not inject_failure)
                )
        finally:
            await db.close()

    asyncio.run(run())


def test_known_foreign_currency_history_is_not_ignored_or_converted(tmp_path):
    async def run(db):
        r, p = req(), policy()
        old = start(req())
        ledger = db.llm_usage_ledger(catalog=catalog(r.model, currency="EUR"))
        await ledger.start(old)
        await ledger.finalize(facts(old, usage=LLMUsage(0, 3, 3)))
        g = guard(db, r)
        await add(g, p)
        view = await g.view(p.budget_id)
        assert view.currency_unsupported and view.remaining is None
        assert view.known_estimated_spend.amount == 0  # No USD/EUR summation.
        provider = ScriptedGateway(success(r))
        with pytest.raises(BudgetAdmissionError) as denied:
            await execution(provider, g).generate(r)
        assert denied.value.reason is BudgetReason.CURRENCY_UNSUPPORTED and not provider.requests

    asyncio.run(database_run(tmp_path, run))


def test_bound_violation_survives_restart_and_new_budget_id_or_window(tmp_path):
    async def run(db):
        r, p = req(), policy(model=req().model)

        class Broken:
            def bound(self, request):
                return UsageUpperBound(100, 1)

        g = guard(db, r, bounder=Broken())
        await add(g, p)
        await execution(ScriptedGateway(success(r)), g).generate(r)
        await db.close()
        restarted = Database(tmp_path)
        try:
            await restarted.initialize()
            correct = guard(restarted, r)
            new = policy(
                model=r.model, start_utc=AT + timedelta(days=2), end_utc=AT + timedelta(days=3)
            )
            await add(correct, new)
            assert (await correct.view(new.budget_id)).integrity_degraded
            new_r = req()
            provider = ScriptedGateway(success(new_r))
            later = ExecutingModelGateway(
                provider,
                budget_guard=correct,
                wall_clock=lambda: AT + timedelta(days=2),
                accounting_diagnostics=lambda d: None,
            )
            with pytest.raises(BudgetAdmissionError) as denied:
                await later.generate(new_r)
            assert denied.value.reason is BudgetReason.INTEGRITY_DEGRADED and not provider.requests
        finally:
            await restarted.close()

    asyncio.run(database_run(tmp_path, run))


def test_unknown_reported_pricing_keeps_original_scope_and_full_hold(tmp_path):
    async def run(db):
        r, p = req(), policy(model=req().model)
        g = guard(db, r)
        await add(g, p)
        unknown = ModelRef(r.model.provider_id, "unmapped-reported-model")
        original = replace(success(r), model_used=unknown)
        assert await execution(ScriptedGateway(original), g).generate(r) is original
        view = await g.view(p.budget_id)
        assert view.held.amount == D("0.30") and not view.has_unbounded_exposure
        assert view.known_estimated_spend.amount == 0
        assert (await g.reservations(p.budget_id))[0].status is ReservationStatus.HELD_UNCERTAIN

    asyncio.run(database_run(tmp_path, run))


def test_final_reported_price_currency_drift_degrades_integrity_without_rewriting_success(tmp_path):
    async def run(db):
        r, p = req(), policy()
        concrete = ModelRef(r.model.provider_id, "reported-eur")
        prices = InMemoryPricingCatalog(
            (*catalog(r.model)._schedules, *catalog(concrete, currency="EUR")._schedules)
        )
        logs = []
        g = guard(db, r, prices=prices, diagnostics=logs.append)
        await add(g, p)
        original = replace(success(r), model_used=concrete)
        assert await execution(ScriptedGateway(original), g).generate(r) is original
        assert (await g.reservations(p.budget_id))[0].status is ReservationStatus.INTEGRITY_DEGRADED
        assert (await g.view(p.budget_id)).integrity_degraded
        assert logs[-1].event == "budget_finalization_incomplete"
        next_r = req()
        provider = ScriptedGateway(success(next_r))
        with pytest.raises(BudgetAdmissionError):
            await execution(provider, g).generate(next_r)
        assert not provider.requests

    asyncio.run(database_run(tmp_path, run))


def test_duplicate_admission_never_grants_generation_replay_permission(tmp_path):
    async def run(db):
        r, p = req(), policy()
        g = guard(db, r)
        await add(g, p)
        await g.admit(start(r), r)
        provider = ScriptedGateway(success(r))
        with pytest.raises(AccountingInfrastructureError):
            await execution(provider, g).generate(r)
        assert not provider.requests and await counts(db) == (1, 1)

    asyncio.run(database_run(tmp_path, run))
