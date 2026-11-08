"""Offline native OpenAI Responses protocol, continuation and streaming proofs."""

import asyncio
import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
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
    StreamOutcome,
    StreamStarted,
    StructuredFailureReason,
    StructuredOutputRequest,
    TextContent,
    TextDelta,
    UsageUpdate,
)
from livingworld.application.llm_budget import ModelUsageLimits, UsageUpperBound
from livingworld.application.llm_config import (
    CredentialProvider,
    EndpointConfig,
    ProviderConfig,
    SecretRef,
    SecretValue,
)
from livingworld.application.llm_execution import RetryPolicy
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
)
from livingworld.application.llm_serialization import request_from_data, request_to_data
from livingworld.infrastructure.llm.anthropic_messages import (
    AnthropicMessagesGateway,
    AnthropicMessagesProfile,
)
from livingworld.infrastructure.llm.gemini_interactions import (
    GeminiInteractionsGateway,
    GeminiInteractionsProfile,
)
from livingworld.infrastructure.llm.openai_compatible import (
    ChatCompletionsProfile,
    OpenAICompatibleChatGateway,
)
from livingworld.infrastructure.llm.openai_responses import (
    OPENAI_RESPONSES_CONTINUATION_SCHEMA_VERSION,
    OPENAI_RESPONSES_PATH,
    OpenAIResponsesGateway,
    OpenAIResponsesProfile,
)

SECRET = "sk-openai-responses-test-secret"
PROMPT = "LW_OPENAI_RESPONSES_PRIVATE_PROMPT_CANARY"
OUTPUT = "Hello"
REASONING = "LW_OPENAI_RESPONSES_REASONING_TEXT_CANARY"
SUMMARY = "LW_OPENAI_RESPONSES_REASONING_SUMMARY_CANARY"
ENCRYPTED = "enc_LW_OPENAI_RESPONSES_OPAQUE_CIPHERTEXT_CANARY"
MODEL = ModelRef(ProviderId("openai-responses-main"), "configured-openai-alias")


class Credentials(CredentialProvider):
    def __init__(self, value=SECRET):
        self.value, self.calls = value, 0

    async def resolve(self, reference):
        assert reference == SECRET_REF
        self.calls += 1
        return SecretValue(self.value)


SECRET_REF = SecretRef(uuid4())


def config(provider_id=MODEL.provider_id, **changes):
    values = {
        "provider_id": provider_id,
        "endpoint": EndpointConfig("https://api.openai.test/base"),
        "secret_ref": SECRET_REF,
    }
    values.update(changes)
    return ProviderConfig(**values)


def profile(**changes):
    values = {
        "supports_streaming": True,
        "supports_native_structured_output": True,
        "supports_reasoning_continuation": True,
        "default_max_output_tokens": 64,
        "max_output_tokens": 4096,
    }
    values.update(changes)
    return OpenAIResponsesProfile(**values)


def request(**changes):
    values = {
        "invocation_id": InvocationId(uuid4()),
        "model": MODEL,
        "purpose": LLMPurpose("test.openai.responses"),
        "messages": (
            LLMMessage(MessageRole.SYSTEM, (TextContent("system"),)),
            LLMMessage(MessageRole.DEVELOPER, (TextContent("developer"),)),
            LLMMessage(MessageRole.USER, (TextContent(PROMPT),)),
            LLMMessage(MessageRole.ASSISTANT, (TextContent("prior"),)),
            LLMMessage(MessageRole.USER, (TextContent("current"),)),
        ),
    }
    values.update(changes)
    return LLMRequest(**values)


def usage():
    return {
        "input_tokens": 11,
        "input_tokens_details": {"cached_tokens": 3},
        "output_tokens": 7,
        "output_tokens_details": {"reasoning_tokens": 5},
        "total_tokens": 18,
    }


def response_body(text=OUTPUT, *, status="completed"):
    body = {
        "id": "resp_fixture_001",
        "object": "response",
        "status": status,
        "model": "gpt-test-version-2026-09-19",
        "service_tier": "default",
        "output": [
            {
                "id": "rs_fixture_001",
                "type": "reasoning",
                "status": "completed",
                "summary": [{"type": "summary_text", "text": SUMMARY}],
                "encrypted_content": ENCRYPTED,
            },
            {
                "id": "msg_fixture_001",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": text,
                        "annotations": [],
                    }
                ],
            },
        ],
        "usage": usage(),
    }
    if status == "incomplete":
        body["incomplete_details"] = {"reason": "max_output_tokens"}
    return body


