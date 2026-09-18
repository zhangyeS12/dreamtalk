"""Controlled, genuinely progressive SSE transport and content-free terminal invariants."""

import asyncio
import json
from collections.abc import Mapping
from dataclasses import FrozenInstanceError, fields, is_dataclass, replace
from io import StringIO
from pathlib import Path

import httpx
import pytest
from livingworld.application.llm import (
    FinishReason,
    LLMContractError,
    LLMErrorCode,
    LLMStreamCompletion,
    LLMUsage,
    ProviderDiagnostics,
    StreamCompleted,
    StreamFailed,
    StreamOutcome,
    StreamStarted,
    StructuredOutputRequest,
    TextDelta,
    UsageUpdate,
)
from livingworld.infrastructure.llm.fake import FakeModelGateway
from livingworld.infrastructure.llm.openai_compatible import (
    ChatCompletionsProfile,
    OpenAICompatibleChatGateway,
)
from livingworld.infrastructure.llm.sse import SSEDecoder, SSEProtocolError, StreamLimits
from livingworld.infrastructure.logging import StructuredLogger
from test_openai_compatible import CANARY, PROMPT, Credentials, config, request

OUTPUT = "LW_STREAM_OUTPUT_CANARY"
REASONING = "LW_STREAM_REASONING_CANARY"
RAW = "LW_STREAM_RAW_ERROR_CANARY"
PROFILE = ChatCompletionsProfile(supports_streaming=True, supports_stream_usage=True)


def chunk(text=None, *, finish=None, delta=None, usage=None, choices=None, **extra):
    return {
        "id": "chatcmpl-controlled-stream",
        "object": "chat.completion.chunk",
        "model": "controlled-model",
        "choices": choices
        if choices is not None
        else [
            {
                "index": 0,
                "delta": {"content": text} if delta is None else delta,
                "finish_reason": finish,
            }
        ],
        "usage": usage,
        **extra,
    }


def sse(*values, newline="\n"):
    return "".join(
        "data: "
        + (value if type(value) is str else json.dumps(value, ensure_ascii=False))
        + newline * 2
        for value in values
    ).encode("utf-8")


def normal(*texts, usage=None):
    return sse(
        chunk(delta={"role": "assistant", "content": ""}),
        *(chunk(text) for text in texts),
        chunk(finish="stop", delta={}, usage=usage),
        "[DONE]",
    )


class Bytes(httpx.AsyncByteStream):
    def __init__(self, fragments, *, error=None, gate=None):
        self.fragments = fragments
        self.error, self.gate = error, gate
        self.reads = 0
        self.closed = False

    async def __aiter__(self):
        for fragment in self.fragments:
            self.reads += 1
            await asyncio.sleep(0)
            yield fragment
        if self.gate is not None:
            await self.gate.wait()
        if self.error is not None:
            raise self.error(CANARY + RAW)

    async def aclose(self):
        self.closed = True


class Wire:
    def __init__(
        self, fragments=(), *, status=200, headers=None, error=None, read_error=None, gate=None
    ):
        self.body = Bytes(fragments, error=read_error, gate=gate)
        self.status, self.error = status, error
        self.headers = (
            {"content-type": "text/event-stream", "x-request-id": "req-controlled-stream"}
            if headers is None
            else headers
        )
        self.requests, self.payloads, self.responses = [], [], []

    async def __call__(self, wire):
        assert wire.headers["authorization"] == "Bearer " + CANARY
        assert wire.headers["accept"] == "text/event-stream"
        assert "cookie" not in wire.headers
        self.requests.append(wire)
        self.payloads.append(json.loads(wire.content))
        if self.error is not None:
            raise self.error(CANARY + RAW, request=wire)
        response = httpx.Response(self.status, stream=self.body, headers=self.headers)
        self.responses.append(response)
        return response


def gateway(wire, *, creds=None, profile=PROFILE, logger=None, limits=None, cfg=None):
    return OpenAICompatibleChatGateway(
        cfg or config(),
        creds or Credentials(),
        profile=profile,
        transport=httpx.MockTransport(wire),
        logger=logger,
        stream_limits=limits,
    )


