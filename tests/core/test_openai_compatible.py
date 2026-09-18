"""Offline wire fixtures and transport/credential boundaries; no live API calls."""

import asyncio
import json
from copy import deepcopy
from dataclasses import FrozenInstanceError, asdict, replace
from io import StringIO
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from livingworld.application.llm import (
    FinishReason,
    InvocationId,
    LLMContractError,
    LLMError,
    LLMErrorCode,
    LLMMessage,
    LLMPurpose,
    LLMRequest,
    MessageRole,
    ModelGateway,
    ModelRef,
    ProviderId,
    StructuredOutputRequest,
    TextContent,
)
from livingworld.application.llm_config import (
    EndpointConfig,
    ProviderConfig,
    SecretRef,
    SecretValue,
)
from livingworld.domain.identifiers import CorrelationId
from livingworld.infrastructure.llm.fake import FakeModelGateway
from livingworld.infrastructure.llm.openai_compatible import (
    ChatCompletionsProfile,
    OpenAICompatibleChatGateway,
)
from livingworld.infrastructure.logging import StructuredLogger

CANARY = "LW_SYNTHETIC_C005B_CREDENTIAL_CANARY_NOT_A_REAL_KEY"
PROMPT = "LW_SYNTHETIC_PRIVATE_PROMPT_NOT_FOR_LOGGING"
RESPONSE = "LW_SYNTHETIC_RESPONSE_NOT_FOR_LOGGING"
REASONING = "LW_PRIVATE_REASONING_CANARY_NOT_ASSISTANT_TEXT"
FIXTURES = Path(__file__).parent / "fixtures/llm"


def fixture(name="openai_chat"):
    return json.loads((FIXTURES / f"{name}.json").read_text("utf-8"))


def request(**changes):
    values = dict(
        invocation_id=InvocationId(uuid4()),
        model=ModelRef(ProviderId("configured-provider"), "opaque/model:1"),
        purpose=LLMPurpose("adapter_contract_test"),
        messages=(
            LLMMessage(MessageRole.SYSTEM, (TextContent("Synthetic system"),)),
            LLMMessage(MessageRole.USER, (TextContent(PROMPT), TextContent(" · suffix"))),
            LLMMessage(MessageRole.ASSISTANT, (TextContent("Synthetic history"),)),
        ),
        max_output_tokens=64,
        stop_sequences=("<END>", "\nSTOP"),
        correlation_id=CorrelationId(uuid4()),
        metadata={"world_id": "internal-world", "path": "C:/private/internal"},
    )
    values.update(changes)
    return LLMRequest(**values)


def config(**changes):
    values = dict(
        provider_id=ProviderId("configured-provider"),
        endpoint=EndpointConfig("https://configured.example/v1"),
        secret_ref=SecretRef(uuid4()),
        timeout_ms=1234,
    )
    values.update(changes)
    return ProviderConfig(**values)


class Credentials:
    def __init__(self, value=CANARY, error=None):
        self._value = value
        self.error = error
        self.calls = []

    async def resolve(self, reference):
        self.calls.append(reference)
        if self.error is not None:
            raise self.error
        return SecretValue(self._value)


class Wire:
    def __init__(self, body=None, *, status=200, headers=None, content=None, error=None):
        self.body = fixture() if body is None else body
        self.status = status
        self.headers = headers or {}
        self.content = content
        self.error = error
        self.requests = []
        self.payloads = []

    async def __call__(self, wire):
        # Plaintext exists only inside the actual transport handler. The saved
        # HTTP request must have its Authorization removed after completion.
        assert wire.headers["authorization"] == f"Bearer {CANARY}"
        assert wire.headers["content-type"] == "application/json"
        assert "cookie" not in wire.headers
        self.requests.append(wire)
        self.payloads.append(json.loads(wire.content))
        if self.error is not None:
            raise self.error(CANARY, request=wire)
        if self.content is not None:
            return httpx.Response(self.status, content=self.content, headers=self.headers)
        return httpx.Response(self.status, json=self.body, headers=self.headers)


