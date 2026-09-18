"""Offline attempt semantics, dispatch certainty and deterministic retry lifecycle."""

import asyncio
import json
from contextlib import aclosing
from dataclasses import FrozenInstanceError, asdict, replace
from datetime import UTC, datetime
from io import StringIO

import httpx
import pytest
from livingworld.application.llm import (
    DispatchState,
    FinishReason,
    LLMAttemptSummary,
    LLMContractError,
    LLMError,
    LLMErrorCode,
    LLMFailure,
    LLMResponse,
    LLMStreamCompletion,
    LLMUsage,
    StreamCompleted,
    StreamFailed,
    StreamOutcome,
    StreamStarted,
    StructuredFailureDetail,
    StructuredFailureReason,
    StructuredOutputMode,
    StructuredOutputRequest,
    TextContent,
    TextDelta,
    UsageUpdate,
)
from livingworld.application.llm_execution import (
    ExecutingModelGateway,
    ExponentialBackoff,
    JitterStrategy,
    RetryPolicy,
    RetryReason,
    decide_retry,
)
from livingworld.application.llm_serialization import request_to_data
from livingworld.infrastructure.llm.openai_compatible import (
    ChatCompletionsProfile,
    OpenAICompatibleChatGateway,
    _retry_after,
)
from livingworld.infrastructure.logging import StructuredLogger
from test_llm_streaming import (
    RAW,
    collect,
    normal,
)
from test_llm_streaming import (
    Wire as StreamWire,
)
from test_openai_compatible import (
    CANARY,
    PROMPT,
    REASONING,
    RESPONSE,
    Credentials,
    Wire,
    config,
    fixture,
    outcome,
    request,
)


class VirtualTime:
    def __init__(self):
        self.value = 10.0
        self.waits = []
        self.oversleep = 0.0

    def clock(self):
        return self.value

    async def sleep(self, seconds):
        self.waits.append(seconds)
        self.value += seconds + self.oversleep
        await asyncio.sleep(0)


class ScriptedGateway:
    def __init__(self, *attempts):
        self.attempts = list(attempts)
        self.requests, self.closed = [], []

    async def generate(self, req):
        self.requests.append(req)
        action = self.attempts.pop(0)
        if isinstance(action, LLMFailure):
            raise LLMError(action)
        return action

    async def stream(self, req):
        self.requests.append(req)
        ordinal = len(self.requests)
        action = self.attempts.pop(0)
        try:
            for event in action:
                if isinstance(event, BaseException):
                    raise event
                yield event
        finally:
            self.closed.append(ordinal)


def failure(req, code=LLMErrorCode.RATE_LIMITED, status=429, **extra):
    values = dict(dispatch_state=DispatchState.HTTP_RESPONSE_RECEIVED, http_status=status)
    values.update(extra)
    return LLMFailure(code, req.invocation_id, **values)


def success(req, finish=FinishReason.STOP):
    return LLMResponse(
        invocation_id=req.invocation_id,
        model_used=req.model,
        content=(TextContent(RESPONSE),),
        finish_reason=finish,
        usage=LLMUsage(7, 3, 10),
        latency_ms=17,
    )


def stream_success(req, *, finish=FinishReason.STOP, result=StreamOutcome.NORMAL):
    usage = LLMUsage(7, 3, 10)
    return [
        StreamStarted(req.invocation_id, req.model),
        *([TextDelta(req.invocation_id, RESPONSE)] if result is StreamOutcome.NORMAL else []),
        UsageUpdate(req.invocation_id, usage),
        StreamCompleted(
            LLMStreamCompletion(
                invocation_id=req.invocation_id,
                model_used=req.model,
                finish_reason=finish,
                outcome=result,
                usage=usage,
            )
        ),
    ]


def execute(gateway, clock=None, *, policy=None, records=None, **extra):
    clock = clock or VirtualTime()
    return ExecutingModelGateway(
        gateway,
        policy=policy,
        clock=clock.clock,
        sleep=clock.sleep,
        random_unit=lambda: 1.0,
        observer=None if records is None else records.append,
        **extra,
    )