class Wire:
    def __init__(self, body=None, *, status=200, headers=None, content=None, error=None):
        self.body = response_body() if body is None else body
        self.status = status
        self.headers = headers or {"x-request-id": "req_openai_responses_fixture"}
        self.content, self.error = content, error
        self.requests, self.payloads = [], []

    async def __call__(self, wire):
        assert wire.headers["authorization"] == f"Bearer {SECRET}"
        assert "cookie" not in wire.headers
        assert wire.url.path.endswith(OPENAI_RESPONSES_PATH)
        self.requests.append(wire)
        self.payloads.append(json.loads(wire.content))
        if self.error:
            raise self.error(PROMPT + SECRET, request=wire)
        if self.content is not None:
            return httpx.Response(self.status, content=self.content, headers=self.headers)
        return httpx.Response(self.status, json=self.body, headers=self.headers)


class Bytes(httpx.AsyncByteStream):
    def __init__(self, fragments):
        self.fragments, self.closed = fragments, False

    async def __aiter__(self):
        for fragment in self.fragments:
            await asyncio.sleep(0)
            yield fragment

    async def aclose(self):
        self.closed = True


class StreamWire:
    def __init__(self, fragments, *, status=200, headers=None):
        self.body = Bytes(fragments)
        self.status = status
        self.headers = headers or {
            "content-type": "text/event-stream",
            "x-request-id": "req_openai_responses_stream",
        }
        self.requests, self.payloads, self.responses = [], [], []

    async def __call__(self, wire):
        assert wire.headers["authorization"] == f"Bearer {SECRET}"
        assert wire.headers["accept"] == "text/event-stream"
        self.requests.append(wire)
        self.payloads.append(json.loads(wire.content))
        response = httpx.Response(self.status, stream=self.body, headers=self.headers)
        self.responses.append(response)
        return response


def sse(name, **fields):
    return f"event: {name}\ndata: {json.dumps({'type': name, **fields})}\n\n".encode()


def created():
    return sse(
        "response.created",
        response={
            "id": "resp_stream_001",
            "object": "response",
            "status": "in_progress",
            "model": "gpt-test-version-2026-09-19",
        },
    )


def stream_terminal(*, status="completed", text=OUTPUT, refusal=False):
    body = response_body(text, status=status)
    body["id"] = "resp_stream_001"
    if refusal:
        body["output"] = [
            {
                "id": "msg_refusal_001",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "refusal", "refusal": "private refusal text"}],
            }
        ]
    return body


def stream_events(*, size=None):
    data = b"".join(
        (
            created(),
            sse("response.future.optional", safe=True),
            sse("response.reasoning_text.delta", delta=REASONING, output_index=0),
            sse("response.reasoning_summary_text.delta", delta=SUMMARY, output_index=0),
            sse(
                "response.output_item.added",
                output_index=1,
                item={
                    "id": "msg_fixture_001",
                    "type": "message",
                    "status": "in_progress",
                    "role": "assistant",
                    "content": [],
                },
            ),
            sse("response.output_text.delta", output_index=1, content_index=0, delta="Hel"),
            sse("response.output_text.delta", output_index=1, content_index=0, delta="lo"),
            sse("response.output_text.done", output_index=1, content_index=0, text="Hello"),
            sse("response.completed", response=stream_terminal()),
        )
    )
    return [data] if size is None else [data[i : i + size] for i in range(0, len(data), size)]


async def generate(wire, req=None, *, credentials=None, model_profile=None):
    credentials = credentials or Credentials()
    async with OpenAIResponsesGateway(
        config(),
        credentials,
        profile=model_profile or profile(),
        transport=httpx.MockTransport(wire),
    ) as gateway:
        result = await gateway.generate(req or request())
    assert all("authorization" not in saved.headers for saved in wire.requests)
    return result


async def collect(wire, req=None, *, credentials=None, model_profile=None):
    credentials = credentials or Credentials()
    async with OpenAIResponsesGateway(
        config(),
        credentials,
        profile=model_profile or profile(),
        transport=httpx.MockTransport(wire),
    ) as gateway:
        events = [event async for event in gateway.stream(req or request(streaming=True))]
    assert all("authorization" not in saved.headers for saved in wire.requests)
    assert all(response.is_closed for response in wire.responses)
    return events