async def outcome(wire, req=None, *, cfg=None, creds=None, profile=None, logger=None):
    req = req or request()
    creds = creds or Credentials()
    options = {} if profile is None else {"profile": profile}
    async with OpenAICompatibleChatGateway(
        cfg or config(), creds, transport=httpx.MockTransport(wire), logger=logger, **options
    ) as gateway:
        result = await gateway.generate(req)
    assert len(wire.requests) == 1
    assert all("authorization" not in saved.headers for saved in wire.requests)
    return result


def assert_failure(wire, code, **kwargs):
    with pytest.raises(LLMError) as captured:
        asyncio.run(outcome(wire, **kwargs))
    error = captured.value
    assert error.failure.code is code
    assert error.__context__ is None
    assert error.__cause__ is None
    assert CANARY not in repr(error)
    assert CANARY not in repr(error.failure)
    assert all("authorization" not in saved.headers for saved in wire.requests)
    return error


@pytest.mark.parametrize(
    ("base", "expected"),
    [
        ("https://api.deepseek.com", "https://api.deepseek.com/chat/completions"),
        ("https://api.openai.com/v1", "https://api.openai.com/v1/chat/completions"),
        ("http://127.0.0.1:43210/v1/", "http://127.0.0.1:43210/v1/chat/completions"),
        (
            "http://localhost:43210/private/api",
            "http://localhost:43210/private/api/chat/completions",
        ),
        ("http://192.168.1.10:8080/v1", "http://192.168.1.10:8080/v1/chat/completions"),
        ("http://[::1]:8080/v1", "http://[::1]:8080/v1/chat/completions"),
    ],
)
def test_configured_base_paths_are_appended_without_vendor_guessing(base, expected):
    wire = Wire()
    asyncio.run(outcome(wire, cfg=config(endpoint=EndpointConfig(base))))
    assert wire.requests[0].method == "POST"
    assert str(wire.requests[0].url) == expected


@pytest.mark.parametrize(
    "base",
    [
        "ftp://configured.example",
        "https:///missing-host",
        "https://name:key@configured.example",
        "https://configured.example#fragment",
        "https://configured.example?key=unsafe",
        "https://configured.example:70000",
        "https://configured.example:0",
        "https://bad host",
        "https://configured.example:",
        "https://bad%host",
        "https://configured.example/a/../v1",
        "https://configured.example/%2e%2e/v1",
        "https://configured.example/%invalid",
    ],
)
def test_unsafe_or_ambiguous_endpoint_is_rejected_before_resolving_credentials(base):
    creds = Credentials()
    with pytest.raises(LLMContractError):
        OpenAICompatibleChatGateway(config(endpoint=EndpointConfig(base)), creds)
    assert creds.calls == []


@pytest.mark.parametrize("status", [301, 302, 307, 308])
def test_redirects_do_not_forward_bearer_to_another_origin(status):
    wire = Wire(status=status, headers={"location": "https://other.example/steal"})
    assert_failure(wire, LLMErrorCode.CONFIGURATION)
    assert len(wire.requests) == 1
    assert wire.requests[0].url.host == "configured.example"


def test_request_mapping_and_optional_single_choice_profile():
    async def scenario():
        for supports_n in (False, True):
            wire = Wire()
            req = request()
            await outcome(wire, req, profile=ChatCompletionsProfile(supports_n=supports_n))
            payload = wire.payloads[0]
            assert payload == {
                "model": req.model.model_id,
                "messages": [
                    {"role": "system", "content": "Synthetic system"},
                    {"role": "user", "content": PROMPT + " · suffix"},
                    {"role": "assistant", "content": "Synthetic history"},
                ],
                "max_tokens": 64,
                "stream": False,
                "stop": ["<END>", "\nSTOP"],
                **({"n": 1} if supports_n else {}),
            }
            assert "max_completion_tokens" not in payload
            assert wire.requests[0].extensions["timeout"] == dict.fromkeys(
                ("connect", "read", "write", "pool"), 1.234
            )
            encoded = json.dumps(payload)
            for internal in (
                str(req.invocation_id.value),
                str(req.correlation_id),
                "internal-world",
                "C:/private/internal",
                req.purpose.value,
            ):
                assert internal not in encoded

    asyncio.run(scenario())


