"""Offline Gemini Interactions v1 protocol, continuation and accounting proofs."""

import asyncio
import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from livingworld.application.llm import (
    AdapterKind,
    DispatchState,
    FinishReason,
    InvocationId,
    LLMError,
    LLMErrorCode,
    LLMFailure,
    LLMMessage,
    LLMPurpose,
    LLMRequest,
    LLMResponse,
    LLMUsage,
    MessageRole,
    ModelCapabilities,
    ModelRef,
    ProviderContinuationArtifact,
    ProviderId,
    ReasoningTokenRelation,
    StreamCompleted,
    StreamFailed,
    StreamStarted,
    StructuredFailureReason,
    StructuredOutputRequest,
    TextContent,
    TextDelta,
    UsageUpdate,
)
from livingworld.application.llm_budget import UsageUpperBound
from livingworld.application.llm_config import (
    EndpointConfig,
    ProviderConfig,
    SecretRef,
    SecretValue,
)
from livingworld.application.llm_execution import RetryPolicy, retry_failure_reason
from livingworld.application.llm_preflight import PreflightPricingEngine
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
    provider_fallback_reason,
)
from livingworld.application.llm_serialization import request_from_data, request_to_data
from livingworld.infrastructure.llm.anthropic_messages import (
    AnthropicMessagesGateway,
    AnthropicMessagesProfile,
)
from livingworld.infrastructure.llm.gemini_interactions import (
    GEMINI_CONTINUATION_SCHEMA_VERSION,
    GEMINI_INTERACTIONS_PATH,
    GeminiInteractionsGateway,
    GeminiInteractionsProfile,
)
from livingworld.infrastructure.llm.openai_compatible import (
    ChatCompletionsProfile,
    OpenAICompatibleChatGateway,
)
from livingworld.infrastructure.persistence.llm_repository import _decode, _encode

FIXTURES = Path(__file__).parent / "fixtures/llm"
SECRET = "AIzaSy-LW_SYNTHETIC_C005E3_NOT_REAL"
PROMPT = "LW_GEMINI_PRIVATE_PROMPT_CANARY"
OUTPUT = "LW_GEMINI_PRIVATE_OUTPUT_CANARY"
SIGNATURE = "LW_GEMINI_THOUGHT_SIGNATURE_CANARY"
GEMINI = ModelRef(ProviderId("gemini-main"), "gemini-configured-alias")


def fixture(name="gemini_interaction"):
    return json.loads((FIXTURES / f"{name}.json").read_text("utf-8"))


def request(**changes):
    values = dict(
        invocation_id=InvocationId(uuid4()),
        model=GEMINI,
        purpose=LLMPurpose("gemini_contract_test"),
        messages=(
            LLMMessage(MessageRole.SYSTEM, (TextContent("system"),)),
            LLMMessage(MessageRole.USER, (TextContent(PROMPT),)),
            LLMMessage(MessageRole.ASSISTANT, (TextContent("prior"),)),
            LLMMessage(MessageRole.USER, (TextContent("current"),)),
        ),
        max_output_tokens=64,
        stop_sequences=("<END>",),
    )
    values.update(changes)
    return LLMRequest(**values)


