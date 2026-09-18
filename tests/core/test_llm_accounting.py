"""Offline accounting integrity, factual usage, exact pricing and privacy invariants."""

import asyncio
import json
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from io import StringIO

import httpx
import pytest
from alembic import command
from alembic.operations import Operations
from livingworld.application.llm import (
    DispatchState,
    FinishReason,
    LLMContractError,
    LLMError,
    LLMErrorCode,
    LLMStreamCompletion,
    LLMUsage,
    ModelRef,
    ProviderId,
    StreamCompleted,
    StreamFailed,
    StreamOutcome,
    StreamStarted,
    StructuredOutputMode,
    StructuredOutputRequest,
    TextDelta,
    UsageUpdate,
)
from livingworld.application.llm_accounting import (
    AccountingInfrastructureError,
    AttemptFacts,
    AttemptOutcome,
    AttemptStart,
    LedgerQuery,
    UsageCompleteness,
    summarize,
)
from livingworld.application.llm_execution import ExecutingModelGateway, RetryPolicy
from livingworld.application.llm_pricing import (
    CostStatus,
    InMemoryPricingCatalog,
    Meter,
    ModelAlias,
    Money,
    PricingConfigurationError,
    PricingEngine,
    PricingSchedule,
    PricingVariant,
    RateLine,
    UTCWindow,
)
from livingworld.infrastructure.llm.openai_compatible import (
    ChatCompletionsProfile,
    OpenAICompatibleChatGateway,
    _InvalidResponse,
    _usage,
)
from livingworld.infrastructure.logging import StructuredLogger
from livingworld.infrastructure.persistence import Database
from livingworld.infrastructure.persistence.llm_repository import AccountingDiagnostics, _encode
from livingworld.infrastructure.persistence.migration import (
    HEAD_REVISION,
    PACKAGE_REVISION,
    _alembic_config,
)
from sqlalchemy import text
from test_llm_execution import ScriptedGateway, VirtualTime, failure, stream_success, success
from test_openai_compatible import (
    CANARY,
    PROMPT,
    REASONING,
    RESPONSE,
    Credentials,
    Wire,
    config,
    fixture,
    request,
)

AT = datetime(2026, 9, 18, 3, tzinfo=UTC)  # Friday UTC peak in controlled DeepSeek data
D = Decimal
STANDARD_USAGE = LLMUsage(
    1000,
    50,
    1050,
    cached_input_tokens=200,
    cache_write_input_tokens=100,
    uncached_input_tokens=700,
    reasoning_output_tokens=20,
)


def rates(input_rate="4", cached="0.4", write="5", output="20"):
    return tuple(
        RateLine(meter, D(rate))
        for meter, rate in (
            (Meter.UNCACHED_INPUT, input_rate),
            (Meter.CACHED_INPUT, cached),
            (Meter.CACHE_WRITE_INPUT, write),
            (Meter.OUTPUT, output),
        )
    )


def schedule(model=None, **changes):
    values = dict(
        schedule_id="controlled-2026-09-18",
        model=model or request().model,
        currency="USD",
        effective_from=AT - timedelta(days=1),
        variants=(PricingVariant(variant_id="short", rates=rates()),),
        source_label="openai-pricing-accessed-2026-09-18-controlled",
    )
    values.update(changes)
    return PricingSchedule(**values)


def quote(
    schedules=None,
    *,
    requested=None,
    reported=None,
    at=AT,
    usage=STANDARD_USAGE,
    tier=None,
    aliases=(),
):
    requested = requested or request().model
    engine = PricingEngine(InMemoryPricingCatalog(schedules or (schedule(requested),), aliases))
    return engine.estimate(
        requested=requested, reported=reported, at=at, usage=usage, processing_tier=tier
    )


def start(req=None, ordinal=1, at=AT):
    req = req or request()
    return AttemptStart(req.invocation_id, ordinal, req.purpose, req.model, at)


def facts(record, **changes):
    values = dict(
        start=record,
        finished_at_utc=record.started_at_utc + timedelta(milliseconds=17),
        latency_ms=17,
        outcome=AttemptOutcome.SUCCESS,
        dispatch_state=DispatchState.HTTP_RESPONSE_RECEIVED,
        reported_model=record.requested_model,
        finish_reason=FinishReason.STOP,
        usage=STANDARD_USAGE,
        completeness=UsageCompleteness.FINAL,
    )
    values.update(changes)
    return AttemptFacts(**values)


class BrokenSink:
    def __init__(self, ledger, *, on_start=False, on_finalize=False):
        self.ledger, self.on_start, self.on_finalize = ledger, on_start, on_finalize

    async def start(self, record):
        if self.on_start:
            raise RuntimeError(f"SQL connection C:/private {PROMPT} {RESPONSE} {CANARY}")
        await self.ledger.start(record)

    async def finalize(self, record):
        if self.on_finalize:
            raise RuntimeError(f"SQL connection C:/private {PROMPT} {RESPONSE} {CANARY}")
        await self.ledger.finalize(record)