def test_empty_stops_are_omitted_and_profile_is_immutable():
    wire = Wire()
    asyncio.run(outcome(wire, request(stop_sequences=())))
    assert "stop" not in wire.payloads[0]
    profile = ChatCompletionsProfile(supports_n=True)
    with pytest.raises(FrozenInstanceError):
        profile.supports_n = False
    with pytest.raises(LLMContractError):
        ChatCompletionsProfile(supports_n=1)


@pytest.mark.parametrize("feature", ["developer", "stream", "schema", "multimodal", "five_stops"])
def test_unsupported_requests_fail_before_transport_and_credentials(feature):
    req = request()
    if feature == "developer":
        req = replace(
            req, messages=(LLMMessage(MessageRole.DEVELOPER, (TextContent("instruction"),)),)
        )
    elif feature == "stream":
        req = replace(req, streaming=True)
    elif feature == "schema":
        req = replace(req, structured_output=StructuredOutputRequest("example", {"type": "object"}))
    elif feature == "five_stops":
        req = replace(req, stop_sequences=("a", "b", "c", "d", "e"))
    else:
        # Simulate a future union member at the adapter seam. Today's public
        # contract already rejects this object; adapter must also fail closed.
        object.__setattr__(req.messages[0], "content", (object(),))
    creds = Credentials()
    wire = Wire()
    assert_failure(wire, LLMErrorCode.UNSUPPORTED_CAPABILITY, req=req, creds=creds)
    assert creds.calls == []
    assert wire.requests == []


def test_stream_port_raises_before_started_and_never_calls_generate():
    async def scenario():
        creds = Credentials()
        wire = Wire()
        async with OpenAICompatibleChatGateway(
            config(), creds, transport=httpx.MockTransport(wire)
        ) as g:
            stream = g.stream(request(streaming=True))
            with pytest.raises(LLMError) as captured:
                await anext(stream)
            assert captured.value.failure.code is LLMErrorCode.UNSUPPORTED_CAPABILITY
            await stream.aclose()
        assert creds.calls == []
        assert wire.requests == []

    asyncio.run(scenario())


def test_secret_is_resolved_at_each_call_and_not_held_in_configuration_or_headers():
    async def scenario():
        creds = Credentials()
        cfg = config()
        wire = Wire(headers={"set-cookie": f"reflected={CANARY}"})
        async with OpenAICompatibleChatGateway(
            cfg, creds, transport=httpx.MockTransport(wire)
        ) as g:
            assert creds.calls == []
            client = g._client
            for _ in range(2):
                await g.generate(request())
                assert g._client is client
                assert not client.cookies
                assert "authorization" not in client.headers
            assert creds.calls == [cfg.secret_ref, cfg.secret_ref]
            assert CANARY not in repr(g)
            assert CANARY not in repr(cfg)
            assert CANARY not in repr(asdict(cfg))
        assert client.is_closed
        assert all("authorization" not in saved.headers for saved in wire.requests)

    asyncio.run(scenario())


@pytest.mark.parametrize("feature", ["no_secret", "provider_mismatch", "closed"])
def test_configuration_errors_are_local(feature):
    async def scenario():
        cfg = config(secret_ref=None) if feature == "no_secret" else config()
        wire = Wire()
        creds = Credentials()
        async with OpenAICompatibleChatGateway(
            cfg, creds, transport=httpx.MockTransport(wire)
        ) as g:
            req = request()
            if feature == "provider_mismatch":
                req = replace(req, model=ModelRef(ProviderId("different"), "same-model"))
            if feature == "closed":
                await g.aclose()
            with pytest.raises(LLMError) as captured:
                await g.generate(req)
            assert captured.value.failure.code is LLMErrorCode.CONFIGURATION
        assert creds.calls == []
        assert wire.requests == []

    asyncio.run(scenario())


def test_credential_failure_is_normalized_without_exception_context():
    creds = Credentials(error=RuntimeError(CANARY))
    wire = Wire()
    assert_failure(wire, LLMErrorCode.AUTHENTICATION, creds=creds)
    assert len(creds.calls) == 1
    assert wire.requests == []