def config(provider_id=GEMINI.provider_id, **changes):
    values = dict(
        provider_id=provider_id,
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
    return GeminiInteractionsProfile(**values)


class Credentials:
    def __init__(self, value=SECRET, error=None):
        self.value, self.error, self.calls = value, error, []

    async def resolve(self, reference):
        self.calls.append(reference)
        if self.error:
            raise self.error("private credential failure")
        return SecretValue(self.value)


class Wire:
    def __init__(self, body=None, *, status=200, headers=None, content=None, error=None):
        self.body = fixture() if body is None else body
        self.status = status
        self.headers = {"x-request-id": "gemini_request_fixture", **(headers or {})}
        self.content, self.error = content, error
        self.requests, self.payloads = [], []

    async def __call__(self, wire):
        assert wire.headers["x-goog-api-key"] == SECRET
        assert "authorization" not in wire.headers
        assert "key=" not in str(wire.url)
        assert "cookie" not in wire.headers
        assert wire.url.path.endswith(GEMINI_INTERACTIONS_PATH)
        self.requests.append(wire)
        self.payloads.append(json.loads(wire.content))
        if self.error:
            raise self.error(SECRET + OUTPUT, request=wire)
        if self.content is not None:
            return httpx.Response(self.status, content=self.content, headers=self.headers)
        return httpx.Response(self.status, json=self.body, headers=self.headers)


class Bytes(httpx.AsyncByteStream):
    def __init__(self, fragments, error=None):
        self.fragments, self.error, self.closed = fragments, error, False

    async def __aiter__(self):
        for fragment in self.fragments:
            await asyncio.sleep(0)
            yield fragment
        if self.error:
            raise self.error(OUTPUT)

    async def aclose(self):
        self.closed = True


class StreamWire:
    def __init__(self, fragments, *, status=200, headers=None, error=None):
        self.body = Bytes(fragments)
        self.status, self.error = status, error
        self.headers = headers or {
            "content-type": "text/event-stream",
            "x-request-id": "gemini_stream_fixture",
        }
        self.requests, self.payloads, self.responses = [], [], []

    async def __call__(self, wire):
        assert wire.headers["x-goog-api-key"] == SECRET
        assert wire.headers["accept"] == "text/event-stream"
        assert "authorization" not in wire.headers and "cookie" not in wire.headers
        self.requests.append(wire)
        self.payloads.append(json.loads(wire.content))
        if self.error:
            raise self.error(OUTPUT, request=wire)
        response = httpx.Response(self.status, stream=self.body, headers=self.headers)
        self.responses.append(response)
        return response


def fragments(name="gemini_stream", size=None):
    data = (FIXTURES / f"{name}.sse").read_bytes()
    return [data] if size is None else [data[i : i + size] for i in range(0, len(data), size)]


async def generate(wire, req=None, *, credentials=None, model_profile=None):
    credentials = credentials or Credentials()
    async with GeminiInteractionsGateway(
        config(),
        credentials,
        profile=model_profile or profile(),
        transport=httpx.MockTransport(wire),
    ) as gateway:
        result = await gateway.generate(req or request())
    assert all("x-goog-api-key" not in saved.headers for saved in wire.requests)
    return result


async def collect(wire, req=None, *, credentials=None, model_profile=None):
    credentials = credentials or Credentials()
    async with GeminiInteractionsGateway(
        config(),
        credentials,
        profile=model_profile or profile(),
        transport=httpx.MockTransport(wire),
    ) as gateway:
        events = [event async for event in gateway.stream(req or request(streaming=True))]
    assert all("x-goog-api-key" not in saved.headers for saved in wire.requests)
    assert all(response.is_closed for response in wire.responses)
    return events


def failed_preflight(req, expected):
    wire, credentials = Wire(), Credentials()

    async def run():
        async with GeminiInteractionsGateway(
            config(), credentials, profile=profile(), transport=httpx.MockTransport(wire)
        ) as gateway:
            with pytest.raises(LLMError) as captured:
                await gateway.generate(req)
        return captured.value.failure

    failure = asyncio.run(run())
    assert failure.code is expected
    assert failure.dispatch_state is DispatchState.NOT_DISPATCHED
    assert not wire.requests and not credentials.calls
    return failure


def test_native_v1_mapping_is_stateless_private_and_minimal():
    wire = Wire()
    result = asyncio.run(generate(wire))
    payload = wire.payloads[0]
    assert payload == {
        "model": GEMINI.model_id,
        "input": [
            {"type": "user_input", "content": [{"type": "text", "text": PROMPT}]},
            {"type": "model_output", "content": [{"type": "text", "text": "prior"}]},
            {"type": "user_input", "content": [{"type": "text", "text": "current"}]},
        ],
        "stream": False,
        "store": False,
        "background": False,
        "generation_config": {
            "thinking_summaries": "none",
            "max_output_tokens": 64,
            "stop_sequences": ["<END>"],
        },
        "system_instruction": "system",
    }
    assert "previous_interaction_id" not in payload and "tools" not in payload
    assert result.text == "Hello world"
    assert result.model_used.model_id == "gemini-3.8-flash"


def test_usage_is_additive_and_preserves_total_without_inventing_cache_write():
    result = asyncio.run(generate(Wire()))
    assert result.usage == LLMUsage(
        input_tokens=11,
        output_tokens=2,
        total_tokens=18,
        cached_input_tokens=3,
        uncached_input_tokens=8,
        reasoning_output_tokens=5,
        reasoning_token_relation=ReasoningTokenRelation.ADDITIVE_TO_OUTPUT,
    )
    assert result.usage.cache_write_input_tokens is None


@pytest.mark.parametrize(
    "messages,code",
    [
        (
            (
                LLMMessage(MessageRole.SYSTEM, (TextContent("one"),)),
                LLMMessage(MessageRole.SYSTEM, (TextContent("two"),)),
                LLMMessage(MessageRole.USER, (TextContent("user"),)),
            ),
            LLMErrorCode.UNSUPPORTED_CAPABILITY,
        ),
        (
            (
                LLMMessage(MessageRole.USER, (TextContent("user"),)),
                LLMMessage(MessageRole.SYSTEM, (TextContent("late"),)),
            ),
            LLMErrorCode.UNSUPPORTED_CAPABILITY,
        ),
        (
            (LLMMessage(MessageRole.DEVELOPER, (TextContent("developer"),)),),
            LLMErrorCode.UNSUPPORTED_CAPABILITY,
        ),
    ],
)
def test_unsupported_message_layouts_fail_before_credentials(messages, code):
    failed_preflight(request(messages=messages), code)


def test_temperature_structured_stream_and_default_prefill_fail_before_network():
    failed_preflight(request(temperature=0.2), LLMErrorCode.UNSUPPORTED_CAPABILITY)
    failed_preflight(
        request(messages=(LLMMessage(MessageRole.ASSISTANT, (TextContent("prefill"),)),)),
        LLMErrorCode.UNSUPPORTED_CAPABILITY,
    )
    failed_preflight(
        request(
            streaming=True,
            structured_output=StructuredOutputRequest("x", {"type": "object"}),
        ),
        LLMErrorCode.UNSUPPORTED_CAPABILITY,
    )


def test_assistant_prefill_is_explicitly_profile_gated():
    req = request(
        messages=(
            LLMMessage(MessageRole.USER, (TextContent("user"),)),
            LLMMessage(MessageRole.ASSISTANT, (TextContent("prefix"),)),
        )
    )
    wire = Wire()
    asyncio.run(generate(wire, req, model_profile=profile(supports_assistant_prefill=True)))
    assert wire.payloads[0]["input"][-1]["type"] == "model_output"


def test_continuation_round_trip_reconstructs_thought_and_exact_text_boundaries():
    first = asyncio.run(generate(Wire()))
    artifact = first.continuation
    assert artifact.adapter_kind is AdapterKind.GEMINI
    assert SIGNATURE not in repr(artifact) and "Hello" not in artifact.opaque_payload.decode()
    previous = LLMMessage(MessageRole.ASSISTANT, first.content, artifact)
    req = request(messages=(previous, LLMMessage(MessageRole.USER, (TextContent("next"),))))
    encoded = request_to_data(req)
    restored = request_from_data(encoded)
    wire = Wire()
    asyncio.run(generate(wire, restored))
    assert wire.payloads[0]["input"][:2] == [
        {"type": "thought", "signature": "thought_sig_fixture"},
        {
            "type": "model_output",
            "content": [
                {"type": "text", "text": "Hello"},
                {"type": "text", "text": " world"},
            ],
        },
    ]


def test_tampered_visible_text_or_artifact_fails_before_credentials():
    first = asyncio.run(generate(Wire()))
    failed_preflight(
        request(
            messages=(
                LLMMessage(
                    MessageRole.ASSISTANT,
                    (TextContent("tampered"),),
                    first.continuation,
                ),
                LLMMessage(MessageRole.USER, (TextContent("next"),)),
            )
        ),
        LLMErrorCode.CONTINUATION_STATE_INVALID,
    )
    broken = replace(first.continuation, opaque_payload=b'{"steps":[]}')
    failed_preflight(
        request(
            messages=(
                LLMMessage(MessageRole.ASSISTANT, first.content, broken),
                LLMMessage(MessageRole.USER, (TextContent("next"),)),
            )
        ),
        LLMErrorCode.CONTINUATION_STATE_INVALID,
    )


def test_foreign_provider_or_adapter_artifact_is_ignored_by_gemini():
    first = asyncio.run(generate(Wire()))
    foreign = replace(first.continuation, provider_id=ProviderId("other-gemini"))
    req = request(
        messages=(
            LLMMessage(MessageRole.ASSISTANT, first.content, foreign),
            LLMMessage(MessageRole.USER, (TextContent("next"),)),
        )
    )
    wire = Wire()
    asyncio.run(generate(wire, req))
    assert wire.payloads[0]["input"][0] == {
        "type": "model_output",
        "content": [
            {"type": "text", "text": "Hello"},
            {"type": "text", "text": " world"},
        ],
    }


def test_openai_and_anthropic_payloads_ignore_gemini_artifact():
    first = asyncio.run(generate(Wire()))
    for provider, gateway_type, provider_profile in (
        (
            ProviderId("openai-main"),
            OpenAICompatibleChatGateway,
            ChatCompletionsProfile(),
        ),
        (
            ProviderId("anthropic-main"),
            AnthropicMessagesGateway,
            AnthropicMessagesProfile(default_max_output_tokens=64),
        ),
    ):
        model = ModelRef(provider, "model")
        req = request(
            model=model,
            messages=(
                LLMMessage(MessageRole.ASSISTANT, first.content, first.continuation),
                LLMMessage(MessageRole.USER, (TextContent("next"),)),
            ),
        )
        gateway = gateway_type(
            config(provider, endpoint=EndpointConfig("https://example.invalid")),
            Credentials(),
            profile=provider_profile,
            transport=httpx.MockTransport(Wire()),
        )
        payload = gateway._payload(req)
        assert "thought_sig_fixture" not in json.dumps(payload)
        asyncio.run(gateway.aclose())


def test_structured_response_uses_original_schema_and_local_draft_2020_12_validation():
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {"answer": {"type": "integer"}},
        "required": ["answer"],
        "additionalProperties": False,
    }
    req = request(structured_output=StructuredOutputRequest("answer", schema))
    wire = Wire(fixture("gemini_structured"))
    result = asyncio.run(generate(wire, req))
    assert wire.payloads[0]["response_format"] == {
        "type": "text",
        "mime_type": "application/json",
        "schema": schema,
    }
    assert result.structured_result.value["answer"] == 42