async def collect(wire, *, req=None, **options):
    async with gateway(wire, **options) as g:
        events = [event async for event in g.stream(req or request(streaming=True))]
        assert not g._client.cookies
    assert len(wire.requests) <= 1
    assert all("authorization" not in wire.headers for wire in wire.requests)
    assert all(response.is_closed for response in wire.responses)
    return events


def completed(events):
    assert isinstance(events[0], StreamStarted)
    assert sum(isinstance(event, StreamStarted) for event in events) == 1
    assert sum(isinstance(event, StreamCompleted) for event in events) == 1
    assert not any(isinstance(event, StreamFailed) for event in events)
    assert isinstance(events[-1], StreamCompleted)
    return events[-1].completion


def failed(events, code, *, started=True):
    assert isinstance(events[-1], StreamFailed)
    assert events[-1].failure.code is code
    assert events[-1].failure.attempt is None
    assert sum(isinstance(event, StreamFailed) for event in events) == 1
    assert sum(isinstance(event, StreamStarted) for event in events) == int(started)
    assert not any(isinstance(event, StreamCompleted) for event in events)
    if not started:
        assert len(events) == 1


def serialized(value):
    """Deliberately includes repr-hidden fields; metadata must still be safe."""
    if is_dataclass(value):
        return {field.name: serialized(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {key: serialized(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [serialized(item) for item in value]
    return str(value)


@pytest.mark.parametrize("name", ["openai_stream", "deepseek_stream"])
@pytest.mark.parametrize("fragment_size", [1, 2, 7, 127, None])
def test_official_shape_fixtures_preserve_order_across_arbitrary_boundaries(name, fragment_size):
    data = (Path(__file__).parent / f"fixtures/llm/{name}.sse").read_bytes()
    fragments = (
        [data]
        if fragment_size is None
        else [data[i : i + fragment_size] for i in range(0, len(data), fragment_size)]
    )
    wire = Wire(fragments)
    events = asyncio.run(collect(wire))
    result = completed(events)
    assert [event.text for event in events if isinstance(event, TextDelta)] == [
        "Hel",
        "lo",
        " ",
        "世界",
    ]
    assert result.model_used.model_id == "controlled-model"
    assert result.finish_reason is FinishReason.STOP
    assert result.usage == LLMUsage(
        12, 4, 16, {"completion_tokens_details": {"reasoning_tokens": 2}}
    )
    assert result.latency_ms >= 0
    assert result.diagnostics.provider_request_id == "req-controlled-stream"
    assert len([event for event in events if isinstance(event, UsageUpdate)]) == 1
    assert REASONING not in str(serialized(events))
    assert wire.payloads[0]["stream"] is True


@pytest.mark.parametrize("include_usage", [False, True])
def test_profile_controls_wire_usage_options_and_capabilities(include_usage):
    async def run():
        wire = Wire([normal("one")])
        creds = Credentials()
        profile = ChatCompletionsProfile(
            supports_n=True, supports_streaming=True, supports_stream_usage=include_usage
        )
        req = request(streaming=True)
        async with gateway(wire, creds=creds, profile=profile) as g:
            assert g.capabilities.streaming is True
            completed([event async for event in g.stream(req)])
        assert creds.calls == [g._config.secret_ref]
        assert wire.payloads == [
            {
                "model": req.model.model_id,
                "messages": [
                    {
                        "role": message.role.value,
                        "content": "".join(b.text for b in message.content),
                    }
                    for message in req.messages
                ],
                "max_tokens": 64,
                "stream": True,
                "stop": ["<END>", "\nSTOP"],
                "n": 1,
                **({"stream_options": {"include_usage": True}} if include_usage else {}),
            }
        ]
        assert "authorization" not in wire.requests[0].headers

    asyncio.run(run())


@pytest.mark.parametrize(
    "case", ["unsupported", "structured", "nonstream", "wrong_provider", "too_many_stops"]
)
def test_preflight_returns_one_failure_without_credentials_or_network(case):
    async def run():
        wire, creds = Wire(), Credentials()
        req = request(streaming=True)
        profile = PROFILE
        code = LLMErrorCode.UNSUPPORTED_CAPABILITY
        if case == "unsupported":
            profile = ChatCompletionsProfile()
        elif case == "structured":
            req = replace(req, structured_output=StructuredOutputRequest("x", {"type": "object"}))
        elif case == "nonstream":
            req, code = replace(req, streaming=False), LLMErrorCode.INVALID_REQUEST
        elif case == "wrong_provider":
            req, code = (
                replace(
                    req, model=replace(req.model, provider_id=type(req.model.provider_id)("other"))
                ),
                LLMErrorCode.CONFIGURATION,
            )
        else:
            req = replace(req, stop_sequences=("1", "2", "3", "4", "5"))
        failed(await collect(wire, req=req, creds=creds, profile=profile), code, started=False)
        assert not wire.requests and not creds.calls

    asyncio.run(run())


@pytest.mark.parametrize(
    "changes",
    [{"supports_streaming": 1}, {"supports_stream_usage": 1}, {"supports_stream_usage": True}],
)
def test_profile_flags_are_typed_consistent_and_immutable(changes):
    with pytest.raises(LLMContractError):
        ChatCompletionsProfile(**changes)
    with pytest.raises(FrozenInstanceError):
        PROFILE.supports_streaming = False


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_multiline_data_comments_empty_role_and_null_content(newline):
    data = (
        ": keep-alive"
        + newline
        + newline
        + "event: ignored"
        + newline
        + "id: ignored"
        + newline
        + "retry: 123"
        + newline
    ).encode()
    data += sse(
        chunk(delta={"role": "assistant"}),
        chunk(delta={"content": None}),
        chunk(delta={"content": ""}),
        newline=newline,
    )
    pretty = json.dumps(chunk(" exact  \t"), ensure_ascii=False, indent=2)
    data += (newline.join("data: " + line for line in pretty.splitlines()) + newline * 2).encode()
    data += sse(chunk(finish="stop", delta={}), "[DONE]", newline=newline)
    events = asyncio.run(collect(Wire([bytes([byte]) for byte in data])))
    assert [event.text for event in events if isinstance(event, TextDelta)] == [" exact  \t"]
    assert completed(events).usage is None


@pytest.mark.parametrize("usage_only", [False, True])
def test_usage_snapshots_are_factual_ordered_deduplicated_and_not_added(usage_only):
    snapshots = [
        {"prompt_tokens": 12, "completion_tokens": count, "total_tokens": 12 + count}
        for count in (5, 3, 7)
    ]
    chunks = [chunk(OUTPUT)]
    for snapshot in (snapshots[0], snapshots[0], snapshots[1], snapshots[2]):
        chunks.append(chunk(delta={}, usage=snapshot, choices=[] if usage_only else None))
    chunks.extend([chunk(finish="stop", delta={}), "[DONE]"])
    events = asyncio.run(collect(Wire([sse(*chunks)])))
    updates = [event.usage for event in events if isinstance(event, UsageUpdate)]
    assert [value.output_tokens for value in updates] == [5, 3, 7]
    assert completed(events).usage == updates[-1] == LLMUsage(12, 7, 19)


def test_unreported_counters_and_unknown_metadata_are_never_fabricated_or_copied():
    data = sse(
        chunk(
            OUTPUT,
            usage={
                "prompt_tokens": 3,
                "private": RAW,
                "completion_tokens_details": {"reasoning_tokens": 2, "private": REASONING},
            },
        ),
        chunk(finish="stop", delta={}),
        "[DONE]",
    )
    events = asyncio.run(collect(Wire([data])))
    assert completed(events).usage == LLMUsage(
        3, None, None, {"completion_tokens_details": {"reasoning_tokens": 2}}
    )
    assert RAW not in str(serialized(events)) and REASONING not in str(serialized(events))


@pytest.mark.parametrize("finish", ["stop", "length", "future_code"])
def test_finish_semantics_and_no_events_after_done(finish):
    data = sse(
        chunk(OUTPUT), chunk(finish=finish, delta={}), "[DONE]", "not JSON", chunk("after terminal")
    )
    events = asyncio.run(collect(Wire([data])))
    result = completed(events)
    assert result.finish_reason is {
        "stop": FinishReason.STOP,
        "length": FinishReason.OUTPUT_LIMIT,
    }.get(finish, FinishReason.UNKNOWN)
    assert [event.text for event in events if isinstance(event, TextDelta)] == [OUTPUT]
    assert OUTPUT not in str(serialized(result))


@pytest.mark.parametrize("kind", ["refusal_delta", "refusal_finish", "content_filter"])
def test_explicit_refusal_and_filter_are_content_free_successful_terminals(kind):
    first = (
        chunk(delta={"refusal": OUTPUT, "content": "suppressed"})
        if kind == "refusal_delta"
        else chunk(delta={})
    )
    finish = {
        "refusal_delta": "stop",
        "refusal_finish": "refusal",
        "content_filter": "content_filter",
    }[kind]
    events = asyncio.run(collect(Wire([sse(first, chunk(finish=finish, delta={}), "[DONE]")])))
    result = completed(events)
    assert result.finish_reason is FinishReason.REFUSAL
    assert result.outcome is (
        StreamOutcome.CONTENT_FILTERED if kind == "content_filter" else StreamOutcome.REFUSAL
    )
    assert not any(isinstance(event, TextDelta) for event in events)
    assert OUTPUT not in str(serialized(result))


def test_ordinary_refusal_sounding_text_is_still_visible_content():
    text = "I cannot help with that."
    events = asyncio.run(collect(Wire([normal(text)])))
    assert completed(events).outcome is StreamOutcome.NORMAL
    assert [event.text for event in events if isinstance(event, TextDelta)] == [text]


@pytest.mark.parametrize(
    "delta",
    [
        {"tool_calls": [{"index": 0, "function": {"arguments": RAW}}]},
        {"function_call": {"arguments": RAW}},
    ],
)
def test_tool_call_data_never_becomes_text_or_execution(delta):
    events = asyncio.run(collect(Wire([sse(chunk(delta=delta), "[DONE]")])))
    failed(events, LLMErrorCode.UNSUPPORTED_CAPABILITY)
    assert not any(isinstance(event, TextDelta) for event in events)
    assert RAW not in str(serialized(events))


def test_extra_choices_are_not_merged_and_index_zero_need_not_be_first():
    choices = [
        {"index": 2, "delta": {"content": RAW}, "finish_reason": None},
        {"index": 0, "delta": {"content": OUTPUT}, "finish_reason": None},
    ]
    events = asyncio.run(
        collect(Wire([sse(chunk(choices=choices), chunk(finish="stop", delta={}), "[DONE]")]))
    )
    completed(events)
    assert [event.text for event in events if isinstance(event, TextDelta)] == [OUTPUT]
    assert RAW not in str(serialized(events))


@pytest.mark.parametrize(
    "bad",
    [
        "not JSON " + RAW,
        "[]",
        '{"duplicate":0,"duplicate":1}',
        chunk(choices="bad"),
        chunk(choices=[]),
        chunk(choices=[{"index": 2, "delta": {}}]),
        chunk(choices=[{"index": False, "delta": {}}]),
        chunk(choices=[{"index": 0, "delta": {}, "finish_reason": 3}]),
        chunk(choices=[{"index": 0, "delta": {}}] * 2),
        chunk(delta="bad"),
        chunk(delta={"role": "user"}),
        chunk(delta={"content": [RAW]}),
        chunk(delta={"refusal": 3}),
        chunk(usage="bad"),
        chunk(usage={"total_tokens": True}),
        chunk(usage={"completion_tokens": -1}),
        chunk(usage={"prompt_tokens_details": []}),
        chunk(object="wrong"),
        chunk(model=""),
        chunk(model=CANARY),
        chunk(model=PROMPT),
        chunk(model="\ud800"),
        chunk(delta={"content": "\ud800"}),
        chunk(choices=[{"index": 0, "delta": {}, "finish_reason": "   "}]),
    ],
)
def test_malformed_json_and_shapes_fail_closed_without_raw_diagnostics(bad):
    # Escaped lone surrogates deliberately test JSON string validity at the boundary.
    data = sse(json.dumps(bad) if type(bad) is dict else bad, "[DONE]")
    events = asyncio.run(collect(Wire([data])))
    failed(events, LLMErrorCode.MALFORMED_RESPONSE)
    assert RAW not in str(serialized(events)) and CANARY not in repr(events)


@pytest.mark.parametrize(
    "data",
    [
        sse(chunk(OUTPUT)),
        sse(chunk(OUTPUT), "[DONE]"),
        sse("[DONE]"),
        b"data: " + b"\xff\n\n",
        sse(chunk(finish="stop", delta={})),
    ],
)
def test_eof_missing_finish_and_invalid_utf8_never_complete(data):
    events = asyncio.run(collect(Wire([data])))
    failed(events, LLMErrorCode.MALFORMED_RESPONSE)


@pytest.mark.parametrize("case", ["new_text_after_finish", "changed_model", "conflicting_finish"])
def test_incoherent_terminal_sequence_fails(case):
    values = [chunk(OUTPUT), chunk(finish="stop", delta={})]
    values.append(
        {
            "new_text_after_finish": chunk("later"),
            "changed_model": chunk(delta={}, model="other"),
            "conflicting_finish": chunk(finish="length", delta={}),
        }[case]
    )
    failed(asyncio.run(collect(Wire([sse(*values, "[DONE]")]))), LLMErrorCode.MALFORMED_RESPONSE)


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (401, LLMErrorCode.AUTHENTICATION),
        (403, LLMErrorCode.AUTHENTICATION),
        (429, LLMErrorCode.RATE_LIMITED),
        (408, LLMErrorCode.TIMEOUT),
        (500, LLMErrorCode.PROVIDER_UNAVAILABLE),
        (503, LLMErrorCode.PROVIDER_UNAVAILABLE),
        (400, LLMErrorCode.INVALID_REQUEST),
        (422, LLMErrorCode.INVALID_REQUEST),
        (302, LLMErrorCode.CONFIGURATION),
    ],
)
def test_http_failure_reuses_normalization_before_started_with_one_attempt(status, code):
    wire = Wire([json.dumps({"error": {"message": RAW + CANARY}}).encode()], status=status)
    events = asyncio.run(collect(wire))
    failed(events, code, started=False)
    assert len(wire.requests) == 1
    assert RAW not in str(serialized(events))


def test_context_limit_error_uses_structured_code_and_error_body_is_bounded():
    wire = Wire([b'{"error":{"code":"context_length_exceeded"}}'], status=400)
    failed(asyncio.run(collect(wire)), LLMErrorCode.CONTEXT_LIMIT, started=False)
    wire = Wire([b"x" * 1024, b"never read"], status=401)
    failed(
        asyncio.run(collect(wire, limits=StreamLimits(max_error_body_bytes=64))),
        LLMErrorCode.AUTHENTICATION,
        started=False,
    )
    assert wire.body.reads == 1


@pytest.mark.parametrize("error", [httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout])
def test_prestart_transport_errors_are_normalized_without_started_or_retry(error):
    wire = Wire(error=error)
    code = (
        LLMErrorCode.TIMEOUT
        if issubclass(error, httpx.TimeoutException)
        else LLMErrorCode.PROVIDER_UNAVAILABLE
    )
    failed(asyncio.run(collect(wire)), code, started=False)
    assert len(wire.requests) == 1


@pytest.mark.parametrize("error", [httpx.ReadError, httpx.RemoteProtocolError, httpx.ReadTimeout])
def test_partial_disconnect_retains_observed_usage_but_has_no_completed_attempt(error):
    wire = Wire([sse(chunk(OUTPUT, usage={"completion_tokens": 7}))], read_error=error)
    events = asyncio.run(collect(wire))
    failed(
        events,
        LLMErrorCode.TIMEOUT if error is httpx.ReadTimeout else LLMErrorCode.PROVIDER_UNAVAILABLE,
    )
    assert [event.text for event in events if isinstance(event, TextDelta)] == [OUTPUT]
    assert [event.usage for event in events if isinstance(event, UsageUpdate)] == [
        LLMUsage(output_tokens=7)
    ]
    assert len(wire.requests) == 1


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"content-type": "application/json"},
        {"content-type": "text/event-stream; charset=latin1"},
    ],
)
def test_started_requires_acceptable_stream_content_type(headers):
    failed(
        asyncio.run(collect(Wire([normal(OUTPUT)], headers=headers))),
        LLMErrorCode.MALFORMED_RESPONSE,
        started=False,
    )