@pytest.mark.parametrize("secret", ["bad\nkey", "bad key", "非ascii凭据"])
def test_invalid_bearer_header_value_never_reaches_http(secret):
    wire = Wire()
    assert_failure(wire, LLMErrorCode.AUTHENTICATION, creds=Credentials(secret))
    assert wire.requests == []


@pytest.mark.parametrize("name", ["openai_chat", "deepseek_chat"])
def test_controlled_documented_provider_fixtures_use_the_same_adapter(name):
    body = fixture(name)
    req = request()
    result = asyncio.run(
        outcome(Wire(body), req, profile=ChatCompletionsProfile(supports_n=name == "openai_chat"))
    )
    assert result.text == "Controlled answer."
    assert result.invocation_id == req.invocation_id
    assert result.model_used.provider_id == req.model.provider_id
    assert result.model_used.model_id == body["model"]
    assert result.finish_reason is FinishReason.STOP
    assert (result.usage.input_tokens, result.usage.output_tokens, result.usage.total_tokens) == (
        12,
        3,
        15,
    )
    assert result.usage.details["prompt_tokens_details"]["cached_tokens"] == 4
    if name == "deepseek_chat":
        assert result.usage.details["completion_tokens_details"]["reasoning_tokens"] == 2
        assert result.usage.details["prompt_cache_hit_tokens"] == 4
    assert result.structured_result is None
    assert REASONING not in result.text + repr(result) + repr(result.usage.details)
    assert type(result.latency_ms) is int and result.latency_ms >= 0


@pytest.mark.parametrize("reported", [None, {}, {"prompt_tokens": 0}, {"total_tokens": 99}])
def test_absent_or_partial_usage_never_invents_tokens(reported):
    body = fixture()
    if reported is None:
        del body["usage"]
    else:
        body["usage"] = reported
    result = asyncio.run(outcome(Wire(body)))
    if reported is None:
        assert result.usage is None
    else:
        assert result.usage.input_tokens == reported.get("prompt_tokens")
        assert result.usage.output_tokens is None
        assert result.usage.total_tokens == reported.get("total_tokens")


@pytest.mark.parametrize(
    ("finish", "reason"),
    [
        ("stop", FinishReason.STOP),
        ("length", FinishReason.OUTPUT_LIMIT),
        ("content_filter", FinishReason.REFUSAL),
        ("refusal", FinishReason.REFUSAL),
        ("future_finish", FinishReason.UNKNOWN),
        (None, FinishReason.UNKNOWN),
    ],
)
def test_finish_reasons_and_safe_unknown_diagnostic(finish, reason):
    body = fixture()
    body["choices"][0]["finish_reason"] = finish
    result = asyncio.run(outcome(Wire(body)))
    assert result.finish_reason is reason
    if finish == "future_finish":
        assert result.diagnostics.diagnostic_code == "finish:future_finish"


def test_explicit_refusal_is_success_with_usage_not_network_failure():
    body = fixture()
    body["choices"][0]["message"].update(content=None, refusal="Controlled refusal")
    result = asyncio.run(outcome(Wire(body)))
    assert result.finish_reason is FinishReason.REFUSAL
    assert result.text == "Controlled refusal"
    assert result.usage.input_tokens == 12
    assert result.structured_result is None
    body["choices"][0]["message"].update(content="I can't help with that.", refusal=None)
    result = asyncio.run(outcome(Wire(body)))
    assert result.finish_reason is FinishReason.STOP


def test_multiple_choices_use_only_first_array_member():
    body = fixture()
    first = body["choices"][0]
    first["index"] = 7
    second = deepcopy(first)
    second["message"]["content"] = "A different independent result"
    body["choices"].append(second)
    result = asyncio.run(outcome(Wire(body)))
    assert result.text == "Controlled answer."


@pytest.mark.parametrize("finish", ["tool_calls", "function_call"])
def test_unexpected_tool_finish_is_unsupported_without_execution(finish):
    body = fixture()
    body["choices"][0]["finish_reason"] = finish
    assert_failure(Wire(body), LLMErrorCode.UNSUPPORTED_CAPABILITY)