@pytest.mark.parametrize(
    "code,status,dispatch",
    [
        (LLMErrorCode.RATE_LIMITED, 429, DispatchState.HTTP_RESPONSE_RECEIVED),
        (LLMErrorCode.PROVIDER_UNAVAILABLE, 500, DispatchState.HTTP_RESPONSE_RECEIVED),
        (LLMErrorCode.PROVIDER_UNAVAILABLE, 502, DispatchState.HTTP_RESPONSE_RECEIVED),
        (LLMErrorCode.PROVIDER_UNAVAILABLE, 503, DispatchState.HTTP_RESPONSE_RECEIVED),
        (LLMErrorCode.PROVIDER_UNAVAILABLE, 504, DispatchState.HTTP_RESPONSE_RECEIVED),
        (LLMErrorCode.TIMEOUT, 408, DispatchState.HTTP_RESPONSE_RECEIVED),
        (LLMErrorCode.TIMEOUT, None, DispatchState.NOT_DISPATCHED),
        (LLMErrorCode.PROVIDER_UNAVAILABLE, None, DispatchState.NOT_DISPATCHED),
    ],
)
def test_generate_retries_same_invocation_same_semantics(code, status, dispatch):
    req = request(structured_output=StructuredOutputRequest("small", {"type": "object"}))
    semantic_before = request_to_data(req)
    bad = failure(req, code, status, dispatch_state=dispatch)
    expected = success(req)
    g, clock, records = ScriptedGateway(bad, expected), VirtualTime(), []
    assert asyncio.run(execute(g, clock, records=records).generate(req)) is expected
    assert g.requests == [req, req] and all(attempt is req for attempt in g.requests)
    assert request_to_data(req) == semantic_before
    assert clock.waits == [0.5]
    assert [record.attempt_ordinal for record in records] == [1, 2]
    assert all(record.invocation_id == req.invocation_id for record in records)


@pytest.mark.parametrize(
    "code",
    [
        LLMErrorCode.AUTHENTICATION,
        LLMErrorCode.CONFIGURATION,
        LLMErrorCode.INVALID_REQUEST,
        LLMErrorCode.UNSUPPORTED_CAPABILITY,
        LLMErrorCode.CONTEXT_LIMIT,
        LLMErrorCode.MALFORMED_RESPONSE,
        LLMErrorCode.CANCELLED,
    ],
)
def test_permanent_failures_return_latest_failure_without_wait(code):
    req = request()
    bad = failure(req, code, 400)
    g, clock = ScriptedGateway(bad, success(req)), VirtualTime()
    with pytest.raises(LLMError) as error:
        asyncio.run(execute(g, clock).generate(req))
    assert error.value.failure is bad
    assert error.value.__context__ is None and error.value.__cause__ is None
    assert len(g.requests) == 1 and not clock.waits


@pytest.mark.parametrize(
    "code", [LLMErrorCode.TIMEOUT, LLMErrorCode.PROVIDER_UNAVAILABLE, LLMErrorCode.RATE_LIMITED]
)
def test_missing_or_ambiguous_dispatch_is_never_replayed(code):
    req, clock, records = request(), VirtualTime(), []
    bad = LLMFailure(code, req.invocation_id)
    assert bad.dispatch_state is DispatchState.DISPATCHED_OR_UNKNOWN
    g = ScriptedGateway(bad, success(req))
    with pytest.raises(LLMError):
        asyncio.run(execute(g, clock, records=records).generate(req))
    assert len(g.requests) == 1 and not clock.waits
    assert records[-1].decision.reason is RetryReason.AMBIGUOUS_DISPATCH_NOT_REPLAYED