@pytest.mark.parametrize(
    "limits", [StreamLimits(max_line_bytes=16), StreamLimits(max_event_bytes=16)]
)
def test_oversized_sse_fails_with_bounded_parser_limits(limits):
    data = (
        b"data: " + b"x" * 17 + b"\n\n"
        if limits.max_line_bytes == 16
        else b"data: abcdefgh\ndata: ijklmnop\n\n"
    )
    failed(asyncio.run(collect(Wire([data]), limits=limits)), LLMErrorCode.MALFORMED_RESPONSE)


def test_decoder_limits_are_central_typed_and_invalid_utf8_never_leaks_bytes():
    for changes in ({"max_event_bytes": 0}, {"max_line_bytes": True}, {"max_model_bytes": -1}):
        with pytest.raises(ValueError, match="invalid_stream_limits"):
            StreamLimits(**changes)
    with pytest.raises(SSEProtocolError) as error:
        list(SSEDecoder(StreamLimits()).feed(b"data: \xff\n\n"))
    assert str(error.value) == "sse_invalid_utf8" and "\\xff" not in str(error.value)


def test_slow_consumer_has_no_eager_reader_and_terminal_closes_before_delivery(monkeypatch):
    async def run():
        def forbidden(*args, **kwargs):
            raise AssertionError("full response/response parser is forbidden during streaming")

        import livingworld.infrastructure.llm.openai_compatible as adapter

        monkeypatch.setattr(adapter, "LLMResponse", forbidden)
        monkeypatch.setattr(adapter, "_response", forbidden)
        monkeypatch.setattr(OpenAICompatibleChatGateway, "generate", forbidden)
        wire = Wire(
            [sse(chunk(OUTPUT)), sse(chunk(" two")), sse(chunk(finish="stop", delta={}), "[DONE]")]
        )
        async with gateway(wire) as g:
            iterator = g.stream(request(streaming=True))
            assert isinstance(await anext(iterator), StreamStarted)
            assert wire.body.reads == 0
            assert (await anext(iterator)).text == OUTPUT
            await asyncio.sleep(0)
            assert wire.body.reads == 1 and not wire.body.closed
            assert (await anext(iterator)).text == " two"
            terminal = await anext(iterator)
            assert isinstance(terminal, StreamCompleted) and wire.body.closed
            assert not hasattr(wire.responses[0], "_content")
            assert "authorization" not in wire.requests[0].headers
            assert OUTPUT not in str(serialized(terminal))
            with pytest.raises(StopAsyncIteration):
                await anext(iterator)

    asyncio.run(run())