def failed_preflight(req, expected, *, model_profile=None):
    wire, credentials = Wire(), Credentials()

    async def run():
        async with OpenAIResponsesGateway(
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


def test_native_mapping_is_stateless_private_role_exact_and_minimal():
    wire = Wire()
    result = asyncio.run(generate(wire))
    payload = wire.payloads[0]
    assert payload == {
        "model": MODEL.model_id,
        "input": [
            {
                "type": "message",
                "role": "system",
                "content": [{"type": "input_text", "text": "system"}],
            },
            {
                "type": "message",
                "role": "developer",
                "content": [{"type": "input_text", "text": "developer"}],
            },
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": PROMPT}],
            },
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "input_text", "text": "prior"}],
            },
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "current"}],
            },
        ],
        "stream": False,
        "store": False,
        "background": False,
        "truncation": "disabled",
        "max_output_tokens": 64,
        "include": ["reasoning.encrypted_content"],
    }
    assert "previous_response_id" not in payload and "conversation" not in payload
    assert "tools" not in payload and "metadata" not in payload
    assert result.text == OUTPUT
    assert result.model_used.model_id == "gpt-test-version-2026-09-19"
    assert result.diagnostics.provider_request_id == "req_openai_responses_fixture"
    assert result.diagnostics.provider_response_id == "resp_fixture_001"


def test_usage_cached_and_reasoning_are_normalized_without_double_count_semantics():
    result = asyncio.run(generate(Wire()))
    assert result.usage == LLMUsage(
        input_tokens=11,
        output_tokens=7,
        total_tokens=18,
        cached_input_tokens=3,
        uncached_input_tokens=8,
        reasoning_output_tokens=5,
        reasoning_token_relation=ReasoningTokenRelation.INCLUDED_IN_OUTPUT,
    )


def test_temperature_and_limits_are_explicit_profile_capabilities():
    failed_preflight(request(temperature=0.2), LLMErrorCode.UNSUPPORTED_CAPABILITY)
    failed_preflight(
        request(max_output_tokens=5000),
        LLMErrorCode.INVALID_REQUEST,
    )
    wire = Wire()
    asyncio.run(
        generate(
            wire,
            request(temperature=0.2),
            model_profile=profile(supports_temperature=True),
        )
    )
    assert wire.payloads[0]["temperature"] == 0.2


def test_continuation_round_trip_reconstructs_reasoning_then_exact_assistant_message():
    first = asyncio.run(generate(Wire()))
    artifact = first.continuation
    assert artifact.adapter_kind is AdapterKind.OPENAI_RESPONSES
    assert ENCRYPTED not in repr(artifact)
    assert OUTPUT not in artifact.opaque_payload.decode()
    previous = LLMMessage(MessageRole.ASSISTANT, first.content, artifact)
    req = request(messages=(previous, LLMMessage(MessageRole.USER, (TextContent("next"),))))
    wire = Wire()
    asyncio.run(generate(wire, request_from_data(request_to_data(req))))
    assert wire.payloads[0]["input"][:2] == [
        {
            "type": "reasoning",
            "id": "rs_fixture_001",
            "status": "completed",
            "encrypted_content": ENCRYPTED,
            "summary": [],
        },
        {
            "type": "message",
            "id": "msg_fixture_001",
            "status": "completed",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "Hello"}],
        },
    ]
    assert "previous_response_id" not in wire.payloads[0]


def test_continuation_tamper_fails_before_secret_or_network_and_foreign_is_ignored():
    first = asyncio.run(generate(Wire()))
    failed_preflight(
        request(
            messages=(
                LLMMessage(
                    MessageRole.ASSISTANT,
                    (TextContent("Goodbye"),),
                    first.continuation,
                ),
                LLMMessage(MessageRole.USER, (TextContent("next"),)),
            )
        ),
        LLMErrorCode.CONTINUATION_STATE_INVALID,
    )
    foreign = replace(first.continuation, provider_id=ProviderId("other-provider"))
    wire = Wire()
    asyncio.run(
        generate(
            wire,
            request(
                messages=(
                    LLMMessage(MessageRole.ASSISTANT, first.content, foreign),
                    LLMMessage(MessageRole.USER, (TextContent("next"),)),
                )
            ),
        )
    )
    assert wire.payloads[0]["input"][0]["type"] == "message"
    assert ENCRYPTED not in json.dumps(wire.payloads[0])