@pytest.mark.parametrize("reason", list(StructuredFailureReason))
def test_completed_structured_failure_preserves_accounting_and_is_not_retried(reason):
    req = request()
    summary = LLMAttemptSummary(req.model, LLMUsage(7, 3, 10), FinishReason.STOP, 17)
    bad = failure(
        req,
        LLMErrorCode.STRUCTURED_OUTPUT_FAILED,
        200,
        attempt=summary,
        structured_detail=StructuredFailureDetail(reason),
    )
    g, clock = ScriptedGateway(bad, success(req)), VirtualTime()
    with pytest.raises(LLMError) as error:
        asyncio.run(execute(g, clock).generate(req))
    assert len(g.requests) == 1 and not clock.waits
    assert error.value.failure.attempt is summary


@pytest.mark.parametrize("finish", list(FinishReason))
def test_success_and_refusal_are_never_discarded(finish):
    req, clock = request(), VirtualTime()
    expected = success(req, finish)
    g = ScriptedGateway(expected, expected)
    assert asyncio.run(execute(g, clock).generate(req)) is expected
    assert len(g.requests) == 1 and not clock.waits


def test_attempt_limit_includes_first_and_preserves_last_failure():
    req, records = request(), []
    failures = [failure(req) for _ in range(4)]
    g, clock = ScriptedGateway(*failures), VirtualTime()
    with pytest.raises(LLMError) as error:
        asyncio.run(execute(g, clock, records=records).generate(req))
    assert error.value.failure is failures[2]
    assert len(g.requests) == 3 and clock.waits == [0.5, 1.0]
    assert records[-1].decision.reason is RetryReason.ATTEMPT_LIMIT_REACHED


@pytest.mark.parametrize("provider_delay", [1.0, 2.0, 999999999.0])
def test_retry_after_cannot_be_shortened_to_fit_elapsed_budget(provider_delay):
    req, records = request(), []
    g = ScriptedGateway(failure(req, retry_after_seconds=provider_delay), success(req))
    clock = VirtualTime()
    with pytest.raises(LLMError):
        asyncio.run(
            execute(
                g, clock, records=records, policy=RetryPolicy(max_elapsed_seconds=1.0)
            ).generate(req)
        )
    assert len(g.requests) == 1 and not clock.waits
    assert records[-1].decision.reason is RetryReason.RETRY_AFTER_EXCEEDS_BUDGET


def test_retry_after_is_minimum_not_additive_backoff():
    req = request()
    g = ScriptedGateway(failure(req, retry_after_seconds=4.0), failure(req), success(req))
    clock = VirtualTime()
    asyncio.run(execute(g, clock).generate(req))
    assert clock.waits == [4.0, 1.0]


def test_elapsed_budget_includes_attempt_duration():
    req, clock, records = request(), VirtualTime(), []

    class SlowAttempt(ScriptedGateway):
        async def generate(self, req):
            clock.value += 30.0
            return await super().generate(req)

    g = SlowAttempt(failure(req), success(req))
    with pytest.raises(LLMError):
        asyncio.run(execute(g, clock, records=records).generate(req))
    assert len(g.requests) == 1 and not clock.waits
    assert records[-1].decision.reason is RetryReason.ELAPSED_BUDGET_EXHAUSTED


@pytest.mark.parametrize("streaming", [False, True])
def test_scheduler_oversleep_prevents_next_dispatch(streaming):
    req, records, clock = request(streaming=streaming), [], VirtualTime()
    clock.oversleep = 30.0
    bad = failure(req)
    g = ScriptedGateway(
        *([[StreamFailed(bad)], stream_success(req)] if streaming else [bad, success(req)])
    )

    async def run():
        wrapper = execute(g, clock, records=records)
        if streaming:
            assert [event async for event in wrapper.stream(req)] == [StreamFailed(bad)]
        else:
            with pytest.raises(LLMError):
                await wrapper.generate(req)

    asyncio.run(run())
    assert len(g.requests) == 1
    assert records[-1].decision.reason is RetryReason.ELAPSED_BUDGET_EXHAUSTED


