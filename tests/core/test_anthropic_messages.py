"""Offline native Anthropic Messages protocol, policy and integration proofs."""

import asyncio
import json
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import fields, is_dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from io import StringIO
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from livingworld.application.llm import (
    DispatchState,
    FinishReason,
    InvocationId,
    LLMError,
    LLMErrorCode,
    LLMFailure,
    LLMMessage,
    LLMPurpose,
    LLMRequest,
    LLMUsage,
    MessageRole,
    ModelCapabilities,
    ModelRef,
    ProviderId,
    ReasoningTokenRelation,
    StreamCompleted,
    StreamFailed,
    StreamOutcome,
    StreamStarted,
    StructuredFailureReason,
    StructuredOutputMode,
    StructuredOutputRequest,
    TextContent,
    TextDelta,
    UsageUpdate,
)
from livingworld.application.llm_accounting import (
    AttemptOutcome,
    LedgerQuery,
    UsageCompleteness,
)
from livingworld.application.llm_config import (
    EndpointConfig,
    ProviderConfig,
    SecretRef,
    SecretValue,
)
from livingworld.application.llm_execution import (
    ExecutingModelGateway,
    JitterStrategy,
    RetryPolicy,
)
from livingworld.application.llm_pricing import (
    CostStatus,
    InMemoryPricingCatalog,
    Meter,
    PricingEngine,
    PricingSchedule,
    PricingVariant,
    RateLine,
)
from livingworld.application.llm_registry import (
    AdapterKind,
    ModelRegistry,
    RegisteredModel,
    RegisteredProvider,
)
from livingworld.application.llm_routing import (
    ConfiguredGateways,
    FallbackReason,
    ProfileSelection,
    PurposePolicy,
    RoutedModelGateway,
    RoutePolicy,
    RoutePolicyId,
    RoutingConfiguration,
    RoutingProfile,
)
from livingworld.application.llm_serialization import request_from_data, request_to_data
from livingworld.domain.identifiers import CorrelationId
from livingworld.infrastructure.llm.anthropic_messages import (
    ANTHROPIC_API_VERSION,
    AnthropicMessagesGateway,
    AnthropicMessagesProfile,
    AnthropicTemperaturePolicy,
    AnthropicWorkspaceId,
)
from livingworld.infrastructure.llm.sse import SSEDecoder, StreamLimits
from livingworld.infrastructure.logging import StructuredLogger
from livingworld.infrastructure.persistence import Database
from livingworld.infrastructure.persistence.llm_repository import _decode, _encode

FIXTURES = Path(__file__).parent / "fixtures/llm"
SECRET = "sk-ant-LW_SYNTHETIC_C005E2_NOT_REAL"
PROMPT = "LW_ANTHROPIC_PRIVATE_PROMPT_CANARY"
RESPONSE = "LW_ANTHROPIC_RESPONSE_CANARY"
REASONING = "LW_ANTHROPIC_REASONING_CANARY"
RAW = "LW_ANTHROPIC_RAW_SSE_CANARY"
ANTHROPIC = ModelRef(ProviderId("anthropic-main"), "configured-claude-alias")


def fixture(name="anthropic_message"):
    return json.loads((FIXTURES / f"{name}.json").read_text("utf-8"))


def request(**changes):
    values = dict(
        invocation_id=InvocationId(uuid4()),
        model=ANTHROPIC,
        purpose=LLMPurpose("anthropic_contract_test"),
        messages=(
            LLMMessage(MessageRole.SYSTEM, (TextContent("system one"),)),
            LLMMessage(MessageRole.SYSTEM, (TextContent("system two"),)),
            LLMMessage(MessageRole.USER, (TextContent(PROMPT), TextContent(" suffix"))),
            LLMMessage(MessageRole.ASSISTANT, (TextContent("prior assistant"),)),
            LLMMessage(MessageRole.USER, (TextContent("final user"),)),
        ),
        max_output_tokens=64,
        stop_sequences=("<END>", "\nSTOP"),
        correlation_id=CorrelationId(uuid4()),
        metadata={"world_id": "private-world", "path": "D:/private"},
    )
    values.update(changes)
    return LLMRequest(**values)


def config(**changes):
    values = dict(
        provider_id=ANTHROPIC.provider_id,
        endpoint=EndpointConfig("https://configured.example/native"),
        secret_ref=SecretRef(uuid4()),
        timeout_ms=1234,
    )
    values.update(changes)
    return ProviderConfig(**values)


def profile(**changes):
    values = dict(
        supports_streaming=True,
        supports_native_structured_output=True,
        default_max_output_tokens=128,
        max_output_tokens=256,
    )
    values.update(changes)
    return AnthropicMessagesProfile(**values)


class Credentials:
    def __init__(self, value=SECRET, error=None):
        self.value, self.error, self.calls = value, error, []

    async def resolve(self, reference):
        self.calls.append(reference)
        if self.error is not None:
            raise self.error("private credential failure")
        return SecretValue(self.value)