@pytest.mark.parametrize(
    "body,reason",
    [
        (
            {
                **fixture("gemini_structured"),
                "steps": [{"type": "model_output", "content": [{"type": "text", "text": "bad"}]}],
            },
            StructuredFailureReason.JSON_PARSE_FAILED,
        ),
        (
            {
                **fixture("gemini_structured"),
                "steps": [
                    {
                        "type": "model_output",
                        "content": [{"type": "text", "text": '{"answer":"bad"}'}],
                    }
                ],
            },
            StructuredFailureReason.SCHEMA_VALIDATION_FAILED,
        ),
        (
            {**fixture("gemini_structured"), "status": "incomplete"},
            StructuredFailureReason.OUTPUT_TRUNCATED,
        ),
    ],
)
def test_structured_failures_retain_completed_attempt_usage(body, reason):
    req = request(
        structured_output=StructuredOutputRequest(
            "answer",
            {
                "type": "object",
                "properties": {"answer": {"type": "integer"}},
                "required": ["answer"],
            },
        )
    )
    with pytest.raises(LLMError) as captured:
        asyncio.run(generate(Wire(body), req))
    failure = captured.value.failure
    assert failure.structured_detail.reason is reason
    assert failure.attempt.usage.output_tokens == 5
    assert (
        failure.attempt.usage.reasoning_token_relation is ReasoningTokenRelation.ADDITIVE_TO_OUTPUT
    )