def executor(gateway, sink, diagnostics):
    time = VirtualTime()
    return ExecutingModelGateway(
        gateway,
        accounting=sink,
        wall_clock=lambda: AT,
        accounting_diagnostics=diagnostics,
        clock=time.clock,
        sleep=time.sleep,
        policy=RetryPolicy(initial_backoff_seconds=0),
    )


async def database_run(tmp_path, action):
    db = Database(tmp_path)
    try:
        await db.initialize()
        return await action(db)
    finally:
        await db.close()


def assert_clean_diagnostics(log):
    for canary in (PROMPT, RESPONSE, REASONING, CANARY, "SQL", "connection", "C:/private"):
        assert canary not in log
    records = [json.loads(line) for line in log.splitlines()]
    assert records and all(r["level"] == "CRITICAL" for r in records)
    assert all(
        r["event"] in {"accounting_persistence_incomplete", "accounting_start_persistence_failed"}
        for r in records
    )


@pytest.mark.parametrize("streaming", [False, True])
def test_start_failure_blocks_provider_with_explicit_local_error(tmp_path, streaming):
    async def run(db):
        req = request(streaming=streaming)
        gateway = ScriptedGateway(success(req))
        log = StringIO()
        execution = executor(
            gateway,
            BrokenSink(db.llm_usage_ledger(), on_start=True),
            AccountingDiagnostics(StructuredLogger(log)),
        )
        with pytest.raises(AccountingInfrastructureError) as caught:
            if streaming:
                await anext(execution.stream(req))
            else:
                await execution.generate(req)
        assert not isinstance(caught.value, LLMError)
        assert caught.value.__context__ is None
        assert not gateway.requests
        assert await db.llm_usage_ledger().query(LedgerQuery()) == ()
        assert_clean_diagnostics(log.getvalue())

    asyncio.run(database_run(tmp_path, run))


@pytest.mark.parametrize("action", ["success", "retryable", "structured", "cancelled"])
def test_finalize_failure_preserves_original_outcome_and_stops_retry(tmp_path, action):
    async def run(db):
        req, log = request(), StringIO()
        original = success(req)
        if action == "retryable":
            original = failure(req)
        elif action == "structured":
            from livingworld.application.llm import LLMAttemptSummary

            original = failure(
                req,
                code=LLMErrorCode.STRUCTURED_OUTPUT_FAILED,
                status=200,
                attempt=LLMAttemptSummary(req.model, STANDARD_USAGE, FinishReason.STOP, 1),
            )
        if action == "cancelled":

            class CancelGateway:
                calls = 0

                async def generate(self, req):
                    self.calls += 1
                    raise asyncio.CancelledError

            gateway = CancelGateway()
        else:
            gateway = ScriptedGateway(original, success(req))
        ledger = db.llm_usage_ledger()
        execution = executor(
            gateway,
            BrokenSink(ledger, on_finalize=True),
            AccountingDiagnostics(StructuredLogger(log)),
        )
        if action == "success":
            assert await execution.generate(req) is original
        elif action == "cancelled":
            with pytest.raises(asyncio.CancelledError):
                await execution.generate(req)
        else:
            with pytest.raises(LLMError) as caught:
                await execution.generate(req)
            assert caught.value.failure is original
        assert (gateway.calls if action == "cancelled" else len(gateway.requests)) == 1
        rows = await ledger.query(LedgerQuery())
        assert len(rows) == 1 and rows[0].outcome is AttemptOutcome.INCOMPLETE
        assert rows[0].quote.estimated_cost is None and rows[0].facts is None
        summary = summarize(rows)
        assert summary.known_estimated_cost == () and summary.known_input_tokens is None
        assert summary.has_incomplete_attempts and summary.has_possible_billing_exposure
        assert summary.final_outcome is AttemptOutcome.INCOMPLETE
        assert_clean_diagnostics(log.getvalue())

    asyncio.run(database_run(tmp_path, run))


@pytest.mark.parametrize("action", ["success", "hidden_retryable", "cancelled"])
def test_stream_finalize_failure_never_replays_and_preserves_completion_or_cancel(tmp_path, action):
    async def run(db):
        req = request(streaming=True)
        events = stream_success(req)
        if action == "hidden_retryable":
            events = [StreamFailed(failure(req))]
        elif action == "cancelled":
            events = [
                StreamStarted(req.invocation_id, req.model),
                UsageUpdate(req.invocation_id, LLMUsage(7, 2, 9)),
                asyncio.CancelledError(),
            ]
        gateway = ScriptedGateway(events, stream_success(req))
        log = StringIO()
        ledger = db.llm_usage_ledger()
        execution = executor(
            gateway,
            BrokenSink(ledger, on_finalize=True),
            AccountingDiagnostics(StructuredLogger(log)),
        )
        if action == "cancelled":
            with pytest.raises(asyncio.CancelledError):
                [event async for event in execution.stream(req)]
        else:
            received = [event async for event in execution.stream(req)]
            if action == "success":
                assert received[-1] is events[-1]
                assert len([e for e in received if isinstance(e, StreamCompleted)]) == 1
            else:
                assert len(received) == 1 and received[0].failure is events[0].failure
        assert len(gateway.requests) == 1 and gateway.closed == [1]
        rows = await ledger.query(LedgerQuery())
        assert rows[0].outcome is AttemptOutcome.INCOMPLETE
        assert summarize(rows).has_possible_billing_exposure
        assert_clean_diagnostics(log.getvalue())

    asyncio.run(database_run(tmp_path, run))