class Wire:
    def __init__(self, body=None, *, status=200, headers=None, content=None, error=None):
        self.body = fixture() if body is None else body
        self.status = status
        self.headers = {"request-id": "req_anthropic_fixture", **(headers or {})}
        self.content, self.error = content, error
        self.requests, self.payloads = [], []

    async def __call__(self, wire):
        assert wire.headers["authorization"] == f"Bearer {SECRET}"
        assert wire.headers["anthropic-version"] == ANTHROPIC_API_VERSION
        assert wire.headers["content-type"] == "application/json"
        assert "x-api-key" not in wire.headers
        assert "anthropic-beta" not in wire.headers
        assert "cookie" not in wire.headers
        self.requests.append(wire)
        self.payloads.append(json.loads(wire.content))
        if self.error is not None:
            raise self.error(SECRET + RAW, request=wire)
        if self.content is not None:
            return httpx.Response(self.status, content=self.content, headers=self.headers)
        return httpx.Response(self.status, json=self.body, headers=self.headers)


class Bytes(httpx.AsyncByteStream):
    def __init__(self, fragments, *, error=None):
        self.fragments, self.error = fragments, error
        self.closed = False

    async def __aiter__(self):
        for fragment in self.fragments:
            await asyncio.sleep(0)
            yield fragment
        if self.error is not None:
            raise self.error(SECRET + RAW)

    async def aclose(self):
        self.closed = True


class StreamWire:
    def __init__(self, fragments=(), *, status=200, headers=None, error=None, read_error=None):
        self.body = Bytes(fragments, error=read_error)
        self.status, self.error = status, error
        self.headers = (
            {"content-type": "text/event-stream", "request-id": "req_anthropic_stream"}
            if headers is None
            else headers
        )
        self.requests, self.payloads, self.responses = [], [], []

    async def __call__(self, wire):
        assert wire.headers["authorization"] == f"Bearer {SECRET}"
        assert wire.headers["anthropic-version"] == ANTHROPIC_API_VERSION
        assert wire.headers["accept"] == "text/event-stream"
        assert "x-api-key" not in wire.headers and "anthropic-beta" not in wire.headers
        self.requests.append(wire)
        self.payloads.append(json.loads(wire.content))
        if self.error is not None:
            raise self.error(SECRET + RAW, request=wire)
        response = httpx.Response(self.status, stream=self.body, headers=self.headers)
        self.responses.append(response)
        return response


def fragments(name, size=None):
    data = (FIXTURES / f"{name}.sse").read_bytes()
    return [data] if size is None else [data[i : i + size] for i in range(0, len(data), size)]


def serialized(value):
    if is_dataclass(value):
        return {field.name: serialized(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {key: serialized(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [serialized(item) for item in value]
    return str(value)


async def generate(wire, req=None, *, cfg=None, credentials=None, model_profile=None, **options):
    credentials = credentials or Credentials()
    async with AnthropicMessagesGateway(
        cfg or config(),
        credentials,
        profile=model_profile or profile(),
        transport=httpx.MockTransport(wire),
        **options,
    ) as gateway:
        result = await gateway.generate(req or request())
    assert all("authorization" not in saved.headers for saved in wire.requests)
    return result


async def collect(wire, req=None, *, model_profile=None, credentials=None, **options):
    credentials = credentials or Credentials()
    async with AnthropicMessagesGateway(
        config(),
        credentials,
        profile=model_profile or profile(),
        transport=httpx.MockTransport(wire),
        **options,
    ) as gateway:
        events = [event async for event in gateway.stream(req or request(streaming=True))]
        assert not gateway._client.cookies
    assert all("authorization" not in saved.headers for saved in wire.requests)
    assert all(response.is_closed for response in wire.responses)
    return events


def failed_preflight(req, expected, *, model_profile=None):
    wire, credentials = Wire(), Credentials()

    async def run():
        async with AnthropicMessagesGateway(
            config(),
            credentials,
            profile=model_profile or profile(),
            transport=httpx.MockTransport(wire),
        ) as gateway:
            with pytest.raises(LLMError) as captured:
                await gateway.generate(req)
        return captured.value.failure

    failure = asyncio.run(run())
    assert failure.code is expected
    assert failure.dispatch_state is DispatchState.NOT_DISPATCHED
    assert not wire.requests and not credentials.calls
    return failure


def test_native_mapping_headers_endpoint_and_private_metadata_boundary():
    async def run():
        wire, credentials = Wire(), Credentials()
        result = await generate(
            wire,
            request(temperature=0.7),
            credentials=credentials,
            model_profile=profile(temperature_policy=AnthropicTemperaturePolicy()),
            workspace_id=AnthropicWorkspaceId("wrkspc_test_123"),
        )
        assert result.text == RESPONSE
        assert credentials.calls
        saved = wire.requests[0]
        assert saved.method == "POST"
        assert str(saved.url) == "https://configured.example/native/v1/messages"
        assert saved.headers["anthropic-workspace-id"] == "wrkspc_test_123"
        payload = wire.payloads[0]
        assert payload == {
            "model": ANTHROPIC.model_id,
            "max_tokens": 64,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": PROMPT},
                        {"type": "text", "text": " suffix"},
                    ],
                },
                {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "prior assistant"}],
                },
                {
                    "role": "user",
                    "content": [{"type": "text", "text": "final user"}],
                },
            ],
            "stream": False,
            "system": [
                {"type": "text", "text": "system one"},
                {"type": "text", "text": "system two"},
            ],
            "stop_sequences": ["<END>", "\nSTOP"],
            "temperature": 0.7,
        }
        encoded = json.dumps(payload)
        for private in ("private-world", "D:/private", "anthropic_contract_test"):
            assert private not in encoded
        for forbidden in (
            "metadata",
            "tools",
            "thinking",
            "service_tier",
            "fallback",
            "user",
        ):
            assert forbidden not in payload

    asyncio.run(run())