@pytest.mark.parametrize("streaming", [False, True])
def test_cancellation_during_backoff_propagates_and_does_not_dispatch(streaming):
    async def run():
        req = request(streaming=streaming)
        g = ScriptedGateway(
            *(
                [[StreamFailed(failure(req))], stream_success(req)]
                if streaming
                else [failure(req), success(req)]
            )
        )
        entered = asyncio.Event()

        async def sleep(_):
            entered.set()
            await asyncio.Event().wait()

        wrapper = ExecutingModelGateway(g, clock=lambda: 0.0, sleep=sleep, random_unit=lambda: 1)
        seen = []

        async def consume():
            if streaming:
                async for event in wrapper.stream(req):
                    seen.append(event)
            else:
                await wrapper.generate(req)

        task = asyncio.create_task(consume())
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert len(g.requests) == 1 and not seen
        if streaming:
            assert g.closed == [1]

    asyncio.run(run())


@pytest.mark.parametrize(
    "code,status,dispatch",
    [
        (LLMErrorCode.RATE_LIMITED, 429, DispatchState.HTTP_RESPONSE_RECEIVED),
        (LLMErrorCode.PROVIDER_UNAVAILABLE, 503, DispatchState.HTTP_RESPONSE_RECEIVED),
        (LLMErrorCode.PROVIDER_UNAVAILABLE, None, DispatchState.NOT_DISPATCHED),
    ],
)
def test_stream_prestart_retries_are_hidden_and_only_one_lifecycle_is_exposed(
    code, status, dispatch
):
    req = request(streaming=True)
    bad = failure(req, code, status, dispatch_state=dispatch)
    expected = stream_success(req)
    g, clock = ScriptedGateway([StreamFailed(bad)], expected), VirtualTime()
    events = asyncio.run(_consume(execute(g, clock), req))
    assert events == expected
    assert sum(isinstance(e, StreamStarted) for e in events) == 1
    assert sum(isinstance(e, StreamCompleted) for e in events) == 1
    assert not any(isinstance(e, StreamFailed) for e in events)
    assert events[-1].completion.usage == events[-2].usage == LLMUsage(7, 3, 10)
    assert g.closed == [1, 2] and all(r is req for r in g.requests)


async def _consume(wrapper, req):
    return [event async for event in wrapper.stream(req)]


def test_all_prestart_failures_expose_only_the_final_failed_event():
    req, clock = request(streaming=True), VirtualTime()
    failures = [failure(req) for _ in range(4)]
    g = ScriptedGateway(*([StreamFailed(bad)] for bad in failures))
    events = asyncio.run(_consume(execute(g, clock), req))
    assert events == [StreamFailed(failures[2])]
    assert len(g.requests) == 3 and g.closed == [1, 2, 3]


@pytest.mark.parametrize(
    "code",
    [
        LLMErrorCode.TIMEOUT,
        LLMErrorCode.PROVIDER_UNAVAILABLE,
        LLMErrorCode.MALFORMED_RESPONSE,
        LLMErrorCode.RATE_LIMITED,
    ],
)
@pytest.mark.parametrize("text_exposed", [False, True])
def test_started_stream_is_never_replayed_even_when_failure_would_otherwise_be_retryable(
    code,
    text_exposed,
):
    req, records, clock = request(streaming=True), [], VirtualTime()
    bad = failure(req, code, 429 if code is LLMErrorCode.RATE_LIMITED else 503)
    first = [StreamStarted(req.invocation_id, req.model)]
    if text_exposed:
        first.extend(
            [
                TextDelta(req.invocation_id, "partial"),
                UsageUpdate(req.invocation_id, LLMUsage(2, 1, 3)),
            ]
        )
    first.append(StreamFailed(bad))
    g = ScriptedGateway(first, stream_success(req))
    assert asyncio.run(_consume(execute(g, clock, records=records), req)) == first
    assert len(g.requests) == 1 and g.closed == [1] and not clock.waits
    assert records[-1].decision.reason is RetryReason.STARTED_STREAM_NOT_REPLAYABLE