@pytest.mark.parametrize("finish", [FinishReason.STOP, FinishReason.REFUSAL])
def test_success_refusal_usage_is_final_and_priced(tmp_path, finish):
    async def run(db):
        req = request()
        ledger = db.llm_usage_ledger(catalog=InMemoryPricingCatalog((schedule(req.model),)))
        response = replace(success(req, finish), usage=STANDARD_USAGE)
        assert (
            await executor(
                ScriptedGateway(response), ledger, lambda d: pytest.fail(repr(d))
            ).generate(req)
            is response
        )
        rows = await ledger.query(LedgerQuery())
        assert rows[0].facts.completeness is UsageCompleteness.FINAL
        assert rows[0].facts.finish_reason is finish
        assert rows[0].quote.estimated_cost == Money("USD", D("0.004380000"))

    asyncio.run(database_run(tmp_path, run))


@pytest.mark.parametrize("action", ["completed", "failed", "cancelled", "abandoned", "missing"])
def test_stream_snapshot_accounting_is_final_or_partial_never_additive(tmp_path, action):
    async def run(db):
        req = request(streaming=True)
        first, latest = LLMUsage(5, 1, 6), LLMUsage(7, 3, 10)
        events = [
            StreamStarted(req.invocation_id, req.model),
            UsageUpdate(req.invocation_id, first),
            UsageUpdate(req.invocation_id, latest),
            TextDelta(req.invocation_id, RESPONSE),
        ]
        if action == "completed":
            events.append(
                StreamCompleted(
                    LLMStreamCompletion(
                        invocation_id=req.invocation_id,
                        model_used=req.model,
                        finish_reason=FinishReason.STOP,
                        usage=latest,
                    )
                )
            )
        elif action == "cancelled":
            events.append(asyncio.CancelledError())
        elif action == "missing":
            events = [StreamStarted(req.invocation_id, req.model)]
        else:
            events.append(StreamFailed(failure(req)))
        ledger = db.llm_usage_ledger()
        execution = executor(ScriptedGateway(events), ledger, lambda d: pytest.fail(repr(d)))
        if action == "abandoned":
            stream = execution.stream(req)
            for _ in range(4):
                await anext(stream)
            await stream.aclose()
        elif action in {"cancelled", "missing"}:
            with pytest.raises(
                asyncio.CancelledError if action == "cancelled" else LLMContractError
            ):
                [event async for event in execution.stream(req)]
        else:
            received = [event async for event in execution.stream(req)]
            assert any(isinstance(e, StreamCompleted) for e in received) == (action == "completed")
        row = (await ledger.query(LedgerQuery()))[0]
        assert row.facts.usage == (None if action == "missing" else latest)
        assert row.facts.completeness is (
            UsageCompleteness.UNKNOWN
            if action == "missing"
            else UsageCompleteness.FINAL
            if action == "completed"
            else UsageCompleteness.PARTIAL
        )
        assert summarize((row,)).known_input_tokens == (None if action == "missing" else 7)

    asyncio.run(database_run(tmp_path, run))


def test_retries_create_distinct_records_unknown_exposure_survives(tmp_path):
    async def run(db):
        req = request()
        response = replace(success(req), usage=STANDARD_USAGE)
        ledger = db.llm_usage_ledger(catalog=InMemoryPricingCatalog((schedule(req.model),)))
        gateway = ScriptedGateway(failure(req), response)
        assert (
            await executor(gateway, ledger, lambda d: pytest.fail(repr(d))).generate(req)
            is response
        )
        rows = await ledger.query(LedgerQuery(invocation_id=req.invocation_id))
        assert [row.start.attempt_ordinal for row in rows] == [1, 2]
        assert rows[0].quote.status is CostStatus.USAGE_UNKNOWN
        assert rows[1].quote.status is CostStatus.PRICED
        summary = summarize(rows)
        assert summary.attempt_count == 2 and summary.known_input_tokens == 1000
        assert summary.known_estimated_cost == (Money("USD", D("0.004380000")),)
        assert (
            summary.has_unknown_usage
            and summary.has_unknown_cost
            and summary.has_possible_billing_exposure
        )
        assert summary.final_outcome is AttemptOutcome.SUCCESS

    asyncio.run(database_run(tmp_path, run))