def test_default_endpoint_and_explicit_profile_capabilities():
    async def run():
        wire = Wire()
        cfg = config(endpoint=None)
        result = await generate(wire, cfg=cfg)
        assert result.text == RESPONSE
        assert str(wire.requests[0].url) == "https://api.anthropic.com/v1/messages"
        async with AnthropicMessagesGateway(
            cfg,
            Credentials(),
            profile=profile(),
            transport=httpx.MockTransport(Wire()),
        ) as gateway:
            assert gateway.capabilities == ModelCapabilities(
                text_generation=True,
                streaming=True,
                structured_output=True,
                structured_output_mode=StructuredOutputMode.NATIVE_JSON_SCHEMA,
            )

    asyncio.run(run())


@pytest.mark.parametrize("case", ["system", "developer", "prefill", "temperature", "stops"])
def test_unsupported_role_and_parameter_semantics_fail_before_credentials(case):
    req = request()
    expected = LLMErrorCode.UNSUPPORTED_CAPABILITY
    if case == "system":
        req = replace(
            req,
            messages=(
                LLMMessage(MessageRole.USER, (TextContent("first"),)),
                LLMMessage(MessageRole.SYSTEM, (TextContent("late"),)),
            ),
        )
    elif case == "developer":
        req = replace(
            req,
            messages=(LLMMessage(MessageRole.DEVELOPER, (TextContent("developer"),)),),
        )
    elif case == "prefill":
        req = replace(
            req,
            messages=req.messages + (LLMMessage(MessageRole.ASSISTANT, (TextContent("prefill"),)),),
        )
    elif case == "temperature":
        req = replace(req, temperature=0.7)
    else:
        req = replace(req, stop_sequences=("1", "2", "3", "4", "5"))
        expected = LLMErrorCode.INVALID_REQUEST
    failed_preflight(req, expected)


def test_max_tokens_requires_request_or_explicit_profile_default_and_never_clamps():
    failed_preflight(
        request(max_output_tokens=None),
        LLMErrorCode.INVALID_REQUEST,
        model_profile=profile(default_max_output_tokens=None),
    )
    failed_preflight(request(max_output_tokens=257), LLMErrorCode.INVALID_REQUEST)

    async def run():
        wire = Wire()
        await generate(wire, request(max_output_tokens=None))
        assert wire.payloads[0]["max_tokens"] == 128

    asyncio.run(run())


def test_prefill_and_temperature_are_only_enabled_by_explicit_profile_policy():
    async def run():
        req = request(
            messages=(
                LLMMessage(MessageRole.USER, (TextContent("user"),)),
                LLMMessage(MessageRole.ASSISTANT, (TextContent("exact prefill "),)),
            ),
            temperature=1.0,
        )
        wire = Wire()
        await generate(
            wire,
            req,
            model_profile=profile(
                supports_assistant_prefill=True,
                temperature_policy=AnthropicTemperaturePolicy(1.0, 1.0),
            ),
        )
        assert wire.payloads[0]["messages"][-1]["content"][0]["text"] == "exact prefill "
        assert wire.payloads[0]["temperature"] == 1.0

    asyncio.run(run())
    failed_preflight(
        replace(request(), temperature=0.7),
        LLMErrorCode.UNSUPPORTED_CAPABILITY,
        model_profile=profile(temperature_policy=AnthropicTemperaturePolicy(1.0, 1.0)),
    )


def test_plain_response_preserves_facts_hides_thinking_and_normalizes_anthropic_usage():
    result = asyncio.run(generate(Wire()))
    assert result.model_used == ModelRef(ANTHROPIC.provider_id, "claude-test-version-20260901")
    assert result.finish_reason is FinishReason.STOP
    assert result.text == RESPONSE and REASONING not in result.text
    assert result.usage == LLMUsage(
        input_tokens=15,
        output_tokens=4,
        cached_input_tokens=2,
        cache_write_input_tokens=3,
        uncached_input_tokens=10,
        reasoning_output_tokens=1,
        cache_write_5m_input_tokens=1,
        cache_write_1h_input_tokens=2,
        reasoning_token_relation=ReasoningTokenRelation.INCLUDED_IN_OUTPUT,
    )
    assert result.processing_tier == "standard"
    assert result.diagnostics.provider_request_id == "req_anthropic_fixture"
    dump = json.dumps(serialized(result), default=str)
    assert REASONING not in dump and SECRET not in dump


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        ("end_turn", FinishReason.STOP),
        ("stop_sequence", FinishReason.STOP),
        ("max_tokens", FinishReason.OUTPUT_LIMIT),
        ("model_context_window_exceeded", FinishReason.CONTEXT_LIMIT),
        ("refusal", FinishReason.REFUSAL),
    ],
)
def test_stop_reason_mapping(reason, expected):
    body = fixture()
    body["stop_reason"] = reason
    result = asyncio.run(generate(Wire(body)))
    assert result.finish_reason is expected