@pytest.mark.parametrize("result", [StreamOutcome.REFUSAL, StreamOutcome.CONTENT_FILTERED])
def test_stream_refusal_filter_complete_without_retry(result):
    req, clock = request(streaming=True), VirtualTime()
    expected = stream_success(req, finish=FinishReason.REFUSAL, result=result)
    g = ScriptedGateway(expected, expected)
    assert asyncio.run(_consume(execute(g, clock), req)) == expected
    assert len(g.requests) == 1 and not clock.waits


@pytest.mark.parametrize("after_started", [False, True])
def test_cancelled_attempt_propagates_no_synthetic_terminal(after_started):
    req = request(streaming=True)
    first = [StreamStarted(req.invocation_id, req.model)] if after_started else []
    g = ScriptedGateway([*first, asyncio.CancelledError()], stream_success(req))
    seen = []

    async def run():
        async for event in execute(g).stream(req):
            seen.append(event)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(run())
    assert seen == first and len(g.requests) == 1 and g.closed == [1]


def test_abandoned_wrapper_stream_closes_underlying_attempt():
    req = request(streaming=True)
    g = ScriptedGateway(stream_success(req))

    async def run():
        async with aclosing(execute(g).stream(req)) as stream:
            assert isinstance(await anext(stream), StreamStarted)
            assert not g.closed

    asyncio.run(run())
    assert g.closed == [1] and len(g.requests) == 1


@pytest.mark.parametrize(
    "error_type,code,dispatch",
    [
        (httpx.PoolTimeout, LLMErrorCode.TIMEOUT, DispatchState.NOT_DISPATCHED),
        (httpx.ConnectTimeout, LLMErrorCode.TIMEOUT, DispatchState.NOT_DISPATCHED),
        (httpx.ConnectError, LLMErrorCode.PROVIDER_UNAVAILABLE, DispatchState.NOT_DISPATCHED),
        (httpx.ReadTimeout, LLMErrorCode.TIMEOUT, DispatchState.DISPATCHED_OR_UNKNOWN),
        (httpx.WriteTimeout, LLMErrorCode.TIMEOUT, DispatchState.DISPATCHED_OR_UNKNOWN),
        (httpx.ReadError, LLMErrorCode.PROVIDER_UNAVAILABLE, DispatchState.DISPATCHED_OR_UNKNOWN),
        (httpx.WriteError, LLMErrorCode.PROVIDER_UNAVAILABLE, DispatchState.DISPATCHED_OR_UNKNOWN),
        (
            httpx.RemoteProtocolError,
            LLMErrorCode.PROVIDER_UNAVAILABLE,
            DispatchState.DISPATCHED_OR_UNKNOWN,
        ),
    ],
)
@pytest.mark.parametrize("streaming", [False, True])
def test_direct_adapter_normalizes_transport_phase_without_retries(
    error_type, code, dispatch, streaming
):
    if streaming:
        wire = StreamWire(error=error_type)
        bad = asyncio.run(collect(wire))[-1].failure
    else:
        wire = Wire(error=error_type)
        with pytest.raises(LLMError) as error:
            asyncio.run(outcome(wire))
        bad = error.value.failure
    assert bad.code is code and bad.dispatch_state is dispatch
    assert bad.attempt is None and bad.http_status is None
    assert len(wire.requests) == 1


@pytest.mark.parametrize("streaming", [False, True])
def test_direct_adapter_normalizes_retry_after_and_preserves_http_status(streaming):
    if streaming:
        wire = StreamWire(status=429, headers={"retry-after": "4"})
        bad = asyncio.run(collect(wire))[-1].failure
    else:
        wire = Wire(status=429, headers={"retry-after": "4"})
        with pytest.raises(LLMError) as error:
            asyncio.run(outcome(wire))
        bad = error.value.failure
    assert bad.dispatch_state is DispatchState.HTTP_RESPONSE_RECEIVED
    assert bad.http_status == 429 and bad.retry_after_seconds == 4.0
    assert len(wire.requests) == 1 and bad.attempt is None


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, None),
        ("", None),
        ("nonsense", None),
        ("1.5", None),
        ("NaN", None),
        ("0", 0),
        (" 12 ", 12),
        ("-3", 0),
        ("Wed, 18 Sep 2024 12:00:04 GMT", 4),
        ("Wed, 18 Sep 2024 11:59:00 GMT", 0),
    ],
)
def test_retry_after_standard_forms_invalid_and_past(value, expected):
    assert _retry_after(value, now_utc=datetime(2024, 9, 18, 12, tzinfo=UTC)) == expected