@pytest.mark.parametrize("streaming", [False, True])
def test_cancel_during_backoff_keeps_attempt_failed_and_invocation_cancelled(tmp_path, streaming):
    async def run(db):
        req = request(streaming=streaming)
        gateway = ScriptedGateway([StreamFailed(failure(req))] if streaming else failure(req))
        ledger = db.llm_usage_ledger()

        async def cancel_sleep(seconds):
            raise asyncio.CancelledError

        execution = ExecutingModelGateway(
            gateway,
            accounting=ledger,
            wall_clock=lambda: AT,
            accounting_diagnostics=lambda d: pytest.fail(repr(d)),
            sleep=cancel_sleep,
        )
        with pytest.raises(asyncio.CancelledError):
            if streaming:
                [e async for e in execution.stream(req)]
            else:
                await execution.generate(req)
        rows = await ledger.query(LedgerQuery())
        assert len(rows) == 1 and rows[0].outcome is AttemptOutcome.FAILED
        assert summarize(rows).final_outcome is AttemptOutcome.CANCELLED
        assert len(gateway.requests) == 1

    asyncio.run(database_run(tmp_path, run))


def test_hidden_stream_attempts_are_accounted_and_latest_snapshot_can_be_terminal(tmp_path):
    async def run(db):
        req = request(streaming=True)
        events = stream_success(req)
        events[-1] = StreamCompleted(replace(events[-1].completion, usage=None))
        gateway = ScriptedGateway([StreamFailed(failure(req))], events)
        ledger = db.llm_usage_ledger()
        received = [
            e async for e in executor(gateway, ledger, lambda d: pytest.fail(repr(d))).stream(req)
        ]
        assert len([e for e in received if isinstance(e, StreamStarted)]) == 1
        assert len([e for e in received if isinstance(e, StreamCompleted)]) == 1
        rows = await ledger.query(LedgerQuery())
        assert [r.start.attempt_ordinal for r in rows] == [1, 2]
        assert rows[1].facts.usage == LLMUsage(7, 3, 10)
        assert rows[1].facts.completeness is UsageCompleteness.FINAL
        assert summarize(rows).final_outcome is AttemptOutcome.SUCCESS

    asyncio.run(database_run(tmp_path, run))


def test_unknown_usage_objects_stay_unknown_and_unsafe_metadata_is_projected_out(tmp_path):
    async def run(db):
        ledger = db.llm_usage_ledger()
        req = request()
        response = replace(success(req), usage=LLMUsage(details={"private": PROMPT}))
        await executor(ScriptedGateway(response), ledger, lambda d: pytest.fail(repr(d))).generate(
            req
        )
        row = (await ledger.query(LedgerQuery()))[0]
        assert row.facts.usage is None and row.facts.completeness is UsageCompleteness.UNKNOWN
        assert row.quote.estimated_cost is None

    asyncio.run(database_run(tmp_path, run))


def test_reported_tier_is_factual_and_pricing_requires_actual_context(tmp_path):
    async def run(db):
        req = request()
        body = fixture()
        body["model"] = req.model.model_id
        body["service_tier"] = "flex"
        catalog = InMemoryPricingCatalog(
            (
                schedule(
                    req.model,
                    variants=(
                        PricingVariant(
                            variant_id="flex",
                            rates=(RateLine(Meter.INPUT, D("1")), RateLine(Meter.OUTPUT, D("2"))),
                            processing_tier="flex",
                        ),
                    ),
                ),
            )
        )
        ledger = db.llm_usage_ledger(catalog=catalog)
        async with OpenAICompatibleChatGateway(
            config(), Credentials(), transport=httpx.MockTransport(Wire(body))
        ) as gateway:
            result = await executor(gateway, ledger, lambda d: pytest.fail(repr(d))).generate(req)
        assert result.processing_tier == "flex"
        row = (await ledger.query(LedgerQuery(model_id=req.model.model_id)))[0]
        assert row.facts.processing_tier == "flex"
        assert row.quote.status is CostStatus.PRICED
        assert row.quote.snapshot.processing_tier == "flex"

    asyncio.run(database_run(tmp_path, run))


@pytest.mark.parametrize(
    "dispatch,status",
    [
        (DispatchState.NOT_DISPATCHED, CostStatus.NOT_DISPATCHED),
        (DispatchState.DISPATCHED_OR_UNKNOWN, CostStatus.POSSIBLY_BILLED_UNKNOWN),
        (DispatchState.HTTP_RESPONSE_RECEIVED, CostStatus.USAGE_UNKNOWN),
    ],
)
def test_missing_usage_never_becomes_zero_cost(tmp_path, dispatch, status):
    async def run(db):
        req = request()
        ledger = db.llm_usage_ledger()
        error = failure(req, code=LLMErrorCode.AUTHENTICATION, status=None, dispatch_state=dispatch)
        with pytest.raises(LLMError):
            await executor(ScriptedGateway(error), ledger, lambda d: pytest.fail(repr(d))).generate(
                req
            )
        row = (await ledger.query(LedgerQuery()))[0]
        assert row.quote.status is status and row.quote.estimated_cost is None
        assert row.facts.usage is None and row.facts.completeness is UsageCompleteness.UNKNOWN
        assert summarize((row,)).has_possible_billing_exposure == (
            dispatch is not DispatchState.NOT_DISPATCHED
        )

    asyncio.run(database_run(tmp_path, run))