@pytest.mark.parametrize("reason", ["tool_use", "pause_turn", "compaction"])
def test_continuation_or_tool_terminal_is_safe_unsupported_without_loop(reason):
    body = fixture()
    body["stop_reason"] = reason
    wire = Wire(body)
    with pytest.raises(LLMError) as captured:
        asyncio.run(generate(wire))
    assert captured.value.failure.code is LLMErrorCode.UNSUPPORTED_CAPABILITY
    assert captured.value.failure.attempt.usage.input_tokens == 15
    assert len(wire.requests) == 1


def test_tool_block_is_never_executed_or_exposed():
    tool_canary = "LW_PRIVATE_TOOL_ARGUMENT_CANARY"
    body = fixture()
    body["content"] = [{"type": "tool_use", "id": "toolu_1", "input": {"x": tool_canary}}]
    body["stop_reason"] = "tool_use"
    with pytest.raises(LLMError) as captured:
        asyncio.run(generate(Wire(body)))
    failure = captured.value.failure
    assert failure.code is LLMErrorCode.UNSUPPORTED_CAPABILITY
    assert tool_canary not in repr(failure)
    assert tool_canary not in json.dumps(serialized(failure), default=str)


def test_native_structured_output_adapts_wire_schema_and_validates_original_locally():
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {"value": {"type": "integer", "minimum": 3}},
        "required": ["value"],
        "additionalProperties": False,
    }
    original = deepcopy(schema)
    req = request(structured_output=StructuredOutputRequest("answer", schema))
    body = fixture("anthropic_structured")
    wire = Wire(body)
    result = asyncio.run(generate(wire, req))
    assert schema == original
    assert wire.payloads[0]["output_config"] == {
        "format": {
            "type": "json_schema",
            "schema": {
                "type": "object",
                "properties": {
                    "value": {
                        "type": "integer",
                        "description": 'Local validation constraints: {"minimum":3}',
                    }
                },
                "required": ["value"],
                "additionalProperties": False,
            },
        }
    }
    assert "output_format" not in wire.payloads[0]
    assert result.structured_result.value["value"] == 3


@pytest.mark.parametrize(
    ("text", "stop", "reason"),
    [
        ("not-json", "end_turn", StructuredFailureReason.JSON_PARSE_FAILED),
        ('{"value":2}', "end_turn", StructuredFailureReason.SCHEMA_VALIDATION_FAILED),
        ('{"value":3}', "max_tokens", StructuredFailureReason.OUTPUT_TRUNCATED),
        ('{"value":3}', "model_context_window_exceeded", StructuredFailureReason.OUTPUT_TRUNCATED),
    ],
)
def test_structured_failures_keep_safe_completed_attempt(text, stop, reason):
    req = request(
        structured_output=StructuredOutputRequest(
            "answer",
            {
                "type": "object",
                "properties": {"value": {"type": "integer", "minimum": 3}},
                "required": ["value"],
            },
        )
    )
    body = fixture()
    body["content"] = [{"type": "text", "text": text}]
    body["stop_reason"] = stop
    with pytest.raises(LLMError) as captured:
        asyncio.run(generate(Wire(body), req))
    failure = captured.value.failure
    assert failure.code is LLMErrorCode.STRUCTURED_OUTPUT_FAILED
    assert failure.structured_detail.reason is reason
    assert failure.attempt.usage.input_tokens == 15
    assert text not in repr(failure) and PROMPT not in repr(failure)


def test_structured_refusal_remains_success_and_skips_json_parsing():
    req = request(structured_output=StructuredOutputRequest("answer", {"type": "object"}))
    body = fixture("anthropic_refusal")
    body["content"][0]["text"] = "not-json refusal"
    result = asyncio.run(generate(Wire(body), req))
    assert result.finish_reason is FinishReason.REFUSAL
    assert result.structured_result is None


@pytest.mark.parametrize(
    ("status", "error_type", "code"),
    [
        (400, "invalid_request_error", LLMErrorCode.INVALID_REQUEST),
        (401, "authentication_error", LLMErrorCode.AUTHENTICATION),
        (402, "billing_error", LLMErrorCode.CONFIGURATION),
        (403, "permission_error", LLMErrorCode.AUTHENTICATION),
        (404, "not_found_error", LLMErrorCode.CONFIGURATION),
        (413, "request_too_large", LLMErrorCode.INVALID_REQUEST),
        (429, "rate_limit_error", LLMErrorCode.RATE_LIMITED),
        (500, "api_error", LLMErrorCode.PROVIDER_UNAVAILABLE),
        (504, "timeout_error", LLMErrorCode.TIMEOUT),
        (529, "overloaded_error", LLMErrorCode.PROVIDER_UNAVAILABLE),
    ],
)
def test_official_error_mapping_is_typed_bounded_and_content_free(status, error_type, code):
    body = (
        fixture(f"anthropic_error_{status}")
        if status in {429, 529}
        else {"type": "error", "error": {"type": error_type}}
    )
    body["error"]["message"] = PROMPT + RAW + SECRET
    wire = Wire(body, status=status, headers={"retry-after": "2"})
    with pytest.raises(LLMError) as captured:
        asyncio.run(generate(wire))
    failure = captured.value.failure
    assert failure.code is code
    assert failure.dispatch_state is DispatchState.HTTP_RESPONSE_RECEIVED
    assert failure.http_status == status
    assert failure.retry_after_seconds == (2.0 if status in {429, 500, 504, 529} else None)
    dump = repr(captured.value) + repr(failure) + json.dumps(serialized(failure), default=str)
    for canary in (PROMPT, RAW, SECRET):
        assert canary not in dump