def test_tool_payload_is_not_flattened_even_with_stop_finish():
    body = fixture()
    body["choices"][0]["message"]["tool_calls"] = [{"function": {"arguments": PROMPT}}]
    assert_failure(Wire(body), LLMErrorCode.UNSUPPORTED_CAPABILITY)


@pytest.mark.parametrize(
    "shape",
    [
        "array",
        "object_type",
        "model",
        "choices",
        "empty_choices",
        "choice",
        "index",
        "message",
        "role",
        "content_missing",
        "content_array",
        "content_null",
        "refusal",
        "finish",
        "usage",
        "negative_usage",
        "bool_usage",
        "advanced_usage",
        "model_secret",
        "text_secret",
    ],
)
def test_malformed_success_never_returns_untrusted_partial_data(shape):
    body = fixture()
    choice = body["choices"][0]
    if shape == "array":
        body = []
    elif shape == "object_type":
        body["object"] = "chat.completion.chunk"
    elif shape == "model":
        body["model"] = None
    elif shape == "choices":
        body["choices"] = {}
    elif shape == "empty_choices":
        body["choices"] = []
    elif shape == "choice":
        body["choices"] = [None]
    elif shape == "index":
        choice["index"] = True
    elif shape == "message":
        choice["message"] = None
    elif shape == "role":
        choice["message"]["role"] = "user"
    elif shape == "content_missing":
        del choice["message"]["content"]
    elif shape == "content_array":
        choice["message"]["content"] = [{"type": "image_url"}]
    elif shape == "content_null":
        choice["message"]["content"] = None
    elif shape == "refusal":
        choice["message"]["refusal"] = {}
    elif shape == "finish":
        choice["finish_reason"] = []
    elif shape == "usage":
        body["usage"] = []
    elif shape == "negative_usage":
        body["usage"]["prompt_tokens"] = -1
    elif shape == "bool_usage":
        body["usage"]["completion_tokens"] = False
    elif shape == "advanced_usage":
        body["usage"]["completion_tokens_details"]["reasoning_tokens"] = "1"
    elif shape == "model_secret":
        body["model"] = CANARY
    elif shape == "text_secret":
        choice["message"]["content"] = CANARY
    assert_failure(Wire(body), LLMErrorCode.MALFORMED_RESPONSE)


@pytest.mark.parametrize("content", [b"{invalid", b"null", b'{"value": NaN}', b"\xff"])
def test_invalid_json_is_normalized(content):
    assert_failure(Wire(content=content), LLMErrorCode.MALFORMED_RESPONSE)


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
    ],
)
def test_status_errors_are_normalized_and_never_retry(status, code):
    wire = Wire(
        {"error": {"message": CANARY + PROMPT}}, status=status, headers={"retry-after": "1"}
    )
    error = assert_failure(wire, code)
    assert len(wire.requests) == 1
    assert error.failure.diagnostics.diagnostic_code == f"http:{status}"


@pytest.mark.parametrize(
    ("transport_error", "code"),
    [
        (httpx.ReadTimeout, LLMErrorCode.TIMEOUT),
        (httpx.ConnectTimeout, LLMErrorCode.TIMEOUT),
        (httpx.ConnectError, LLMErrorCode.PROVIDER_UNAVAILABLE),
        (httpx.RemoteProtocolError, LLMErrorCode.PROVIDER_UNAVAILABLE),
    ],
)
def test_transport_errors_are_safe_and_no_second_attempt_occurs(transport_error, code):
    wire = Wire(error=transport_error)
    assert_failure(wire, code)
    assert len(wire.requests) == 1


@pytest.mark.parametrize("field", ["code", "type"])
def test_structured_context_limit_code_maps_without_english_guessing(field):
    wire = Wire({"error": {field: "context_length_exceeded", "message": CANARY}}, status=400)
    assert_failure(wire, LLMErrorCode.CONTEXT_LIMIT)