def test_duplicate_delivery_is_idempotent_historical_estimate_survives_catalog_update(tmp_path):
    async def run(db):
        record = start()
        catalog = InMemoryPricingCatalog((schedule(record.requested_model),))
        ledger = db.llm_usage_ledger(catalog=catalog)
        await asyncio.gather(ledger.start(record), ledger.start(record))
        completed = facts(record)
        await asyncio.gather(ledger.finalize(completed), ledger.finalize(completed))
        original = (await ledger.query(LedgerQuery()))[0]
        changed = db.llm_usage_ledger(
            catalog=InMemoryPricingCatalog(
                (
                    schedule(
                        record.requested_model,
                        schedule_id="changed",
                        variants=(PricingVariant(variant_id="new", rates=rates("99")),),
                    ),
                )
            )
        )
        await changed.finalize(completed)
        assert (await changed.query(LedgerQuery())) == (original,)
        assert original.quote.snapshot.schedule.schedule_id == "controlled-2026-09-18"
        with pytest.raises(LLMContractError, match="conflicting_attempt_finalization"):
            await ledger.finalize(replace(completed, latency_ms=999))
        with pytest.raises(LLMContractError, match="conflicting_attempt_start"):
            await ledger.start(replace(record, started_at_utc=AT + timedelta(seconds=1)))
        assert len(await ledger.query(LedgerQuery())) == 1

    asyncio.run(database_run(tmp_path, run))


def test_incomplete_restart_keeps_unknown_exposure_and_queries_are_scoped(tmp_path):
    async def create(db):
        ledger = db.llm_usage_ledger()
        record = start()
        await ledger.start(record)
        return record

    record = asyncio.run(database_run(tmp_path, create))

    async def restart(db):
        ledger = db.llm_usage_ledger()
        rows = await ledger.query(
            LedgerQuery(
                since_utc=AT,
                until_utc=AT + timedelta(seconds=1),
                provider_id=record.requested_model.provider_id.value,
                model_id=record.requested_model.model_id,
                purpose=record.purpose,
            )
        )
        assert len(rows) == 1 and rows[0].facts is None
        assert rows[0].quote.estimated_cost is None
        assert summarize(rows).has_incomplete_attempts
        assert not await ledger.query(LedgerQuery(until_utc=AT))
        assert not await ledger.query(LedgerQuery(provider_id="other"))
        assert not await ledger.query(LedgerQuery(model_id="other"))
        assert not await ledger.query(LedgerQuery(purpose=replace(record.purpose, value="other")))

    asyncio.run(database_run(tmp_path, restart))


def test_real_finalize_sql_failure_rolls_back_without_replaying_provider(tmp_path):
    from sqlalchemy import event

    async def run(db):
        req, log = request(), StringIO()
        ledger = db.llm_usage_ledger(catalog=InMemoryPricingCatalog((schedule(req.model),)))
        original = replace(success(req), usage=STANDARD_USAGE)
        gateway = ScriptedGateway(original, original)

        def broken_update(connection, cursor, statement, parameters, context, executemany):
            if statement.startswith("UPDATE llm_attempts"):
                raise RuntimeError(f"SQL finalize {PROMPT} {RESPONSE} {CANARY}")

        event.listen(db.engine.sync_engine, "before_cursor_execute", broken_update)
        try:
            result = await executor(
                gateway, ledger, AccountingDiagnostics(StructuredLogger(log))
            ).generate(req)
            assert result is original and len(gateway.requests) == 1
            row = (await ledger.query(LedgerQuery()))[0]
            assert row.outcome is AttemptOutcome.INCOMPLETE
            assert row.facts is None and row.quote.estimated_cost is None
            assert summarize((row,)).has_possible_billing_exposure
            assert_clean_diagnostics(log.getvalue())
        finally:
            event.remove(db.engine.sync_engine, "before_cursor_execute", broken_update)

    asyncio.run(database_run(tmp_path, run))


@pytest.mark.parametrize("outcome", [StreamOutcome.REFUSAL, StreamOutcome.CONTENT_FILTERED])
def test_stream_refusal_and_filter_are_success_with_final_factual_usage(tmp_path, outcome):
    async def run(db):
        req = request(streaming=True)
        events = stream_success(req, finish=FinishReason.REFUSAL, result=outcome)
        ledger = db.llm_usage_ledger()
        received = [
            e
            async for e in executor(
                ScriptedGateway(events), ledger, lambda d: pytest.fail(repr(d))
            ).stream(req)
        ]
        assert received[-1] is events[-1]
        row = (await ledger.query(LedgerQuery()))[0]
        assert row.facts.outcome is AttemptOutcome.SUCCESS
        assert row.facts.stream_outcome is outcome
        assert (
            row.facts.completeness is UsageCompleteness.FINAL and row.facts.usage.output_tokens == 3
        )

    asyncio.run(database_run(tmp_path, run))