@pytest.mark.parametrize("name", ["bytes", "missing", "nonfinite", "fixture"])
def test_malformed_success_is_rejected_without_raw_body(name):
    content = {
        "bytes": b"not-json",
        "missing": b'{"type":"message","role":"assistant"}',
        "nonfinite": b'{"x":NaN}',
        "fixture": (FIXTURES / "anthropic_malformed.json").read_bytes(),
    }[name]
    with pytest.raises(LLMError) as captured:
        asyncio.run(generate(Wire(content=content)))
    assert captured.value.failure.code is LLMErrorCode.MALFORMED_RESPONSE
    assert content.decode("utf-8") not in repr(captured.value.failure)


@pytest.mark.parametrize("size", [1, 7, None])
def test_named_sse_lifecycle_text_usage_ping_unknown_and_message_stop(size):
    wire = StreamWire(fragments("anthropic_stream", size))
    events = asyncio.run(collect(wire))
    assert sum(isinstance(event, StreamStarted) for event in events) == 1
    assert sum(isinstance(event, StreamCompleted) for event in events) == 1
    assert not any(isinstance(event, StreamFailed) for event in events)
    assert [event.text for event in events if isinstance(event, TextDelta)] == ["Hel", "lo"]
    assert REASONING not in json.dumps(serialized(events), default=str)
    updates = [event.usage for event in events if isinstance(event, UsageUpdate)]
    assert updates[-1] == LLMUsage(
        input_tokens=15,
        output_tokens=4,
        cached_input_tokens=2,
        cache_write_input_tokens=3,
        uncached_input_tokens=10,
        reasoning_output_tokens=1,
        cache_write_5m_input_tokens=1,
        cache_write_1h_input_tokens=2,
        reasoning_token_relation=ReasoningTokenRelation.INCLUDED_IN_OUTPUT,
    )
    completion = events[-1].completion
    assert completion.usage == updates[-1]
    assert completion.finish_reason is FinishReason.STOP
    assert completion.model_used.model_id == "claude-test-version-20260901"
    assert completion.diagnostics.provider_request_id == "req_anthropic_stream"
    assert wire.payloads[0]["stream"] is True
    assert b"[DONE]" not in b"".join(wire.body.fragments)


def test_stream_refusal_terminal_is_authoritative_without_buffering_prior_deltas():
    events = asyncio.run(collect(StreamWire(fragments("anthropic_stream_refusal"))))
    assert [event.text for event in events if isinstance(event, TextDelta)] == [
        "LW_ANTHROPIC_REFUSAL_TEXT"
    ]
    completion = events[-1].completion
    assert completion.finish_reason is FinishReason.REFUSAL
    assert completion.outcome is StreamOutcome.REFUSAL


def test_sse_error_event_after_start_is_unknown_dispatch_and_has_no_completion():
    events = asyncio.run(collect(StreamWire(fragments("anthropic_stream_error"))))
    assert isinstance(events[0], StreamStarted)
    assert isinstance(events[-1], StreamFailed)
    assert not any(isinstance(event, StreamCompleted) for event in events)
    failure = events[-1].failure
    assert failure.code is LLMErrorCode.PROVIDER_UNAVAILABLE
    assert failure.dispatch_state is DispatchState.DISPATCHED_OR_UNKNOWN
    assert failure.http_status is None
    assert RAW not in json.dumps(serialized(events), default=str)


@pytest.mark.parametrize("case", ["no_start", "no_reason", "eof", "done", "bad_known"])
def test_stream_protocol_failures_never_create_completion(case):
    def event(name, data):
        return f"event: {name}\ndata: {json.dumps(data)}\n\n".encode()

    start = event(
        "message_start",
        {
            "type": "message_start",
            "message": {
                "type": "message",
                "role": "assistant",
                "model": "claude-test",
                "content": [],
                "stop_reason": None,
                "usage": {"input_tokens": 1, "output_tokens": 0},
            },
        },
    )
    if case == "no_start":
        data = event("message_stop", {"type": "message_stop"})
    elif case == "no_reason":
        data = start + event("message_stop", {"type": "message_stop"})
    elif case == "eof":
        data = start
    elif case == "done":
        data = start + b"data: [DONE]\n\n"
    else:
        data = start + event("ping", {"type": "ping", "unexpected": object().__class__.__name__})
        data = data.replace(b'"type": "ping"', b'"type": "message_stop"')
    events = asyncio.run(collect(StreamWire([data])))
    assert isinstance(events[-1], StreamFailed)
    assert events[-1].failure.code is LLMErrorCode.MALFORMED_RESPONSE
    assert not any(isinstance(event, StreamCompleted) for event in events)