def test_policy_block_is_successful_refusal_and_bypasses_structured_parsing():
    body = {
        **fixture("gemini_structured"),
        "status": "incomplete",
        "steps": [],
        "errors": [{"code": "safety", "message": OUTPUT}],
    }
    req = request(structured_output=StructuredOutputRequest("answer", {"type": "object"}))
    result = asyncio.run(generate(Wire(body), req))
    assert result.finish_reason is FinishReason.REFUSAL and result.content == ()


@pytest.mark.parametrize(
    "status,machine,expected,dispatch",
    [
        (
            400,
            "invalid_argument",
            LLMErrorCode.INVALID_REQUEST,
            DispatchState.HTTP_RESPONSE_RECEIVED,
        ),
        (401, "unauthenticated", LLMErrorCode.AUTHENTICATION, DispatchState.HTTP_RESPONSE_RECEIVED),
        (
            403,
            "permission_denied",
            LLMErrorCode.PERMISSION_DENIED,
            DispatchState.HTTP_RESPONSE_RECEIVED,
        ),
        (404, "not_found", LLMErrorCode.NOT_FOUND, DispatchState.HTTP_RESPONSE_RECEIVED),
        (
            429,
            "rate_limit_exceeded",
            LLMErrorCode.RATE_LIMITED,
            DispatchState.HTTP_RESPONSE_RECEIVED,
        ),
        (
            429,
            "quota_exceeded",
            LLMErrorCode.QUOTA_EXHAUSTED,
            DispatchState.REJECTED_BEFORE_EXECUTION,
        ),
        (
            412,
            "failed_precondition",
            LLMErrorCode.FAILED_PRECONDITION,
            DispatchState.HTTP_RESPONSE_RECEIVED,
        ),
        (500, "internal", LLMErrorCode.PROVIDER_UNAVAILABLE, DispatchState.HTTP_RESPONSE_RECEIVED),
        (
            503,
            "service_unavailable",
            LLMErrorCode.PROVIDER_UNAVAILABLE,
            DispatchState.HTTP_RESPONSE_RECEIVED,
        ),
        (504, "deadline_exceeded", LLMErrorCode.TIMEOUT, DispatchState.HTTP_RESPONSE_RECEIVED),
        (
            501,
            "unimplemented",
            LLMErrorCode.UNSUPPORTED_CAPABILITY,
            DispatchState.HTTP_RESPONSE_RECEIVED,
        ),
    ],
)
def test_stable_error_codes_are_primary_and_safe(status, machine, expected, dispatch):
    with pytest.raises(LLMError) as captured:
        asyncio.run(generate(Wire({"error": {"code": machine, "message": OUTPUT}}, status=status)))
    failure = captured.value.failure
    assert failure.code is expected and failure.dispatch_state is dispatch
    assert OUTPUT not in repr(failure) and failure.diagnostics.diagnostic_code == machine


