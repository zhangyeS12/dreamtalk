"""Offline structured boundary: controlled fixtures, one transport attempt, no real keys."""

import asyncio
import json
from collections.abc import Mapping
from dataclasses import FrozenInstanceError, fields, replace
from io import StringIO
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from livingworld.application.llm import (
    FinishReason,
    LLMAttemptSummary,
    LLMContractError,
    LLMError,
    LLMErrorCode,
    LLMFailure,
    LLMResponse,
    LLMUsage,
    ModelCapabilities,
    StructuredFailureDetail,
    StructuredFailureReason,
    StructuredOutputMode,
    StructuredOutputRequest,
)
from livingworld.infrastructure.llm.openai_compatible import (
    ChatCompletionsProfile,
    OpenAICompatibleChatGateway,
)
from livingworld.infrastructure.llm.structured import (
    DIALECT,
    InvalidStructuredSchema,
    prepare_schema,
    validate_text,
)
from livingworld.infrastructure.logging import StructuredLogger
from test_openai_compatible import CANARY, PROMPT, Credentials, Wire, config, fixture, request

OUTPUT = "LW_PRIVATE_OUTPUT_C005C1_CANARY"
MODES = [StructuredOutputMode.NATIVE_JSON_SCHEMA, StructuredOutputMode.JSON_OBJECT_LOCAL_VALIDATE]
SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "integer"}},
    "required": ["answer"],
    "additionalProperties": False,
}


def structured(schema=None):
    return request(structured_output=StructuredOutputRequest("synthetic_answer", schema or SCHEMA))


def body(text='{"answer":42}', finish="stop", refusal=None):
    result = fixture()
    result["choices"][0]["message"] = {"role": "assistant", "content": text}
    result["choices"][0]["finish_reason"] = finish
    if refusal is not None:
        result["choices"][0]["message"]["refusal"] = refusal
    return result


async def generate(wire, req=None, *, mode=MODES[0], creds=None, logger=None):
    async with OpenAICompatibleChatGateway(
        config(),
        creds or Credentials(),
        profile=ChatCompletionsProfile(structured_output_mode=mode),
        transport=httpx.MockTransport(wire),
        logger=logger,
    ) as gateway:
        return await gateway.generate(req or structured())


def failure(wire, reason, **kwargs):
    with pytest.raises(LLMError) as captured:
        asyncio.run(generate(wire, **kwargs))
    error = captured.value
    assert error.failure.code is LLMErrorCode.STRUCTURED_OUTPUT_FAILED
    assert error.failure.structured_detail.reason is reason
    assert error.__context__ is None and error.__cause__ is None
    assert len(wire.requests) == 1
    assert "authorization" not in wire.requests[0].headers
    return error.failure


def plain(value):
    """Explicitly inspect every field, including fields hidden from repr."""
    if isinstance(value, Mapping):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [plain(item) for item in value]
    if isinstance(value, UUID):
        return str(value)
    if hasattr(value, "__dataclass_fields__"):
        return {field.name: plain(getattr(value, field.name)) for field in fields(value)}
    return value


@pytest.mark.parametrize("mode", list(StructuredOutputMode))
def test_mode_is_explicit_immutable_and_reported(mode):
    profile = ChatCompletionsProfile(structured_output_mode=mode)
    gateway = OpenAICompatibleChatGateway(config(), Credentials(), profile=profile)
    assert gateway.capabilities.structured_output_mode is mode
    assert gateway.capabilities.structured_output is (mode is not StructuredOutputMode.NONE)
    with pytest.raises(FrozenInstanceError):
        profile.structured_output_mode = StructuredOutputMode.NONE
    asyncio.run(gateway.aclose())
    with pytest.raises(LLMContractError):
        ChatCompletionsProfile(structured_output_mode=mode.value)
    if mode is not StructuredOutputMode.NONE:
        with pytest.raises(LLMContractError):
            ModelCapabilities(structured_output_mode=mode)