def test_same_fragment_backpressure_does_not_parse_ahead_into_later_error():
    async def run():
        wire = Wire([sse(chunk(OUTPUT), "malformed " + RAW)])
        async with gateway(wire) as g:
            iterator = g.stream(request(streaming=True))
            assert isinstance(await anext(iterator), StreamStarted)
            assert (await anext(iterator)).text == OUTPUT
            assert not wire.body.closed
            failure = await anext(iterator)
            assert isinstance(failure, StreamFailed) and wire.body.closed
            with pytest.raises(StopAsyncIteration):
                await anext(iterator)

    asyncio.run(run())


def test_cancellation_during_read_propagates_and_closes_without_terminal():
    async def run():
        wire = Wire([sse(chunk(OUTPUT))], gate=asyncio.Event())
        async with gateway(wire) as g:
            iterator = g.stream(request(streaming=True))
            events = [await anext(iterator), await anext(iterator)]
            task = asyncio.create_task(anext(iterator))
            await asyncio.sleep(0)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert wire.body.closed and "authorization" not in wire.requests[0].headers
            assert not any(isinstance(event, (StreamCompleted, StreamFailed)) for event in events)
            with pytest.raises(StopAsyncIteration):
                await anext(iterator)

    asyncio.run(run())


@pytest.mark.parametrize("after_text", [False, True])
def test_explicit_early_iterator_close_and_context_managed_exit_release_response(after_text):
    async def run():
        from contextlib import aclosing

        wire = Wire([sse(chunk(OUTPUT))], gate=asyncio.Event())
        async with gateway(wire) as g:
            async with aclosing(g.stream(request(streaming=True))) as iterator:
                assert isinstance(await anext(iterator), StreamStarted)
                if after_text:
                    assert (await anext(iterator)).text == OUTPUT
            assert wire.body.closed and "authorization" not in wire.requests[0].headers
            with pytest.raises(StopAsyncIteration):
                await anext(iterator)

    asyncio.run(run())