def test_responses_artifact_is_ignored_by_other_protocol_adapters():
    first = asyncio.run(generate(Wire()))
    cases = (
        (
            ProviderId("compatible-foreign"),
            OpenAICompatibleChatGateway,
            ChatCompletionsProfile(),
        ),
        (
            ProviderId("anthropic-foreign"),
            AnthropicMessagesGateway,
            AnthropicMessagesProfile(default_max_output_tokens=64),
        ),
        (
            ProviderId("gemini-foreign"),
            GeminiInteractionsGateway,
            GeminiInteractionsProfile(),
        ),
    )
    for provider, gateway_type, provider_profile in cases:
        model = ModelRef(provider, "model")
        req = request(
            model=model,
            max_output_tokens=64,
            messages=(
                LLMMessage(MessageRole.ASSISTANT, first.content, first.continuation),
                LLMMessage(MessageRole.USER, (TextContent("next"),)),
            ),
        )
        gateway = gateway_type(
            config(provider_id=provider),
            Credentials(),
            profile=provider_profile,
            transport=httpx.MockTransport(Wire()),
        )
        payload = gateway._payload(req)
        assert ENCRYPTED not in json.dumps(payload)
        asyncio.run(gateway.aclose())


def test_reasoning_summary_text_and_ciphertext_never_become_visible_or_repr_diagnostics():
    result = asyncio.run(generate(Wire()))
    public = result.text + repr(result) + repr(result.diagnostics)
    assert OUTPUT in result.text
    assert all(canary not in public for canary in (REASONING, SUMMARY, ENCRYPTED, SECRET, PROMPT))
    assert result.usage.reasoning_output_tokens == 5


def test_native_structured_wire_shape_and_original_local_validation():
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {"answer": {"type": "integer"}},
        "required": ["answer"],
        "additionalProperties": False,
    }
    original = json.loads(json.dumps(schema))
    req = request(structured_output=StructuredOutputRequest("answer_schema", schema))
    wire = Wire(response_body('{"answer":42}'))
    result = asyncio.run(generate(wire, req))
    assert schema == original
    assert wire.payloads[0]["text"] == {
        "format": {
            "type": "json_schema",
            "name": "answer_schema",
            "schema": {key: value for key, value in schema.items() if key != "$schema"},
            "strict": True,
        }
    }
    assert result.structured_result.value["answer"] == 42


def test_structured_wire_name_is_stable_and_safe_without_mutating_source_schema():
    schema = {"type": "object"}
    req = request(structured_output=StructuredOutputRequest("unsafe name / 私密", schema))
    first, second = Wire(response_body("{}")), Wire(response_body("{}"))
    asyncio.run(generate(first, req))
    asyncio.run(generate(second, req))
    wire_name = first.payloads[0]["text"]["format"]["name"]
    assert wire_name == second.payloads[0]["text"]["format"]["name"]
    assert wire_name.startswith("lw_") and len(wire_name) == 35
    assert first.payloads[0]["text"]["format"]["schema"] == {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
        "required": [],
    }


@pytest.mark.parametrize(
    "body,reason",
    [
        (response_body("bad"), StructuredFailureReason.JSON_PARSE_FAILED),
        (response_body('{"answer":"bad"}'), StructuredFailureReason.SCHEMA_VALIDATION_FAILED),
        (
            response_body('{"answer":42}', status="incomplete"),
            StructuredFailureReason.OUTPUT_TRUNCATED,
        ),
    ],
)
def test_structured_failures_keep_attempt_usage(body, reason):
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
    assert (
        failure.attempt.usage.reasoning_token_relation is ReasoningTokenRelation.INCLUDED_IN_OUTPUT
    )


def test_refusal_is_success_and_bypasses_structured_parse():
    body = response_body()
    body["output"] = [
        {
            "id": "msg_refusal",
            "type": "message",
            "status": "completed",
            "role": "assistant",
            "content": [{"type": "refusal", "refusal": "not JSON"}],
        }
    ]
    result = asyncio.run(
        generate(
            Wire(body),
            request(structured_output=StructuredOutputRequest("answer", {"type": "object"})),
        )
    )
    assert result.finish_reason is FinishReason.REFUSAL and result.content == ()