@pytest.mark.parametrize("mode", MODES)
def test_exact_wire_mapping_and_messages_unchanged(mode):
    req = structured()
    wire = Wire(body())
    result = asyncio.run(generate(wire, req, mode=mode))
    expected = (
        {"type": "json_object"}
        if mode is MODES[1]
        else {
            "type": "json_schema",
            "json_schema": {
                "name": "synthetic_answer",
                "strict": True,
                "schema": SCHEMA,
            },
        }
    )
    assert len(wire.requests) == 1
    assert wire.payloads[0]["response_format"] == expected
    assert wire.payloads[0]["messages"] == [
        {"role": message.role.value, "content": "".join(b.text for b in message.content)}
        for message in req.messages
    ]
    assert result.text == '{"answer":42}'
    assert result.structured_result.schema_name == "synthetic_answer"
    assert result.structured_result.value == {"answer": 42}
    assert result.usage.input_tokens == body()["usage"]["prompt_tokens"]
    assert result.model_used.model_id == body()["model"]
    assert result.latency_ms >= 0
    assert plain(req.structured_output.schema) == SCHEMA
    assert "authorization" not in wire.requests[0].headers


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "unrecognized"},
        {"type": 42},
        {"required": "answer"},
        {"$schema": "http://json-schema.org/draft-07/schema#", "type": "object"},
        {"type": "object", "properties": {"answer": {"$schema": "urn:private-dialect"}}},
        {"type": "object", "$ref": "https://private.example/schema"},
        {"type": "object", "$ref": "file:///private/schema"},
        {"type": "object", "$ref": "relative.json"},
        {"type": "object", "$dynamicRef": "https://private.example/schema"},
        {"type": "object", "properties": {"answer": {"$ref": "https://private.example/schema"}}},
        {"type": "object", "$ref": "#/$defs/missing"},
        {"type": "object", "$ref": "#/default", "default": 42},
        {
            "type": "object",
            "$ref": "#/examples/0",
            "examples": [
                {"$ref": "https://private.example/schema"},
            ],
        },
        {"type": "object", "properties": {"answer": {"pattern": "["}}},
    ],
)
def test_invalid_schema_precedes_credentials_and_network(schema, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("schema resolution must not access network or filesystem")

    wire = Wire(body())
    creds = Credentials()
    monkeypatch.setattr(httpx, "get", forbidden)
    monkeypatch.setattr(Path, "read_text", forbidden)
    with pytest.raises(LLMError) as captured:
        asyncio.run(generate(wire, structured(schema), creds=creds))
    assert captured.value.failure.code is LLMErrorCode.INVALID_REQUEST
    assert captured.value.failure.attempt is None
    assert captured.value.__context__ is None
    assert wire.requests == [] and creds.calls == []


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("root", ["array", "string", "number", "boolean", "null"])
def test_narrow_transport_does_not_rewrite_general_roots(mode, root):
    wire = Wire(body())
    creds = Credentials()
    with pytest.raises(LLMError) as captured:
        asyncio.run(generate(wire, structured({"type": root}), mode=mode, creds=creds))
    assert captured.value.failure.code is LLMErrorCode.UNSUPPORTED_CAPABILITY
    assert creds.calls == [] and wire.requests == []


def test_none_rejects_before_credentials():
    wire = Wire(body())
    creds = Credentials()
    with pytest.raises(LLMError) as captured:
        asyncio.run(generate(wire, mode=StructuredOutputMode.NONE, creds=creds))
    assert captured.value.failure.code is LLMErrorCode.UNSUPPORTED_CAPABILITY
    assert creds.calls == [] and wire.requests == []


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize(
    "text,keyword",
    [
        ('{"answer":"42"}', "type"),
        ("{}", "required"),
        ('{"answer":42,"extra":true}', "additionalProperties"),
    ],
)
def test_schema_failure_preserves_completed_facts(mode, text, keyword):
    result = failure(Wire(body(text)), StructuredFailureReason.SCHEMA_VALIDATION_FAILED, mode=mode)
    assert result.structured_detail.validator_keyword == keyword
    summary = result.attempt
    assert isinstance(summary, LLMAttemptSummary)
    assert summary.usage.input_tokens == body()["usage"]["prompt_tokens"]
    assert summary.usage.output_tokens == body()["usage"]["completion_tokens"]
    assert summary.usage.total_tokens == body()["usage"]["total_tokens"]
    assert summary.usage.details["prompt_tokens_details"]["cached_tokens"] == 4
    assert summary.model.model_id == body()["model"]
    assert summary.finish_reason is FinishReason.STOP and summary.latency_ms >= 0


@pytest.mark.parametrize(
    "text",
    [
        "{",
        '{"answer":42}garbage',
        '{"answer":NaN}',
        '{"answer":Infinity}',
        '{"answer":-Infinity}',
        '{"answer":1e999}',
        '{"answer":42,"answer":43}',
        '{"answer":42,"nested":{"x":1,"x":2}}',
        '```json\n{"answer":42}\n```',
        'Here is {"answer":42}',
        "{'answer':42}",
        '{"answer":42,}',
        "{} {}",
    ],
)
def test_strict_parse_failure_retains_usage_without_output(text):
    result = failure(Wire(body(text)), StructuredFailureReason.JSON_PARSE_FAILED)
    assert result.attempt.usage.total_tokens == body()["usage"]["total_tokens"]
    assert set(plain(result.attempt)) == {
        "model",
        "usage",
        "finish_reason",
        "latency_ms",
        "processing_tier",
    }
    assert not hasattr(result, "attempt_response")
    assert not hasattr(result.attempt, "content")


@pytest.mark.parametrize("text", ["", " ", "\n\t "])
def test_empty_output_has_its_own_reason(text):
    result = failure(Wire(body(text)), StructuredFailureReason.EMPTY_OUTPUT)
    assert result.attempt.usage is not None


@pytest.mark.parametrize("text", ['{"answer":', '{"answer":42}', "", None])
def test_length_precedes_json_validation_and_keeps_usage(text):
    result = failure(Wire(body(text, "length")), StructuredFailureReason.OUTPUT_TRUNCATED)
    assert result.attempt.finish_reason is FinishReason.OUTPUT_LIMIT
    assert result.attempt.usage.total_tokens == body()["usage"]["total_tokens"]


@pytest.mark.parametrize(
    "finish,refusal,text",
    [
        ("stop", OUTPUT, None),
        ("content_filter", None, None),
        ("refusal", None, "not JSON"),
        ("length", OUTPUT, "{broken"),
    ],
)
def test_recognized_refusal_filter_remains_response(finish, refusal, text):
    result = asyncio.run(generate(Wire(body(text, finish, refusal))))
    assert isinstance(result, LLMResponse) and result.finish_reason is FinishReason.REFUSAL
    assert result.structured_result is None and result.usage is not None


@pytest.mark.parametrize(
    "error,status,code",
    [
        (None, 401, LLMErrorCode.AUTHENTICATION),
        (httpx.ConnectError, 200, LLMErrorCode.PROVIDER_UNAVAILABLE),
        (httpx.ReadTimeout, 200, LLMErrorCode.TIMEOUT),
    ],
)
def test_pre_response_failures_do_not_invent_attempt(error, status, code):
    wire = Wire(body(), status=status, error=error)
    with pytest.raises(LLMError) as captured:
        asyncio.run(generate(wire))
    assert captured.value.failure.code is code
    assert captured.value.failure.attempt is None
    assert captured.value.__context__ is None
    assert len(wire.requests) == 1


@pytest.mark.parametrize(
    "schema,text,expected",
    [
        ({"type": "array", "items": {"type": "integer"}}, "[1,2]", (1, 2)),
        ({"type": "string"}, '"hello"', "hello"),
        ({"type": "number"}, "1.5", 1.5),
        ({"type": "integer"}, "42", 42),
        ({"type": "boolean"}, "true", True),
        ({"type": "null"}, "null", None),
    ],
)
def test_local_validator_supports_all_schema_permitted_roots(schema, text, expected):
    req = StructuredOutputRequest("synthetic_root", schema)
    assert validate_text(req, prepare_schema(req), text).value == expected


def test_local_refs_dialect_and_format_annotation_policy():
    req = StructuredOutputRequest(
        "local_ref",
        {
            "$schema": DIALECT,
            "type": "object",
            "$defs": {"mail": {"type": "string", "format": "email"}},
            "properties": {"answer": {"$ref": "#/$defs/mail"}},
        },
    )
    result = asyncio.run(
        generate(
            Wire(body('{"answer":"not-an-email"}')),
            request(
                structured_output=req,
            ),
        )
    )
    assert result.structured_result.value == {"answer": "not-an-email"}


def test_annotation_data_is_not_mistaken_for_schema_references():
    req = StructuredOutputRequest(
        "annotation",
        {
            "type": "object",
            "examples": [{"$ref": "https://example.invalid/data"}],
            "properties": {"$ref": {"type": "string"}},
        },
    )
    assert prepare_schema(req) is not None


def test_recursive_local_schema_reference_is_preflighted_once():
    req = structured(
        {
            "type": "object",
            "properties": {
                "children": {"type": "array", "items": {"$ref": "#"}},
            },
        }
    )
    text = '{"children":[{"children":[]}]}'
    response = asyncio.run(generate(Wire(body(text)), req))
    assert response.structured_result.value["children"][0]["children"] == ()


def test_defaults_are_not_inserted_or_values_coerced():
    req = structured(
        {
            "type": "object",
            "properties": {"answer": {"type": "integer", "default": 42}},
        }
    )
    result = asyncio.run(generate(Wire(body("{}")), req))
    assert result.structured_result.value == {} and result.text == "{}"


def test_nested_path_is_bounded_and_keys_never_serialize_private_data():
    schema = {
        "type": "object",
        "properties": {
            "rows": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        OUTPUT: {"type": "integer"},
                    },
                },
            }
        },
    }
    text = json.dumps({"rows": [{OUTPUT: "wrong-type"}]})
    result = failure(
        Wire(body(text)), StructuredFailureReason.SCHEMA_VALIDATION_FAILED, req=structured(schema)
    )
    assert result.structured_detail.instance_path == ("*", 0, "*")
    assert len(result.structured_detail.schema_path) <= 16
    assert OUTPUT not in json.dumps(plain(result))