def test_credentials_are_late_resolved_and_released_on_credential_failure_and_cancel():
    async def run():
        creds = Credentials(error=RuntimeError(CANARY + RAW))
        wire = Wire()
        failed(await collect(wire, creds=creds), LLMErrorCode.AUTHENTICATION, started=False)
        assert not wire.requests

        class PendingCredentials:
            async def resolve(self, reference):
                await asyncio.Event().wait()

        async with gateway(Wire(), creds=PendingCredentials()) as g:
            iterator = g.stream(request(streaming=True))
            task = asyncio.create_task(anext(iterator))
            await asyncio.sleep(0)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    asyncio.run(run())


def test_stream_events_diagnostics_and_logs_do_not_expose_private_canaries(caplog):
    log = StringIO()
    wire = Wire(
        [
            sse(
                chunk(OUTPUT, delta={"content": OUTPUT, "reasoning_content": REASONING}),
                chunk(finish="stop", delta={}),
                "[DONE]",
            )
        ],
        headers={"content-type": "text/event-stream; charset=utf-8", "x-request-id": CANARY},
    )
    events = asyncio.run(collect(wire, logger=StructuredLogger(log)))
    result = completed(events)
    assert result.diagnostics.provider_request_id == "chatcmpl-controlled-stream"
    assert OUTPUT in str(serialized([e for e in events if isinstance(e, TextDelta)]))
    terminal = json.dumps(serialized(result)) + repr(result)
    for canary in (CANARY, PROMPT, OUTPUT, REASONING, RAW):
        assert canary not in terminal and canary not in log.getvalue() + caplog.text
    bad = Wire([b"data: " + (CANARY + RAW + PROMPT).encode() + b"\n\n"])
    events = asyncio.run(collect(bad, logger=StructuredLogger(log)))
    failed(events, LLMErrorCode.MALFORMED_RESPONSE)
    for canary in (CANARY, RAW, PROMPT):
        assert canary not in str(serialized(events)) + log.getvalue()