def test_quota_never_same_candidate_retries_but_may_explicitly_fallback():
    failure = asyncio.run(_quota_failure())
    assert retry_failure_reason(failure, RetryPolicy()).value == "permanent_failure"
    assert provider_fallback_reason(failure, RetryPolicy()) is FallbackReason.QUOTA_EXHAUSTED


def test_three_provider_route_keeps_one_invocation_and_global_attempt_ordinals():
    openai = ModelRef(ProviderId("openai-main"), "openai-model")
    anthropic = ModelRef(ProviderId("anthropic-main"), "anthropic-model")
    gemini = GEMINI
    invocation = InvocationId(uuid4())
    req = request(invocation_id=invocation, model=openai)

    class Gateway:
        def __init__(self, result):
            self.result, self.requests = result, []

        async def generate(self, current):
            self.requests.append(current)
            if isinstance(self.result, LLMFailure):
                raise LLMError(self.result)
            return replace(self.result, invocation_id=current.invocation_id)

        async def stream(self, current):
            if False:
                yield current

    class Ledger:
        def __init__(self):
            self.starts, self.facts, self.terminals = [], [], []

        async def start(self, value):
            self.starts.append(value)

        async def finalize(self, value):
            self.facts.append(value)

        async def complete_invocation(self, identity, outcome):
            self.terminals.append((identity, outcome))

    def failure(model, status):
        return LLMFailure(
            LLMErrorCode.PROVIDER_UNAVAILABLE,
            invocation,
            dispatch_state=DispatchState.HTTP_RESPONSE_RECEIVED,
            http_status=status,
        )

    success = LLMResponse(
        invocation_id=invocation,
        model_used=gemini,
        content=(TextContent("ok"),),
        finish_reason=FinishReason.STOP,
        usage=LLMUsage(output_tokens=1),
    )
    gateways = {
        openai: Gateway(failure(openai, 503)),
        anthropic: Gateway(failure(anthropic, 503)),
        gemini: Gateway(success),
    }
    registry = ModelRegistry(
        tuple(
            RegisteredProvider(model.provider_id, kind)
            for model, kind in (
                (openai, AdapterKind.OPENAI_COMPATIBLE),
                (anthropic, AdapterKind.ANTHROPIC),
                (gemini, AdapterKind.GEMINI),
            )
        ),
        tuple(
            RegisteredModel(
                model=model,
                enabled=True,
                capabilities=ModelCapabilities(text_generation=True),
            )
            for model in (openai, anthropic, gemini)
        ),
    )
    policy = RoutePolicy(
        RoutePolicyId("openai-anthropic-gemini"),
        (openai, anthropic, gemini),
        frozenset({FallbackReason.TRANSIENT_HTTP_FAILURE}),
    )
    ledger = Ledger()
    router = RoutedModelGateway(
        registry,
        RoutingConfiguration((PurposePolicy(RoutingProfile.BEST, policy),)),
        ConfiguredGateways(gateways),
        policy=RetryPolicy(max_attempts=1),
        accounting=ledger,
        wall_clock=lambda: datetime(2026, 9, 19, tzinfo=UTC),
        accounting_diagnostics=lambda _diagnostic: None,
    )
    result = asyncio.run(router.generate(req, selection=ProfileSelection(RoutingProfile.BEST)))
    assert result.model_used == gemini and result.invocation_id == invocation
    assert [start.attempt_ordinal for start in ledger.starts] == [1, 2, 3]
    assert [start.requested_model for start in ledger.starts] == [openai, anthropic, gemini]
    assert len(ledger.terminals) == 1