@pytest.mark.parametrize("reason_text", [OUTPUT, json.dumps({"answer": OUTPUT})])
def test_errors_summary_and_logs_exclude_all_content_canaries(reason_text, caplog):
    logs = StringIO()
    caplog.set_level("DEBUG")
    wire = Wire(body(reason_text), headers={"x-request-id": OUTPUT})
    with pytest.raises(LLMError) as captured:
        asyncio.run(generate(wire, logger=StructuredLogger(logs)))
    error = captured.value
    summary = error.failure.attempt
    visible = json.dumps(plain(error.failure)) + repr(summary) + repr(error) + logs.getvalue()
    visible += caplog.text
    for canary in (CANARY, PROMPT, OUTPUT, reason_text):
        assert canary not in visible
    assert error.__context__ is None and error.__cause__ is None
    assert not hasattr(summary, "__dict__")
    with pytest.raises(FrozenInstanceError):
        summary.latency_ms = 2


def test_attempt_usage_projects_only_closed_numeric_counters():
    response_usage = LLMUsage(
        2,
        3,
        5,
        {
            "raw_output": OUTPUT,
            PROMPT: CANARY,
            "completion_tokens_details": {"reasoning_tokens": 1, "text": OUTPUT},
        },
    )
    summary = LLMAttemptSummary(request().model, response_usage, FinishReason.STOP, 0)
    assert summary.usage.details == {"completion_tokens_details": {"reasoning_tokens": 1}}
    visible = json.dumps(plain(summary)) + repr(summary)
    assert all(canary not in visible for canary in (CANARY, PROMPT, OUTPUT))
    assert "raw_output" in response_usage.details  # Original usage is not mutated.
    with pytest.raises(LLMContractError):
        replace(summary, usage=LLMUsage(details={"prompt_cache_hit_tokens": OUTPUT}))
    with pytest.raises(LLMContractError):
        LLMFailure(LLMErrorCode.MALFORMED_RESPONSE, request().invocation_id, attempt=object())