def test_huge_valid_retry_after_never_becomes_an_early_replay():
    assert _retry_after("9" * 400) > RetryPolicy().max_elapsed_seconds
    assert _retry_after("-" + "9" * 400) == 0


@pytest.mark.parametrize(
    "error_type,retry", [(httpx.ConnectError, True), (httpx.ReadTimeout, False)]
)
@pytest.mark.parametrize("streaming", [False, True])
def test_real_adapter_orchestration_distinguishes_connect_failure_from_lost_response(
    error_type,
    retry,
    streaming,
):
    async def run():
        req, credentials, clock = request(streaming=streaming), Credentials(), VirtualTime()
        first = StreamWire(error=error_type) if streaming else Wire(error=error_type)
        second = StreamWire([normal(RESPONSE)]) if streaming else Wire()
        wires = [first, second]

        async def send(wire):
            return await wires.pop(0)(wire)

        async with OpenAICompatibleChatGateway(
            config(),
            credentials,
            transport=httpx.MockTransport(send),
            profile=ChatCompletionsProfile(supports_streaming=True),
        ) as adapter:
            wrapper = execute(adapter, clock)
            if streaming:
                events = await _consume(wrapper, req)
                assert isinstance(events[-1], StreamCompleted if retry else StreamFailed)
            elif retry:
                await wrapper.generate(req)
            else:
                with pytest.raises(LLMError):
                    await wrapper.generate(req)
        count = 2 if retry else 1
        assert len(credentials.calls) == count
        assert len(first.requests) + len(second.requests) == count
        assert all(
            "authorization" not in w.headers for part in (first, second) for w in part.requests
        )
        if retry:
            assert first.payloads == second.payloads

    asyncio.run(run())


@pytest.mark.parametrize("status", [429, 503])
@pytest.mark.parametrize("streaming", [False, True])
def test_real_explicit_http_failures_retry_with_fresh_credentials(status, streaming):
    async def run():
        req, clock, credentials = request(streaming=streaming), VirtualTime(), Credentials()
        first = (
            StreamWire(status=status, headers={"retry-after": "3"})
            if streaming
            else Wire(status=status, headers={"retry-after": "3"})
        )
        second = StreamWire([normal(RESPONSE)]) if streaming else Wire()
        wires = [first, second]

        async def send(wire):
            if len(wires) == 1:
                assert clock.waits == [3.0]
                assert "authorization" not in first.requests[0].headers
                if streaming:
                    assert first.body.closed
            return await wires.pop(0)(wire)

        async with OpenAICompatibleChatGateway(
            config(),
            credentials,
            transport=httpx.MockTransport(send),
            profile=ChatCompletionsProfile(supports_streaming=True),
        ) as adapter:
            wrapper = execute(adapter, clock)
            if streaming:
                events = await _consume(wrapper, req)
                assert isinstance(events[-1], StreamCompleted)
                assert sum(isinstance(e, StreamStarted) for e in events) == 1
                assert not any(isinstance(e, StreamFailed) for e in events)
            else:
                await wrapper.generate(req)
        assert len(credentials.calls) == 2 and first.payloads == second.payloads
        assert not any("attempt" in name or "invocation" in name for name in first.payloads[0])

    asyncio.run(run())