async def _quota_failure():
    try:
        await generate(Wire({"error": {"code": "quota_exceeded"}}, status=429))
    except LLMError as error:
        return error.failure
    raise AssertionError


@pytest.mark.parametrize("size", [1, 7, None])
def test_stream_lifecycle_initial_text_thought_usage_and_continuation(size):
    wire = StreamWire(fragments(size=size))
    events = asyncio.run(collect(wire))
    assert sum(isinstance(event, StreamStarted) for event in events) == 1
    assert sum(isinstance(event, StreamCompleted) for event in events) == 1
    assert not any(isinstance(event, StreamFailed) for event in events)
    assert [event.text for event in events if isinstance(event, TextDelta)] == ["Hel", "lo"]
    assert SIGNATURE not in repr(events)
    update = next(event for event in events if isinstance(event, UsageUpdate))
    terminal = next(event.completion for event in events if isinstance(event, StreamCompleted))
    assert terminal.usage == update.usage
    assert terminal.usage.reasoning_token_relation is ReasoningTokenRelation.ADDITIVE_TO_OUTPUT
    assert terminal.finish_reason is FinishReason.STOP
    assert (
        terminal.continuation is not None
        and "Hello" not in terminal.continuation.opaque_payload.decode()
    )
    next_request = request(
        messages=(
            LLMMessage(
                MessageRole.ASSISTANT,
                (TextContent("Hello"),),
                terminal.continuation,
            ),
            LLMMessage(MessageRole.USER, (TextContent("next"),)),
        )
    )
    next_wire = Wire()
    asyncio.run(generate(next_wire, next_request))
    assert next_wire.payloads[0]["input"][:2] == [
        {"type": "thought", "signature": "thought_sig_stream"},
        {"type": "model_output", "content": [{"type": "text", "text": "Hello"}]},
    ]