def test_multiple_priced_attempts_and_currencies_remain_separate(tmp_path):
    async def run(db):
        req = request()
        usd = db.llm_usage_ledger(catalog=InMemoryPricingCatalog((schedule(req.model),)))
        eur = db.llm_usage_ledger(
            catalog=InMemoryPricingCatalog((schedule(req.model, currency="EUR"),))
        )
        for ordinal, ledger in enumerate((usd, usd, eur), 1):
            record = start(req, ordinal)
            await ledger.start(record)
            await ledger.finalize(
                facts(
                    record, outcome=AttemptOutcome.FAILED if ordinal < 3 else AttemptOutcome.SUCCESS
                )
            )
        await usd.complete_invocation(req.invocation_id, AttemptOutcome.SUCCESS)
        summary = summarize(await usd.query(LedgerQuery()))
        assert summary.known_input_tokens == 3000 and summary.known_output_tokens == 150
        assert summary.known_estimated_cost == (
            Money("EUR", D("0.004380000")),
            Money("USD", D("0.008760000")),
        )
        assert not summary.has_unknown_cost and summary.final_outcome is AttemptOutcome.SUCCESS
        with sqlite3.connect(db.path) as sql:
            assert sql.execute(
                "SELECT DISTINCT typeof(estimated_cost) FROM llm_attempts"
            ).fetchall() == [("text",)]

    asyncio.run(database_run(tmp_path, run))