def test_completion_type_is_immutable_content_free_and_usage_metadata_is_closed():
    req = request()
    result = LLMStreamCompletion(
        invocation_id=req.invocation_id,
        model_used=req.model,
        finish_reason=FinishReason.STOP,
        usage=LLMUsage(1, 2, 3, {"raw": RAW, "prompt": PROMPT, "output": OUTPUT}),
    )
    assert result.usage == LLMUsage(1, 2, 3)
    assert not {
        "content",
        "text",
        "messages",
        "structured_result",
        "reasoning_content",
        "headers",
        "response",
        "raw_sse",
    } & {f.name for f in fields(result)}
    with pytest.raises(FrozenInstanceError):
        result.finish_reason = FinishReason.UNKNOWN
    with pytest.raises(LLMContractError):
        StreamCompleted(object())
    with pytest.raises(LLMContractError):
        replace(result, diagnostics=ProviderDiagnostics(diagnostic_code=RAW))
    with pytest.raises(LLMContractError):
        replace(result, diagnostics=ProviderDiagnostics(provider_request_id="x" * 129))
    with pytest.raises(LLMContractError):
        replace(result, outcome=StreamOutcome.REFUSAL)
    assert not any(value in str(serialized(result)) for value in (RAW, PROMPT, OUTPUT))