def test_stream_error_after_created_is_unknown_dispatch_with_no_completion():
    events = asyncio.run(collect(StreamWire(fragments("gemini_stream_error"))))
    assert any(isinstance(event, StreamStarted) for event in events)
    assert [event.text for event in events if isinstance(event, TextDelta)] == ["partial"]
    assert not any(isinstance(event, StreamCompleted) for event in events)
    failure = next(event.failure for event in events if isinstance(event, StreamFailed))
    assert failure.dispatch_state is DispatchState.DISPATCHED_OR_UNKNOWN


def sse(name, data):
    return f"event: {name}\ndata: {json.dumps({'event_type': name, **data})}\n\n".encode()


def created():
    return sse(
        "interaction.created",
        {
            "interaction": {
                "id": "v1_custom",
                "status": "in_progress",
                "object": "interaction",
                "model": "gemini-3.8-flash",
            }
        },
    )


def test_unknown_well_formed_event_is_ignored_and_eof_before_completion_fails():
    data = created() + sse("future.bounded_event", {"safe": True})
    events = asyncio.run(collect(StreamWire([data])))
    assert any(isinstance(event, StreamStarted) for event in events)
    failure = next(event.failure for event in events if isinstance(event, StreamFailed))
    assert failure.code is LLMErrorCode.MALFORMED_RESPONSE


def test_unexpected_function_step_is_unsupported_and_route_locked():
    data = created() + sse(
        "step.start", {"index": 0, "step": {"type": "function_call", "name": "tool"}}
    )
    events = asyncio.run(collect(StreamWire([data])))
    assert any(isinstance(event, StreamStarted) for event in events)
    failure = next(event.failure for event in events if isinstance(event, StreamFailed))
    assert failure.code is LLMErrorCode.UNSUPPORTED_CAPABILITY


def test_nonstream_and_stream_malformed_success_and_transport_are_one_attempt():
    wire = Wire(content=b"not-json")
    with pytest.raises(LLMError) as captured:
        asyncio.run(generate(wire))
    assert captured.value.failure.code is LLMErrorCode.MALFORMED_RESPONSE
    assert len(wire.requests) == 1
    transport = Wire(error=httpx.ConnectError)
    with pytest.raises(LLMError) as captured:
        asyncio.run(generate(transport))
    assert captured.value.failure.dispatch_state is DispatchState.NOT_DISPATCHED
    assert len(transport.requests) == 1