@pytest.mark.parametrize("mode", ["valid", "parse", "schema", "truncated", "refusal", "empty"])
def test_real_wire_accounting_retains_usage_and_never_persists_content(tmp_path, mode):
    async def run(db):
        body = fixture("deepseek_chat")
        body["choices"][0]["message"]["content"] = RESPONSE if mode == "parse" else '{"ok": true}'
        body["choices"][0]["message"]["reasoning_content"] = REASONING
        if mode == "truncated":
            body["choices"][0]["finish_reason"] = "length"
        if mode == "refusal":
            body["choices"][0]["message"]["refusal"] = RESPONSE
        if mode == "schema":
            body["choices"][0]["message"]["content"] = '{"ok": "' + RESPONSE + '"}'
        if mode == "empty":
            body["choices"][0]["message"]["content"] = ""
        req = request(
            structured_output=StructuredOutputRequest(
                "safe",
                {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
            ),
            metadata={
                "character_belief": "LW_BELIEF_DB_CANARY",
                "player_knowledge": "LW_PLAYER_DB_CANARY",
            },
        )
        wire, log = Wire(body), StringIO()
        ledger = db.llm_usage_ledger()
        async with OpenAICompatibleChatGateway(
            config(),
            Credentials(),
            transport=httpx.MockTransport(wire),
            profile=ChatCompletionsProfile(
                structured_output_mode=StructuredOutputMode.JSON_OBJECT_LOCAL_VALIDATE
            ),
        ) as gateway:
            execution = executor(gateway, ledger, AccountingDiagnostics(StructuredLogger(log)))
            if mode in {"parse", "schema", "truncated", "empty"}:
                with pytest.raises(LLMError):
                    await execution.generate(req)
            else:
                await execution.generate(req)
        row = (await ledger.query(LedgerQuery()))[0]
        assert row.facts.usage.input_tokens == 12 and row.facts.usage.cached_input_tokens == 4
        assert (
            row.facts.usage.uncached_input_tokens == 8
            and row.facts.usage.reasoning_output_tokens == 2
        )
        assert row.facts.completeness is UsageCompleteness.FINAL
        assert len(wire.requests) == 1
        with sqlite3.connect(db.path) as sql:
            raw = repr(sql.execute("SELECT * FROM llm_attempts").fetchall()).encode()
            for table in (
                "world_events",
                "knowledge_assertions",
                "content_character_definitions",
                "content_lore_entries",
            ):
                assert sql.execute(f"SELECT COUNT(*) FROM {table}").fetchone() == (0,)
        for canary in (
            CANARY,
            PROMPT,
            RESPONSE,
            REASONING,
            "LW_BELIEF_DB_CANARY",
            "LW_PLAYER_DB_CANARY",
        ):
            assert canary.encode() not in raw and canary not in log.getvalue()
        assert "authorization" not in raw.decode().lower()
        # Closed codec rejects full responses/requests/credentials rather than hiding repr.
        for unsafe in (req, Credentials(), success(req)):
            with pytest.raises(LLMContractError, match="unsupported_accounting_value"):
                _encode(unsafe)

    asyncio.run(database_run(tmp_path, run))
    raw_files = b"".join(path.read_bytes() for path in tmp_path.glob("runtime.sqlite3*"))
    for canary in (
        CANARY,
        PROMPT,
        RESPONSE,
        REASONING,
        "LW_BELIEF_DB_CANARY",
        "LW_PLAYER_DB_CANARY",
    ):
        assert canary.encode() not in raw_files


def test_official_usage_breakdowns_and_missing_fields():
    openai = _usage(
        {
            "prompt_tokens": 1000,
            "completion_tokens": 50,
            "total_tokens": 1050,
            "prompt_tokens_details": {"cached_tokens": 200, "cache_write_tokens": 100},
            "completion_tokens_details": {"reasoning_tokens": 20},
        }
    )
    assert replace(openai, details={}) == STANDARD_USAGE
    deepseek = _usage(
        {
            "prompt_tokens": 1000,
            "completion_tokens": 50,
            "prompt_cache_hit_tokens": 200,
            "prompt_cache_miss_tokens": 800,
            "completion_tokens_details": {"reasoning_tokens": 20},
        }
    )
    assert deepseek.cached_input_tokens == 200 and deepseek.uncached_input_tokens == 800
    assert deepseek.cache_write_input_tokens is None
    missing = _usage({"prompt_tokens": 10, "prompt_tokens_details": {"cached_tokens": 2}})
    assert missing.uncached_input_tokens is None and missing.cache_write_input_tokens is None
    assert missing.output_tokens is None


@pytest.mark.parametrize(
    "usage",
    [
        {
            "prompt_tokens": 10,
            "prompt_tokens_details": {"cached_tokens": 8, "cache_write_tokens": 3},
        },
        {"prompt_tokens": 10, "prompt_cache_hit_tokens": 2, "prompt_cache_miss_tokens": 7},
        {
            "prompt_tokens": 10,
            "prompt_cache_hit_tokens": 2,
            "prompt_tokens_details": {"cached_tokens": 3},
        },
        {"completion_tokens": 2, "completion_tokens_details": {"reasoning_tokens": 3}},
        {"prompt_cache_miss_tokens": -1},
    ],
)
def test_impossible_provider_partitions_fail_without_clamping(usage):
    with pytest.raises(_InvalidResponse):
        _usage(usage)


def test_openai_fixture_prices_cache_write_context_and_reasoning_without_double_count():
    variants = (
        PricingVariant(variant_id="short", rates=rates(), input_max_exclusive=10000),
        PricingVariant(variant_id="long", rates=rates("8", "0.8", "10", "30"), input_min=10000),
    )
    assert quote((schedule(variants=variants),)).estimated_cost == Money("USD", D("0.004380000"))
    long_usage = replace(
        STANDARD_USAGE, input_tokens=10000, total_tokens=10050, uncached_input_tokens=9700
    )
    result = quote((schedule(variants=variants),), usage=long_usage)
    assert result.estimated_cost == Money("USD", D("0.080260000"))
    assert result.snapshot.selected_variant_id == "long"
    assert len(result.snapshot.line_items) == 4
    assert result.snapshot.line_items[-1].quantity == 50  # Includes reasoning, not 70.


def test_deepseek_fixture_utc_weekday_peak_off_peak_boundary():
    weekdays = (0, 1, 2, 3, 4)
    peak = (UTCWindow(weekdays, 60, 240), UTCWindow(weekdays, 360, 600))
    off = (
        UTCWindow(weekdays, 0, 60),
        UTCWindow(weekdays, 240, 360),
        UTCWindow(weekdays, 600, 1440),
        UTCWindow((5, 6), 0, 1440),
    )

    def deep_rates(miss, hit, output):
        return tuple(
            RateLine(m, D(r))
            for m, r in (
                (Meter.UNCACHED_INPUT, miss),
                (Meter.CACHED_INPUT, hit),
                (Meter.OUTPUT, output),
            )
        )

    variants = (
        PricingVariant(
            variant_id="peak", rates=deep_rates("0.3", "0.006", "1.2"), utc_windows=peak
        ),
        PricingVariant(variant_id="off", rates=deep_rates("0.15", "0.003", "0.6"), utc_windows=off),
    )
    catalog = (
        schedule(
            variants=variants,
            effective_from=AT - timedelta(days=7),
            source_label="deepseek-pricing-accessed-2026-09-18-controlled",
        ),
    )
    usage = LLMUsage(
        1000,
        50,
        1050,
        cached_input_tokens=200,
        uncached_input_tokens=800,
        reasoning_output_tokens=20,
    )
    assert quote(catalog, usage=usage).estimated_cost.amount == D("0.000301200")
    assert quote(catalog, usage=usage, at=AT.replace(hour=4)).estimated_cost.amount == D(
        "0.000150600"
    )
    assert quote(catalog, usage=usage, at=AT + timedelta(days=1)).estimated_cost.amount == D(
        "0.000150600"
    )


def test_effective_date_model_alias_selection_unknown_context_and_ambiguity():
    old = schedule(effective_until=AT)
    new = schedule(
        schedule_id="new",
        effective_from=AT,
        variants=(PricingVariant(variant_id="changed", rates=rates("8")),),
    )
    assert quote((old, new)).snapshot.schedule.schedule_id == "new"
    assert (
        quote((old, new), at=AT - timedelta(seconds=1)).snapshot.schedule.schedule_id
        == old.schedule_id
    )
    unknown = ModelRef(ProviderId("configured-provider"), "unmapped")
    assert quote(reported=unknown).status is CostStatus.PRICE_UNKNOWN
    alias = ModelAlias(request().model, new.model, allow_requested_fallback=True)
    assert quote((new,), reported=unknown, aliases=(alias,)).status is CostStatus.PRICED
    assert quote((schedule(),), requested=unknown).status is CostStatus.PRICE_UNKNOWN
    assert (
        quote(
            (
                schedule(
                    variants=(
                        PricingVariant(variant_id="tier", rates=rates(), processing_tier="flex"),
                    )
                ),
            )
        ).status
        is CostStatus.PRICING_CONTEXT_INCOMPLETE
    )
    assert (
        quote(
            (
                schedule(
                    variants=(
                        PricingVariant(variant_id="tier", rates=rates(), processing_tier="flex"),
                    )
                ),
            ),
            tier="flex",
        ).status
        is CostStatus.PRICED
    )
    with pytest.raises(PricingConfigurationError, match="ambiguous_pricing_variants"):
        quote((schedule(), schedule(schedule_id="conflicting")))
    assert quote(usage=LLMUsage(10, 3, 13)).status is CostStatus.PRICING_CONTEXT_INCOMPLETE
    with pytest.raises(PricingConfigurationError, match="overlapping_billing_meters"):
        PricingVariant(
            variant_id="bad",
            rates=(RateLine(Meter.OUTPUT, D("1")), RateLine(Meter.REASONING_OUTPUT, D("2"))),
        )


def test_money_is_exact_context_independent_and_rounding_is_explicit():
    with pytest.raises(PricingConfigurationError, match="invalid_money"):
        Money("USD", 0.1)
    variant = PricingVariant(
        variant_id="round-half-even", rates=(RateLine(Meter.OUTPUT, D("0.0005")),)
    )
    with localcontext() as context:
        context.prec = 2
        assert quote(
            (schedule(variants=(variant,)),), usage=LLMUsage(output_tokens=1)
        ).estimated_cost.amount == D("0.000000000")
        assert quote(
            (schedule(variants=(variant,)),), usage=LLMUsage(output_tokens=3)
        ).estimated_cost.amount == D("0.000000002")
    with pytest.raises(ValueError):
        quote(at=AT.replace(tzinfo=None))


def test_explicit_output_partition_prices_reasoning_once():
    variant = PricingVariant(
        variant_id="output-partition",
        rates=(
            RateLine(Meter.NON_REASONING_OUTPUT, D("1")),
            RateLine(Meter.REASONING_OUTPUT, D("2")),
        ),
    )
    result = quote((schedule(variants=(variant,)),))
    assert [item.quantity for item in result.snapshot.line_items] == [30, 20]
    assert result.estimated_cost == Money("USD", D("0.000070000"))


def test_final_snapshot_can_still_have_unreported_input_and_summary_flags_it(tmp_path):
    async def run(db):
        req = request()
        ledger = db.llm_usage_ledger()
        response = replace(success(req), usage=LLMUsage(output_tokens=3))
        await executor(ScriptedGateway(response), ledger, lambda d: pytest.fail(repr(d))).generate(
            req
        )
        rows = await ledger.query(LedgerQuery())
        assert rows[0].facts.completeness is UsageCompleteness.FINAL
        summary = summarize(rows)
        assert summary.has_unknown_usage and summary.known_input_tokens is None
        assert summary.known_output_tokens == 3

    asyncio.run(database_run(tmp_path, run))


@pytest.mark.parametrize("inject_failure", [False, True])
def test_0009_upgrade_preserves_prior_rows_and_rolls_back_on_failure(
    tmp_path, monkeypatch, inject_failure
):
    async def run():
        db = Database(tmp_path)
        try:
            async with db.engine.begin() as conn:
                await conn.run_sync(lambda c: command.upgrade(_alembic_config(c), PACKAGE_REVISION))
                before = (await conn.execute(text("SELECT * FROM migration_history"))).all()
            if inject_failure:
                original = Operations.create_index

                def broken(self, name, *args, **kwargs):
                    if name == "ix_llm_attempt_model":
                        raise RuntimeError("controlled_accounting_ddl_failure")
                    return original(self, name, *args, **kwargs)

                monkeypatch.setattr(Operations, "create_index", broken)
                with pytest.raises(RuntimeError, match="controlled_accounting_ddl_failure"):
                    await db.initialize()
            else:
                await db.initialize()
                await db.initialize()
            async with db.engine.connect() as conn:
                assert (await conn.execute(text("SELECT * FROM migration_history"))).all() == before
                assert (
                    await conn.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar_one() == (PACKAGE_REVISION if inject_failure else HEAD_REVISION)
                tables = (
                    (await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")))
                    .scalars()
                    .all()
                )
                assert ("llm_attempts" in tables) != inject_failure
        finally:
            await db.close()

    asyncio.run(run())