@pytest.mark.parametrize(
    "output,reason,finish",
    [
        ("not JSON", StructuredFailureReason.JSON_PARSE_FAILED, "stop"),
        ('{"x":"wrong"}', StructuredFailureReason.SCHEMA_VALIDATION_FAILED, "stop"),
        ('{"x":1}', StructuredFailureReason.OUTPUT_TRUNCATED, "length"),
        ("", StructuredFailureReason.EMPTY_OUTPUT, "stop"),
    ],
)
def test_real_structured_completion_failure_after_429_keeps_usage_and_stops(output, reason, finish):
    async def run():
        req = request(
            structured_output=StructuredOutputRequest(
                "small",
                {"type": "object", "properties": {"x": {"type": "integer"}}, "required": ["x"]},
            )
        )
        body = fixture()
        body["choices"][0]["message"]["content"] = output
        body["choices"][0]["finish_reason"] = finish
        first, second = Wire(status=429), Wire(body)
        wires = [first, second]

        async def send(wire):
            return await wires.pop(0)(wire)

        async with OpenAICompatibleChatGateway(
            config(),
            Credentials(),
            transport=httpx.MockTransport(send),
            profile=ChatCompletionsProfile(
                structured_output_mode=StructuredOutputMode.JSON_OBJECT_LOCAL_VALIDATE
            ),
        ) as adapter:
            with pytest.raises(LLMError) as error:
                await execute(adapter).generate(req)
        bad = error.value.failure
        assert bad.structured_detail.reason is reason
        assert bad.attempt.usage.input_tokens == body["usage"]["prompt_tokens"]
        assert bad.dispatch_state is DispatchState.HTTP_RESPONSE_RECEIVED and bad.http_status == 200
        assert len(first.requests) == len(second.requests) == 1

    asyncio.run(run())


@pytest.mark.parametrize("error_type", [httpx.ReadError, httpx.ReadTimeout])
@pytest.mark.parametrize("partial", [False, True])
def test_real_poststart_transport_failure_is_not_replayed(error_type, partial):
    async def run():
        req, clock = request(streaming=True), VirtualTime()
        from test_llm_streaming import chunk, sse

        wire = StreamWire([sse(chunk("partial"))] if partial else [], read_error=error_type)
        async with OpenAICompatibleChatGateway(
            config(),
            Credentials(),
            transport=httpx.MockTransport(wire),
            profile=ChatCompletionsProfile(supports_streaming=True),
        ) as adapter:
            events = await _consume(execute(adapter, clock), req)
        assert isinstance(events[0], StreamStarted) and isinstance(events[-1], StreamFailed)
        assert sum(isinstance(e, StreamFailed) for e in events) == 1
        assert not any(isinstance(e, StreamCompleted) for e in events)
        assert [e.text for e in events if isinstance(e, TextDelta)] == (
            ["partial"] if partial else []
        )
        assert events[-1].failure.dispatch_state is DispatchState.DISPATCHED_OR_UNKNOWN
        assert len(wire.requests) == 1 and not clock.waits and wire.body.closed

    asyncio.run(run())


def test_closed_retry_records_and_logs_do_not_expand_content_or_provider_failures():
    async def run():
        log, records, clock = StringIO(), [], VirtualTime()
        logger = StructuredLogger(log)
        req = request()
        first = Wire(
            {"error": {"message": RAW + CANARY + PROMPT}},
            status=429,
            headers={"x-request-id": CANARY, "retry-after": "2"},
        )
        second = Wire()
        wires = [first, second]

        async def send(wire):
            return await wires.pop(0)(wire)

        def observe(record):
            records.append(record)
            logger.emit(
                "llm_execution",
                record.decision.reason.value,
                trace_id=str(record.invocation_id.value),
            )

        async with OpenAICompatibleChatGateway(
            config(),
            Credentials(),
            transport=httpx.MockTransport(send),
            logger=logger,
        ) as adapter:
            wrapper = ExecutingModelGateway(
                adapter,
                clock=clock.clock,
                sleep=clock.sleep,
                random_unit=lambda: 1,
                observer=observe,
            )
            await wrapper.generate(req)
        serialized = (
            repr(records) + json.dumps([asdict(r) for r in records], default=str) + log.getvalue()
        )
        for canary in (CANARY, PROMPT, RESPONSE, REASONING, RAW):
            assert canary not in serialized
        assert [r.attempt_ordinal for r in records] == [1, 2]

    asyncio.run(run())