def test_structured_streaming_is_rejected_before_secret_or_network():
    req = request(
        streaming=True,
        structured_output=StructuredOutputRequest("x", {"type": "object"}),
    )
    wire, credentials = StreamWire(), Credentials()
    events = asyncio.run(collect(wire, req, credentials=credentials))
    assert len(events) == 1 and isinstance(events[0], StreamFailed)
    assert events[0].failure.code is LLMErrorCode.UNSUPPORTED_CAPABILITY
    assert not wire.requests and not credentials.calls


def test_contradictory_ttl_breakdown_preserves_output_and_marks_pricing_incomplete():
    body = fixture()
    body["usage"]["cache_creation"] = {
        "ephemeral_5m_input_tokens": 2,
        "ephemeral_1h_input_tokens": 2,
    }
    result = asyncio.run(generate(Wire(body)))
    assert result.text == RESPONSE
    assert result.usage.cache_write_input_tokens == 3
    assert result.usage.cache_write_5m_input_tokens is None
    assert result.usage.cache_write_1h_input_tokens is None
    assert result.usage.details["cache_write_ttl_breakdown_incomplete"] == 1
    assert result.diagnostics.diagnostic_code == "cache_write_ttl_breakdown_incomplete"
    schedule = PricingSchedule(
        schedule_id="anthropic-controlled",
        model=result.model_used,
        currency="USD",
        effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        variants=(
            PricingVariant(
                variant_id="ttl",
                rates=(
                    RateLine(Meter.UNCACHED_INPUT, Decimal("1")),
                    RateLine(Meter.CACHED_INPUT, Decimal("0.1")),
                    RateLine(Meter.CACHE_WRITE_5M_INPUT, Decimal("1.25")),
                    RateLine(Meter.CACHE_WRITE_1H_INPUT, Decimal("2")),
                    RateLine(Meter.OUTPUT, Decimal("5")),
                ),
            ),
        ),
        source_label="controlled-anthropic-fixture",
    )
    quote = PricingEngine(InMemoryPricingCatalog((schedule,))).estimate(
        requested=ANTHROPIC,
        reported=result.model_used,
        at=datetime(2026, 9, 19, tzinfo=UTC),
        usage=result.usage,
        processing_tier=result.processing_tier,
    )
    assert quote.status is CostStatus.PRICING_CONTEXT_INCOMPLETE


def test_ttl_cache_and_reasoning_meters_price_without_double_counting():
    result = asyncio.run(generate(Wire()))
    schedule = PricingSchedule(
        schedule_id="anthropic-controlled-complete",
        model=result.model_used,
        currency="USD",
        effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        variants=(
            PricingVariant(
                variant_id="ttl",
                rates=(
                    RateLine(Meter.UNCACHED_INPUT, Decimal("1")),
                    RateLine(Meter.CACHED_INPUT, Decimal("0.1")),
                    RateLine(Meter.CACHE_WRITE_5M_INPUT, Decimal("1.25")),
                    RateLine(Meter.CACHE_WRITE_1H_INPUT, Decimal("2")),
                    RateLine(Meter.OUTPUT, Decimal("5")),
                ),
            ),
        ),
        source_label="controlled-anthropic-fixture",
    )
    quote = PricingEngine(InMemoryPricingCatalog((schedule,))).estimate(
        requested=ANTHROPIC,
        reported=result.model_used,
        at=datetime(2026, 9, 19, tzinfo=UTC),
        usage=result.usage,
        processing_tier=result.processing_tier,
    )
    assert quote.status is CostStatus.PRICED
    assert [line.quantity for line in quote.snapshot.line_items] == [10, 2, 1, 2, 4]


class VirtualTime:
    def __init__(self):
        self.value, self.waits = 0.0, []

    def clock(self):
        return self.value

    async def sleep(self, seconds):
        self.waits.append(seconds)
        self.value += seconds


def test_529_retry_is_owned_by_execution_and_adapter_does_one_call_per_attempt():
    async def run():
        first = Wire(
            {"type": "error", "error": {"type": "overloaded_error", "message": RAW}},
            status=529,
            headers={"retry-after": "1"},
        )
        second = Wire()
        wires = [first, second]

        async def send(wire):
            return await wires.pop(0)(wire)

        credentials, time = Credentials(), VirtualTime()
        async with AnthropicMessagesGateway(
            config(),
            credentials,
            profile=profile(),
            transport=httpx.MockTransport(send),
        ) as adapter:
            execution = ExecutingModelGateway(
                adapter,
                policy=RetryPolicy(
                    max_attempts=2,
                    initial_backoff_seconds=0,
                    max_backoff_seconds=1,
                    max_elapsed_seconds=5,
                    jitter=JitterStrategy.NONE,
                ),
                clock=time.clock,
                sleep=time.sleep,
                random_unit=lambda: 1,
            )
            result = await execution.generate(request())
        assert result.text == RESPONSE
        assert len(first.requests) == len(second.requests) == 1
        assert len(credentials.calls) == 2
        assert time.waits == [1.0]

    asyncio.run(run())