def test_fake_uses_identical_content_free_stream_contract_without_building_response(monkeypatch):
    async def run():
        req = request()
        fake = FakeModelGateway(chunks=(OUTPUT, "", " two"), usage=LLMUsage(1, 2, 3))
        response = await fake.generate(req)
        assert response.text == OUTPUT + " two"

        def forbidden(*args):
            raise AssertionError("stream must not construct a full response")

        monkeypatch.setattr(FakeModelGateway, "_response", forbidden)
        events = [event async for event in fake.stream(replace(req, streaming=True))]
        result = completed(events)
        assert [event.text for event in events if isinstance(event, TextDelta)] == [OUTPUT, " two"]
        assert result.usage == response.usage and OUTPUT not in str(serialized(result))
        events = [
            event
            async for event in FakeModelGateway(
                chunks=(OUTPUT,), finish_reason=FinishReason.REFUSAL
            ).stream(replace(req, streaming=True))
        ]
        assert completed(events).outcome is StreamOutcome.REFUSAL
        assert not any(isinstance(event, TextDelta) for event in events)

    asyncio.run(run())


def test_many_deltas_do_not_accumulate_an_answer_in_adapter_memory():
    import tracemalloc

    async def run():
        class GeneratedBytes(httpx.AsyncByteStream):
            async def __aiter__(self):
                for _ in range(600):
                    yield sse(chunk("x" * 4096))
                yield sse(chunk(finish="stop", delta={}), "[DONE]")

            async def aclose(self):
                pass

        async def wire(request):
            return httpx.Response(
                200, headers={"content-type": "text/event-stream"}, stream=GeneratedBytes()
            )

        async with OpenAICompatibleChatGateway(
            config(), Credentials(), profile=PROFILE, transport=httpx.MockTransport(wire)
        ) as g:
            iterator = g.stream(request(streaming=True))
            assert isinstance(await anext(iterator), StreamStarted)
            tracemalloc.start()
            try:
                count = 0
                async for event in iterator:
                    if isinstance(event, TextDelta):
                        count += 1
                    elif isinstance(event, StreamCompleted):
                        assert event.completion.usage is None
                _, peak = tracemalloc.get_traced_memory()
                assert count == 600
                # 2.4 MB delivered. A full-answer duplicate would exceed this
                # generous budget; one current line/event fits comfortably.
                assert peak < 1024 * 1024
            finally:
                tracemalloc.stop()

    asyncio.run(run())