def test_invalid_schema_and_structured_stream_fail_before_credentials_and_network():
    failed_preflight(
        request(
            structured_output=StructuredOutputRequest(
                "answer", {"$ref": "https://example.invalid/schema"}
            )
        ),
        LLMErrorCode.INVALID_REQUEST,
    )
    failed_preflight(
        request(
            streaming=True,
            structured_output=StructuredOutputRequest("answer", {"type": "object"}),
        ),
        LLMErrorCode.UNSUPPORTED_CAPABILITY,
    )


def test_tool_result_is_unsupported_and_never_executed():
    body = response_body()
    body["output"] = [{"type": "function_call", "name": "danger", "arguments": "{}"}]
    with pytest.raises(LLMError) as captured:
        asyncio.run(generate(Wire(body)))
    assert captured.value.failure.code is LLMErrorCode.UNSUPPORTED_CAPABILITY


@pytest.mark.parametrize("size", [1, 11, None])
def test_stream_state_machine_text_usage_terminal_and_opaque_continuation(size):
    events = asyncio.run(collect(StreamWire(stream_events(size=size))))
    assert sum(isinstance(event, StreamStarted) for event in events) == 1
    assert sum(isinstance(event, StreamCompleted) for event in events) == 1
    assert not any(isinstance(event, StreamFailed) for event in events)
    assert [event.text for event in events if isinstance(event, TextDelta)] == ["Hel", "lo"]
    completion = next(event.completion for event in events if isinstance(event, StreamCompleted))
    update = next(event.usage for event in events if isinstance(event, UsageUpdate))
    assert completion.usage == update
    assert completion.finish_reason is FinishReason.STOP
    assert completion.diagnostics.provider_response_id == "resp_stream_001"
    assert completion.continuation.adapter_kind is AdapterKind.OPENAI_RESPONSES
    assert OUTPUT not in completion.continuation.opaque_payload.decode()
    assert all(canary not in repr(events) for canary in (REASONING, SUMMARY, ENCRYPTED, SECRET))


def test_stream_refusal_has_no_visible_text_and_is_successful_terminal():
    data = b"".join(
        (
            created(),
            sse("response.refusal.delta", output_index=0, content_index=0, delta="private"),
            sse("response.refusal.done", output_index=0, content_index=0, refusal="private"),
            sse("response.completed", response=stream_terminal(refusal=True)),
        )
    )
    events = asyncio.run(collect(StreamWire([data])))
    assert not any(isinstance(event, TextDelta) for event in events)
    completion = next(event.completion for event in events if isinstance(event, StreamCompleted))
    assert completion.finish_reason is FinishReason.REFUSAL
    assert completion.outcome is StreamOutcome.REFUSAL


def test_unsafe_provider_request_id_is_omitted_without_breaking_stream():
    wire = StreamWire(
        stream_events(),
        headers={
            "content-type": "text/event-stream",
            "x-request-id": "unsafe/id",
        },
    )
    events = asyncio.run(collect(wire))
    completion = next(event.completion for event in events if isinstance(event, StreamCompleted))
    assert completion.diagnostics.provider_request_id is None
    assert completion.diagnostics.provider_response_id == "resp_stream_001"


def test_stream_incomplete_max_output_is_successful_output_limit_terminal():
    data = b"".join(
        (
            created(),
            sse("response.output_text.delta", output_index=1, content_index=0, delta="part"),
            sse("response.output_text.done", output_index=1, content_index=0, text="part"),
            sse(
                "response.incomplete",
                response=stream_terminal(status="incomplete", text="part"),
            ),
        )
    )
    events = asyncio.run(collect(StreamWire([data])))
    completion = next(event.completion for event in events if isinstance(event, StreamCompleted))
    assert completion.finish_reason is FinishReason.OUTPUT_LIMIT