def test_missing_usage_stays_unknown_after_postprocessing_failure():
    raw = body(OUTPUT)
    raw.pop("usage")
    result = failure(Wire(raw), StructuredFailureReason.JSON_PARSE_FAILED)
    assert result.attempt.usage is None


def test_credential_failure_has_no_attempt_or_network():
    wire = Wire(body())
    with pytest.raises(LLMError) as captured:
        asyncio.run(generate(wire, creds=Credentials(error=ValueError(CANARY))))
    assert captured.value.failure.code is LLMErrorCode.AUTHENTICATION
    assert captured.value.failure.attempt is None
    assert captured.value.__context__ is None
    assert wire.requests == []


def test_full_response_is_not_an_attempt_summary():
    response = asyncio.run(generate(Wire(body())))
    with pytest.raises(LLMContractError):
        LLMFailure(LLMErrorCode.STRUCTURED_OUTPUT_FAILED, response.invocation_id, attempt=response)


def test_native_root_anyof_is_unsupported_before_network():
    wire = Wire(body())
    with pytest.raises(LLMError) as captured:
        asyncio.run(generate(wire, structured({"type": "object", "anyOf": [SCHEMA]})))
    assert captured.value.failure.code is LLMErrorCode.UNSUPPORTED_CAPABILITY
    assert wire.requests == []