class FailureGateway:
    def __init__(self, failure):
        self.failure, self.requests = failure, []

    async def generate(self, req):
        self.requests.append(req)
        raise LLMError(replace(self.failure, invocation_id=req.invocation_id))

    async def stream(self, req):
        self.requests.append(req)
        yield StreamFailed(replace(self.failure, invocation_id=req.invocation_id))


class BudgetAccountingSpy:
    def __init__(self):
        self.admissions, self.finals, self.terminals = [], [], []

    async def admit(self, start, req):
        self.admissions.append((start, req.model))

    async def finalize(self, facts):
        self.finals.append(facts)

    async def complete_invocation(self, invocation_id, outcome):
        self.terminals.append((invocation_id, outcome))


def routing_registry(openai, anthropic):
    caps = ModelCapabilities(text_generation=True)
    return ModelRegistry(
        (
            RegisteredProvider(openai.provider_id, AdapterKind.OPENAI_COMPATIBLE),
            RegisteredProvider(anthropic.provider_id, AdapterKind.ANTHROPIC),
        ),
        (
            RegisteredModel(model=openai, enabled=True, capabilities=caps),
            RegisteredModel(model=anthropic, enabled=True, capabilities=caps),
        ),
    )


def test_router_falls_back_to_native_anthropic_with_global_accounting_ordinals():
    async def run():
        openai = ModelRef(ProviderId("openai-main"), "openai-alias")
        req = replace(request(), model=openai)
        transient = LLMFailure(
            LLMErrorCode.PROVIDER_UNAVAILABLE,
            req.invocation_id,
            dispatch_state=DispatchState.HTTP_RESPONSE_RECEIVED,
            http_status=503,
        )
        first, wire, spy = FailureGateway(transient), Wire(), BudgetAccountingSpy()
        async with AnthropicMessagesGateway(
            config(), Credentials(), profile=profile(), transport=httpx.MockTransport(wire)
        ) as native:
            route = RoutePolicy(
                RoutePolicyId("openai-to-anthropic"),
                (openai, ANTHROPIC),
                frozenset({FallbackReason.TRANSIENT_HTTP_FAILURE}),
            )
            router = RoutedModelGateway(
                routing_registry(openai, ANTHROPIC),
                RoutingConfiguration((PurposePolicy(RoutingProfile.BALANCED, route),)),
                ConfiguredGateways({openai: first, ANTHROPIC: native}),
                policy=RetryPolicy(max_attempts=1, max_elapsed_seconds=5),
                budget_guard=spy,
                wall_clock=lambda: datetime(2026, 9, 19, tzinfo=UTC),
                accounting_diagnostics=lambda _: pytest.fail("unexpected accounting failure"),
                clock=lambda: 0.0,
                sleep=lambda _: asyncio.sleep(0),
            )
            result = await router.generate(req, selection=ProfileSelection(RoutingProfile.BALANCED))
        assert result.text == RESPONSE and result.invocation_id == req.invocation_id
        assert [start.attempt_ordinal for start, _ in spy.admissions] == [1, 2]
        assert [model for _, model in spy.admissions] == [openai, ANTHROPIC]
        assert [facts.start.attempt_ordinal for facts in spy.finals] == [1, 2]
        assert spy.finals[-1].usage.cache_write_5m_input_tokens == 1
        assert spy.finals[-1].usage.reasoning_output_tokens == 1
        assert spy.terminals == [(req.invocation_id, AttemptOutcome.SUCCESS)]
        assert len(first.requests) == 1 and len(wire.requests) == 1

    asyncio.run(run())


@pytest.mark.parametrize("mode", ["unknown_dispatch", "refusal"])
def test_router_does_not_cross_provider_fallback_for_unknown_dispatch_or_refusal(mode):
    async def run():
        openai = ModelRef(ProviderId("openai-main"), "openai-alias")
        req = replace(request(), model=openai)
        second_failure = LLMFailure(
            LLMErrorCode.PROVIDER_UNAVAILABLE,
            req.invocation_id,
            dispatch_state=DispatchState.DISPATCHED_OR_UNKNOWN,
        )
        second = FailureGateway(second_failure)
        if mode == "unknown_dispatch":
            first = FailureGateway(second_failure)
        else:
            body = fixture()
            body["stop_reason"] = "refusal"
            first = AnthropicMessagesGateway(
                config(provider_id=openai.provider_id),
                Credentials(),
                profile=profile(),
                transport=httpx.MockTransport(Wire(body)),
            )
        route = RoutePolicy(
            RoutePolicyId("no-unsafe-fallback"),
            (openai, ANTHROPIC),
            frozenset({FallbackReason.TRANSIENT_HTTP_FAILURE}),
        )
        router = RoutedModelGateway(
            routing_registry(openai, ANTHROPIC),
            RoutingConfiguration((PurposePolicy(RoutingProfile.BALANCED, route),)),
            ConfiguredGateways({openai: first, ANTHROPIC: second}),
            policy=RetryPolicy(max_attempts=1),
        )
        try:
            if mode == "unknown_dispatch":
                with pytest.raises(LLMError):
                    await router.generate(req, selection=ProfileSelection(RoutingProfile.BALANCED))
            else:
                result = await router.generate(
                    req, selection=ProfileSelection(RoutingProfile.BALANCED)
                )
                assert result.finish_reason is FinishReason.REFUSAL
        finally:
            if isinstance(first, AnthropicMessagesGateway):
                await first.aclose()
        assert not second.requests

    asyncio.run(run())