def test_cancellation_propagates_without_terminal_event():
    gate = asyncio.Event()

    class Blocking(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield created()
            await gate.wait()

        async def aclose(self):
            pass

    async def run():
        wire = StreamWire([])
        wire.body = Blocking()
        async with GeminiInteractionsGateway(
            config(), Credentials(), profile=profile(), transport=httpx.MockTransport(wire)
        ) as gateway:
            iterator = gateway.stream(request(streaming=True))
            assert isinstance(await anext(iterator), StreamStarted)
            pending = asyncio.create_task(anext(iterator))
            await asyncio.sleep(0)
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await pending

    asyncio.run(run())


def test_generated_output_pricing_uses_reasoning_relation_and_fails_closed_when_unknown():
    model = ModelRef(GEMINI.provider_id, "gemini-3.8-flash")
    schedule = PricingSchedule(
        schedule_id="gemini-generated",
        model=model,
        currency="USD",
        effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        variants=(
            PricingVariant(
                variant_id="default",
                rates=(RateLine(Meter.GENERATED_OUTPUT, Decimal("1"), 1),),
            ),
        ),
        source_label="test",
    )
    engine = PricingEngine(InMemoryPricingCatalog((schedule,)))
    at = datetime(2026, 9, 19, tzinfo=UTC)
    additive = engine.estimate(
        requested=model,
        reported=model,
        at=at,
        usage=LLMUsage(
            output_tokens=2,
            reasoning_output_tokens=5,
            reasoning_token_relation=ReasoningTokenRelation.ADDITIVE_TO_OUTPUT,
        ),
    )
    included = engine.estimate(
        requested=model,
        reported=model,
        at=at,
        usage=LLMUsage(
            output_tokens=7,
            reasoning_output_tokens=5,
            reasoning_token_relation=ReasoningTokenRelation.INCLUDED_IN_OUTPUT,
        ),
    )
    unknown = engine.estimate(
        requested=model,
        reported=model,
        at=at,
        usage=LLMUsage(output_tokens=7, reasoning_output_tokens=5),
    )
    assert (
        additive.estimated_cost.amount == included.estimated_cost.amount == Decimal("7.000000000")
    )
    assert unknown.status is CostStatus.PRICING_CONTEXT_INCOMPLETE


def test_hard_preflight_uses_single_combined_generated_output_cap():
    schedule = PricingSchedule(
        schedule_id="gemini-bound",
        model=GEMINI,
        currency="USD",
        effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        variants=(
            PricingVariant(
                variant_id="default",
                rates=(RateLine(Meter.GENERATED_OUTPUT, Decimal("2"), 1),),
            ),
        ),
        source_label="test",
    )
    bound = PreflightPricingEngine(InMemoryPricingCatalog((schedule,))).bound(
        requested=GEMINI,
        usage=UsageUpperBound(input_tokens=10, output_tokens=4),
        at=datetime(2026, 9, 19, tzinfo=UTC),
    )
    assert bound.money.amount == Decimal("8.000000000")


def test_usage_relation_legacy_default_and_artifact_persistence_boundary():
    additive = LLMUsage(
        output_tokens=2,
        reasoning_output_tokens=5,
        reasoning_token_relation=ReasoningTokenRelation.ADDITIVE_TO_OUTPUT,
    )
    assert _decode(_encode(additive)) == additive
    old = _encode(additive)
    del old["fields"]["reasoning_token_relation"]
    assert _decode(old).reasoning_token_relation is ReasoningTokenRelation.UNKNOWN
    first = asyncio.run(generate(Wire()))
    with pytest.raises(Exception) as captured:
        _encode(first.continuation)
    assert "unsupported_accounting_value" in str(captured.value)


def test_artifact_contract_rejects_wrong_version_and_repr_has_no_payload_canary():
    artifact = ProviderContinuationArtifact(
        AdapterKind.GEMINI,
        GEMINI.provider_id,
        GEMINI_CONTINUATION_SCHEMA_VERSION,
        SIGNATURE.encode(),
        hashlib.sha256(b"visible").hexdigest(),
    )
    assert SIGNATURE not in repr(artifact)
    wrong = replace(artifact, artifact_schema_version=2)
    failed_preflight(
        request(
            messages=(
                LLMMessage(MessageRole.ASSISTANT, (TextContent("visible"),), wrong),
                LLMMessage(MessageRole.USER, (TextContent("next"),)),
            )
        ),
        LLMErrorCode.CONTINUATION_STATE_INVALID,
    )