def test_stream_failed_malformed_known_eof_and_post_start_error_have_no_completion():
    failed_body = stream_terminal()
    failed_body["status"] = "failed"
    failed_body["error"] = {"type": "server_error", "code": "server_error"}
    cases = (
        created() + sse("response.failed", response=failed_body),
        created()
        + sse("response.output_text.delta", output_index="bad", content_index=0, delta="x"),
        created(),
        created() + sse("error", code="server_error", message="private provider error"),
    )
    for data in cases:
        events = asyncio.run(collect(StreamWire([data])))
        assert any(isinstance(event, StreamStarted) for event in events)
        assert not any(isinstance(event, StreamCompleted) for event in events)
        failure = next(event.failure for event in events if isinstance(event, StreamFailed))
        assert failure.dispatch_state is not DispatchState.NOT_DISPATCHED


def test_stream_tool_item_is_unsupported_after_start():
    data = created() + sse(
        "response.output_item.added",
        output_index=0,
        item={"id": "call_1", "type": "function_call", "name": "danger"},
    )
    events = asyncio.run(collect(StreamWire([data])))
    failure = next(event.failure for event in events if isinstance(event, StreamFailed))
    assert failure.code is LLMErrorCode.UNSUPPORTED_CAPABILITY
    assert not any(isinstance(event, StreamCompleted) for event in events)


def test_stream_cancellation_propagates_without_failed_or_completed_terminal():
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
        async with OpenAIResponsesGateway(
            config(),
            Credentials(),
            profile=profile(),
            transport=httpx.MockTransport(wire),
        ) as gateway:
            iterator = gateway.stream(request(streaming=True))
            assert isinstance(await anext(iterator), StreamStarted)
            pending = asyncio.create_task(anext(iterator))
            await asyncio.sleep(0)
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await pending

    asyncio.run(run())


@pytest.mark.parametrize(
    "status,machine,expected,dispatch",
    [
        (
            400,
            "invalid_request_error",
            LLMErrorCode.INVALID_REQUEST,
            DispatchState.HTTP_RESPONSE_RECEIVED,
        ),
        (
            400,
            "context_length_exceeded",
            LLMErrorCode.CONTEXT_LIMIT,
            DispatchState.HTTP_RESPONSE_RECEIVED,
        ),
        (401, "invalid_api_key", LLMErrorCode.AUTHENTICATION, DispatchState.HTTP_RESPONSE_RECEIVED),
        (
            403,
            "permission_denied",
            LLMErrorCode.PERMISSION_DENIED,
            DispatchState.HTTP_RESPONSE_RECEIVED,
        ),
        (
            429,
            "rate_limit_exceeded",
            LLMErrorCode.RATE_LIMITED,
            DispatchState.HTTP_RESPONSE_RECEIVED,
        ),
        (
            429,
            "insufficient_quota",
            LLMErrorCode.QUOTA_EXHAUSTED,
            DispatchState.REJECTED_BEFORE_EXECUTION,
        ),
        (
            500,
            "server_error",
            LLMErrorCode.PROVIDER_UNAVAILABLE,
            DispatchState.HTTP_RESPONSE_RECEIVED,
        ),
        (504, "timeout", LLMErrorCode.TIMEOUT, DispatchState.HTTP_RESPONSE_RECEIVED),
    ],
)
def test_machine_error_mapping_is_safe(status, machine, expected, dispatch):
    body = {"error": {"type": machine, "code": machine, "message": PROMPT + SECRET}}
    with pytest.raises(LLMError) as captured:
        asyncio.run(generate(Wire(body, status=status)))
    failure = captured.value.failure
    assert failure.code is expected and failure.dispatch_state is dispatch
    assert failure.diagnostics.diagnostic_code == machine
    assert PROMPT not in repr(failure) and SECRET not in repr(failure)


def test_malformed_and_connect_failure_make_one_physical_call_only():
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