def test_logs_failures_and_safe_contract_objects_never_retain_content_or_secrets():
    async def run():
        output = StringIO()
        logger = StructuredLogger(output)
        wire = Wire(
            {"type": "error", "error": {"type": "overloaded_error", "message": RAW + PROMPT}},
            status=529,
            headers={"request-id": SECRET},
        )
        with pytest.raises(LLMError) as captured:
            await generate(wire, logger=logger)
        dump = (
            output.getvalue()
            + repr(captured.value)
            + json.dumps(serialized(captured.value.failure), default=str)
        )
        for canary in (SECRET, PROMPT, RESPONSE, REASONING, RAW, "private-world", "D:/private"):
            assert canary not in dump

    asyncio.run(run())


def test_request_codec_round_trips_temperature_and_reads_legacy_absence_as_none():
    current = request(temperature=0.7, max_output_tokens=None)
    encoded = request_to_data(current)
    assert request_from_data(encoded) == current
    encoded.pop("temperature")
    assert request_from_data(encoded) == replace(current, temperature=None)


def test_accounting_codec_preserves_ttl_facts_and_old_records_default_to_unknown():
    usage = LLMUsage(
        input_tokens=15,
        output_tokens=4,
        cached_input_tokens=2,
        cache_write_input_tokens=3,
        uncached_input_tokens=10,
        reasoning_output_tokens=1,
        cache_write_5m_input_tokens=1,
        cache_write_1h_input_tokens=2,
    )
    encoded = _encode(usage)
    assert _decode(encoded) == usage
    encoded["fields"].pop("cache_write_5m_input_tokens")
    encoded["fields"].pop("cache_write_1h_input_tokens")
    old = _decode(encoded)
    assert old.cache_write_5m_input_tokens is None
    assert old.cache_write_1h_input_tokens is None


def test_real_native_attempt_uses_generic_durable_accounting_and_pricing(tmp_path):
    async def run():
        db = Database(tmp_path)
        try:
            await db.initialize()
            reported = ModelRef(ANTHROPIC.provider_id, "claude-test-version-20260901")
            schedule = PricingSchedule(
                schedule_id="anthropic-durable-controlled",
                model=reported,
                currency="USD",
                effective_from=datetime(2026, 1, 1, tzinfo=UTC),
                variants=(
                    PricingVariant(
                        variant_id="ttl",
                        rates=(
                            RateLine(Meter.UNCACHED_INPUT, Decimal("1")),
                            RateLine(Meter.CACHED_INPUT, Decimal("0.1")),
                            RateLine(Meter.CACHE_WRITE_5M_INPUT, Decimal("1.25")),
                            RateLine(Meter.CACHE_WRITE_1H_INPUT, Decimal("2")),
                            RateLine(Meter.OUTPUT, Decimal("5")),
                        ),
                    ),
                ),
                source_label="controlled-anthropic-fixture",
            )
            ledger = db.llm_usage_ledger(catalog=InMemoryPricingCatalog((schedule,)))
            req, wire = request(), Wire()
            async with AnthropicMessagesGateway(
                config(),
                Credentials(),
                profile=profile(),
                transport=httpx.MockTransport(wire),
            ) as adapter:
                execution = ExecutingModelGateway(
                    adapter,
                    policy=RetryPolicy(max_attempts=1),
                    accounting=ledger,
                    wall_clock=lambda: datetime(2026, 9, 19, tzinfo=UTC),
                    accounting_diagnostics=lambda _: pytest.fail("unexpected accounting failure"),
                    clock=lambda: 0.0,
                    sleep=lambda _: asyncio.sleep(0),
                )
                result = await execution.generate(req)
            assert result.model_used == reported
            rows = await ledger.query(LedgerQuery(invocation_id=req.invocation_id))
            assert len(rows) == 1
            row = rows[0]
            assert row.start.requested_model == ANTHROPIC
            assert row.facts.reported_model == reported
            assert row.facts.completeness is UsageCompleteness.FINAL
            assert row.facts.usage.cache_write_5m_input_tokens == 1
            assert row.facts.usage.cache_write_1h_input_tokens == 2
            assert row.facts.usage.reasoning_output_tokens == 1
            assert row.facts.processing_tier == "standard"
            assert row.quote.status is CostStatus.PRICED
            assert [line.quantity for line in row.quote.snapshot.line_items] == [10, 2, 1, 2, 4]
            raw = json.dumps(_encode(row.facts), default=str)
            for canary in (SECRET, PROMPT, RESPONSE, REASONING, RAW, "private-world"):
                assert canary not in raw
        finally:
            await db.close()

    asyncio.run(run())


def test_named_sse_parser_extension_keeps_openai_data_only_compatibility():
    decoder = SSEDecoder(StreamLimits())
    payload = b'event: message_stop\ndata: {"type":"message_stop"}\n\n'
    named = list(decoder.feed_named(payload))
    assert named[0].event == "message_stop"
    assert named[0].data == '{"type":"message_stop"}'
    assert list(SSEDecoder(StreamLimits()).feed(payload)) == ['{"type":"message_stop"}']