def test_usage_update_and_completion_share_only_normalized_snapshot_facts():
    req = request()
    usage = LLMUsage(1, 2, 3, {"private": OUTPUT, "reasoning_content": REASONING})
    update = UsageUpdate(req.invocation_id, usage)
    result = LLMStreamCompletion(
        invocation_id=req.invocation_id,
        model_used=req.model,
        finish_reason=FinishReason.STOP,
        usage=usage,
    )
    assert update.usage == result.usage == LLMUsage(1, 2, 3)
    assert OUTPUT not in str(serialized(update)) and REASONING not in str(serialized(result))


@pytest.mark.parametrize(
    "headers",
    [
        {"content-type": "text/event-stream", "x-request-id": PROMPT},
        {"content-type": "text/event-stream", "x-request-id": "x" * 129},
    ],
)
def test_request_id_diagnostics_reject_prompt_reflection_and_oversized_values(headers):
    events = asyncio.run(collect(Wire([normal(OUTPUT)], headers=headers)))
    result = completed(events)
    assert result.diagnostics.provider_request_id == "chatcmpl-controlled-stream"
    assert PROMPT not in str(serialized(result))


def test_secret_reflected_as_visible_text_is_rejected_without_leaking_it():
    events = asyncio.run(collect(Wire([normal(CANARY)])))
    failed(events, LLMErrorCode.MALFORMED_RESPONSE)
    assert CANARY not in str(serialized(events))


def test_close_transport_failure_is_normalized_and_authorization_already_scrubbed():
    async def run():
        wire = Wire([normal(OUTPUT)])

        async def close():
            assert "authorization" not in wire.requests[0].headers
            raise httpx.ReadError(CANARY + RAW)

        wire.body.aclose = close
        events = await collect(wire)
        failed(events, LLMErrorCode.PROVIDER_UNAVAILABLE)
        assert CANARY not in str(serialized(events)) and RAW not in str(serialized(events))

    asyncio.run(run())