def test_unclassified_400_does_not_guess_context_from_english():
    wire = Wire({"error": {"message": "maximum context length exceeded"}}, status=400)
    assert_failure(wire, LLMErrorCode.INVALID_REQUEST)


def test_provider_request_id_is_optional_diagnostic_not_invocation():
    req = request()
    result = asyncio.run(outcome(Wire(headers={"x-request-id": "req-controlled"}), req))
    assert result.invocation_id == req.invocation_id
    assert result.diagnostics.provider_request_id == "req-controlled"
    result = asyncio.run(outcome(Wire(), req))
    assert result.diagnostics.provider_request_id == fixture()["id"]
    body = fixture()
    del body["id"]
    assert asyncio.run(outcome(Wire(body))).diagnostics.provider_request_id is None


@pytest.mark.parametrize("unsafe", [CANARY, PROMPT, "x" * 129, "https://unsafe.example", "bad\nID"])
def test_unsafe_diagnostics_are_omitted_not_logged(unsafe):
    body = fixture()
    body["id"] = unsafe
    body["choices"][0]["finish_reason"] = unsafe
    result = asyncio.run(outcome(Wire(body, headers={"x-request-id": unsafe})))
    assert result.diagnostics.provider_request_id is None
    assert result.diagnostics.diagnostic_code == "unknown_finish_reason"


def test_success_and_error_logs_exclude_credentials_prompt_response_and_reasoning(caplog):
    caplog.set_level("DEBUG")
    stream = StringIO()
    logger = StructuredLogger(stream)
    body = fixture("deepseek_chat")
    body["choices"][0]["message"]["content"] = RESPONSE
    req = request()
    result = asyncio.run(outcome(Wire(body), req, logger=logger))
    assert_failure(
        Wire({"error": {"message": CANARY + PROMPT + RESPONSE}}, status=401),
        LLMErrorCode.AUTHENTICATION,
        logger=logger,
    )
    log = stream.getvalue() + caplog.text
    for protected in (CANARY, PROMPT, RESPONSE, REASONING, "Authorization", "Bearer"):
        assert protected not in log
    assert CANARY not in repr(req) + repr(result) + repr(result.diagnostics)
    records = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert records[0]["trace_id"] == str(req.invocation_id.value)
    assert records[0]["event"] == "chat_completed"
    assert records[1]["event"] == "chat_authentication"
    assert all(
        set(record) == {"timestamp", "level", "component", "event", "trace_id"}
        for record in records
    )


def test_http_cancellation_propagates_and_scrubs_header_without_retry():
    async def scenario():
        started = asyncio.Event()
        cancelled = asyncio.Event()
        requests = []

        async def handler(wire):
            requests.append(wire)
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise

        async with OpenAICompatibleChatGateway(
            config(), Credentials(), transport=httpx.MockTransport(handler)
        ) as g:
            task = asyncio.create_task(g.generate(request()))
            await started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert cancelled.is_set()
            assert len(requests) == 1
            assert "authorization" not in requests[0].headers

    asyncio.run(scenario())


def test_credential_resolution_cancellation_is_not_swallowed():
    async def scenario():
        started = asyncio.Event()

        class WaitingCredentials:
            async def resolve(self, _):
                started.set()
                await asyncio.Event().wait()

        wire = Wire()
        async with OpenAICompatibleChatGateway(
            config(), WaitingCredentials(), transport=httpx.MockTransport(wire)
        ) as g:
            task = asyncio.create_task(g.generate(request()))
            await started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert wire.requests == []

    asyncio.run(scenario())


def test_existing_fake_port_still_works_and_models_have_no_name_heuristics():
    async def scenario():
        req = request()
        fake: ModelGateway = FakeModelGateway(chunks=("controlled", " fake"))
        assert (await fake.generate(req)).text == "controlled fake"
        for model in ("opaque", "contains-deepseek", "contains-gpt", "o3-like-name"):
            wire = Wire()
            await outcome(wire, replace(req, model=ModelRef(req.model.provider_id, model)))
            assert wire.payloads[0]["model"] == model
            assert "thinking" not in wire.payloads[0]
            assert "reasoning_effort" not in wire.payloads[0]

    asyncio.run(scenario())