def test_openai_output_pricing_does_not_double_count_reasoning():
    reported = ModelRef(MODEL.provider_id, "gpt-test-version-2026-09-19")
    schedule = PricingSchedule(
        schedule_id="openai-responses-output",
        model=reported,
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
    estimate = PricingEngine(InMemoryPricingCatalog((schedule,))).estimate(
        requested=MODEL,
        reported=reported,
        at=datetime(2026, 9, 19, tzinfo=UTC),
        usage=LLMUsage(
            output_tokens=7,
            reasoning_output_tokens=5,
            reasoning_token_relation=ReasoningTokenRelation.INCLUDED_IN_OUTPUT,
        ),
    )
    assert estimate.status is CostStatus.PRICED
    assert estimate.estimated_cost.amount == Decimal("7.000000000")


def test_hard_preflight_uses_one_combined_generated_output_cap():
    schedule = PricingSchedule(
        schedule_id="openai-responses-bound",
        model=MODEL,
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
        requested=MODEL,
        usage=UsageUpperBound(input_tokens=10, output_tokens=4),
        at=datetime(2026, 9, 19, tzinfo=UTC),
    )
    assert bound.money.amount == Decimal("8.000000000")


def test_registry_supports_four_distinct_protocol_families():
    models = (
        ModelRef(ProviderId("compatible"), "compatible-model"),
        ModelRef(ProviderId("anthropic"), "anthropic-model"),
        ModelRef(ProviderId("gemini"), "gemini-model"),
        MODEL,
    )
    kinds = (
        AdapterKind.OPENAI_COMPATIBLE,
        AdapterKind.ANTHROPIC,
        AdapterKind.GEMINI,
        AdapterKind.OPENAI_RESPONSES,
    )
    registry = ModelRegistry(
        tuple(
            RegisteredProvider(model.provider_id, kind)
            for model, kind in zip(models, kinds, strict=True)
        ),
        tuple(
            RegisteredModel(
                model=model,
                enabled=True,
                capabilities=ModelCapabilities(text_generation=True),
                limits=ModelUsageLimits(
                    max_billable_input_tokens=1000,
                    max_output_tokens=100,
                ),
            )
            for model in models
        ),
    )
    assert tuple(registry.provider(model.provider_id).adapter_kind for model in models) == kinds


def test_four_protocol_route_keeps_one_invocation_and_global_attempt_ordinals():
    compatible = ModelRef(ProviderId("compatible-route"), "compatible-model")
    anthropic = ModelRef(ProviderId("anthropic-route"), "anthropic-model")
    gemini = ModelRef(ProviderId("gemini-route"), "gemini-model")
    responses = MODEL
    models = (compatible, anthropic, gemini, responses)
    invocation = InvocationId(uuid4())
    req = request(invocation_id=invocation, model=compatible)

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

    def failure():
        return LLMFailure(
            LLMErrorCode.PROVIDER_UNAVAILABLE,
            invocation,
            dispatch_state=DispatchState.HTTP_RESPONSE_RECEIVED,
            http_status=503,
        )

    success = LLMResponse(
        invocation_id=invocation,
        model_used=responses,
        content=(TextContent("ok"),),
        finish_reason=FinishReason.STOP,
        usage=LLMUsage(output_tokens=1),
    )
    gateways = {
        compatible: Gateway(failure()),
        anthropic: Gateway(failure()),
        gemini: Gateway(failure()),
        responses: Gateway(success),
    }
    kinds = (
        AdapterKind.OPENAI_COMPATIBLE,
        AdapterKind.ANTHROPIC,
        AdapterKind.GEMINI,
        AdapterKind.OPENAI_RESPONSES,
    )
    registry = ModelRegistry(
        tuple(
            RegisteredProvider(model.provider_id, kind)
            for model, kind in zip(models, kinds, strict=True)
        ),
        tuple(
            RegisteredModel(
                model=model,
                enabled=True,
                capabilities=ModelCapabilities(text_generation=True),
            )
            for model in models
        ),
    )
    policy = RoutePolicy(
        RoutePolicyId("four-native-protocols"),
        models,
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
    assert result.model_used == responses and result.invocation_id == invocation
    assert [start.attempt_ordinal for start in ledger.starts] == [1, 2, 3, 4]
    assert [start.requested_model for start in ledger.starts] == list(models)
    assert len(ledger.facts) == 4 and len(ledger.terminals) == 1


def test_artifact_is_not_supported_by_accounting_persistence_codec():
    from livingworld.infrastructure.persistence.llm_repository import _encode

    artifact = ProviderContinuationArtifact(
        AdapterKind.OPENAI_RESPONSES,
        MODEL.provider_id,
        OPENAI_RESPONSES_CONTINUATION_SCHEMA_VERSION,
        ENCRYPTED.encode(),
        hashlib.sha256(b"Hello").hexdigest(),
    )
    with pytest.raises(Exception) as captured:
        _encode(artifact)
    assert "unsupported_accounting_value" in str(captured.value)
    assert ENCRYPTED not in repr(artifact)