def test_paths_are_bounded_even_for_deep_validation_failure():
    schema = {"type": "integer"}
    value = "wrong-type"
    for _ in range(24):
        schema = {"type": "object", "properties": {"nested": schema}}
        value = {"nested": value}
    result = failure(
        Wire(body(json.dumps(value))),
        StructuredFailureReason.SCHEMA_VALIDATION_FAILED,
        req=structured(schema),
    )
    assert len(result.structured_detail.instance_path) == 16
    assert len(result.structured_detail.schema_path) == 16


def test_valid_json_whitespace_preserves_raw_text():
    text = ' \n{"answer":42}\t '
    response = asyncio.run(generate(Wire(body(text))))
    assert response.text == text
    assert response.structured_result.value == {"answer": 42}


@pytest.mark.parametrize(
    "name,mode", [("openai_structured", MODES[0]), ("deepseek_structured", MODES[1])]
)
def test_controlled_vendor_fixtures(name, mode):
    path = Path(__file__).parent / "fixtures/llm" / f"{name}.json"
    raw = json.loads(path.read_text("utf-8"))
    result = asyncio.run(generate(Wire(raw), mode=mode))
    assert result.structured_result.value == {"answer": 42}
    assert result.usage.total_tokens == raw["usage"]["total_tokens"]


def test_invalid_schema_public_error_does_not_keep_library_exception():
    req = StructuredOutputRequest("private", {"type": OUTPUT})
    with pytest.raises(InvalidStructuredSchema) as captured:
        prepare_schema(req)
    assert captured.value.__context__ is None
    assert OUTPUT not in str(captured.value)


def test_failure_path_contract_rejects_unredacted_keys():
    with pytest.raises(LLMContractError):
        StructuredFailureDetail(StructuredFailureReason.SCHEMA_VALIDATION_FAILED, (OUTPUT,))