@pytest.mark.parametrize(
    "category,code,status,dispatch",
    [
        ("retry_rate_limits", LLMErrorCode.RATE_LIMITED, 429, DispatchState.HTTP_RESPONSE_RECEIVED),
        (
            "retry_transient_http",
            LLMErrorCode.PROVIDER_UNAVAILABLE,
            503,
            DispatchState.HTTP_RESPONSE_RECEIVED,
        ),
        ("retry_not_dispatched", LLMErrorCode.TIMEOUT, None, DispatchState.NOT_DISPATCHED),
        ("retry_http_timeouts", LLMErrorCode.TIMEOUT, 408, DispatchState.HTTP_RESPONSE_RECEIVED),
    ],
)
def test_transient_categories_can_be_disabled(category, code, status, dispatch):
    req, clock = request(), VirtualTime()
    g = ScriptedGateway(failure(req, code, status, dispatch_state=dispatch), success(req))
    with pytest.raises(LLMError):
        asyncio.run(execute(g, clock, policy=RetryPolicy(**{category: False})).generate(req))
    assert len(g.requests) == 1 and not clock.waits


def test_full_jitter_exponential_cap_remaining_budget_and_large_ordinal():
    policy = RetryPolicy(initial_backoff_seconds=2, max_backoff_seconds=5)
    strategy = ExponentialBackoff(lambda: 0.25)
    assert [strategy.delay(policy, n, 30) for n in (1, 2, 3, 999999)] == [0.5, 1, 1.25, 1.25]
    assert strategy.delay(policy, 3, 1) == 0.25
    assert ExponentialBackoff(lambda: 0).delay(policy, 1, 30) == 0
    assert ExponentialBackoff(lambda: 1).delay(policy, 1, 30) == 2
    assert strategy.delay(replace(policy, jitter=JitterStrategy.NONE), 2, 30) == 4
    with pytest.raises(FrozenInstanceError):
        policy.max_attempts = 999


@pytest.mark.parametrize(
    "change",
    [
        {"max_attempts": 0},
        {"max_attempts": True},
        {"max_elapsed_seconds": float("inf")},
        {"initial_backoff_seconds": float("nan")},
        {"max_backoff_seconds": -1},
        {"max_backoff_seconds": 0.1},
        {"max_elapsed_seconds": 0},
        {"jitter": "full"},
        {"retry_rate_limits": 1},
    ],
)
def test_retry_policy_rejects_unbounded_or_invalid_values(change):
    with pytest.raises(LLMContractError):
        RetryPolicy(**change)


@pytest.mark.parametrize(
    "change",
    [
        {"dispatch_state": "not_dispatched"},
        {"http_status": True},
        {"http_status": 999},
        {"retry_after_seconds": float("inf")},
        {"retry_after_seconds": -1},
        {"dispatch_state": DispatchState.NOT_DISPATCHED, "http_status": 429},
        {
            "dispatch_state": DispatchState.NOT_DISPATCHED,
            "http_status": None,
            "retry_after_seconds": 2,
        },
    ],
)
def test_failure_metadata_is_typed_finite_and_coherent(change):
    with pytest.raises(LLMContractError):
        failure(request(), **change)


@pytest.mark.parametrize("status", [501, 505, 599, None])
def test_http_status_without_known_transient_semantics_does_not_retry(status):
    decision = decide_retry(
        failure(request(), LLMErrorCode.PROVIDER_UNAVAILABLE, status),
        attempt_ordinal=1,
        elapsed_seconds=0,
        policy=RetryPolicy(),
        backoff=ExponentialBackoff(lambda: 1),
    )
    assert not decision.retry and decision.reason is RetryReason.PERMANENT_FAILURE
