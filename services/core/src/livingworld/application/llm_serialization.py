"""Explicit local request round-trip codec, not a provider wire schema or a logger."""

from collections.abc import Mapping
from uuid import UUID

from livingworld.application.llm import (
    InvocationId,
    LLMContractError,
    LLMMessage,
    LLMPurpose,
    LLMRequest,
    MessageRole,
    ModelRef,
    ProviderId,
    StructuredOutputRequest,
    TextContent,
    _type,
)
from livingworld.domain.identifiers import CorrelationId


def _json_data(value):
    if isinstance(value, Mapping):
        return {key: _json_data(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [_json_data(child) for child in value]
    return value


def request_to_data(request: LLMRequest) -> dict:
    _type(request, LLMRequest, "llm_request")
    return {
        "invocation_id": request.invocation_id.value.hex,
        "model": {
            "provider_id": request.model.provider_id.value,
            "model_id": request.model.model_id,
        },
        "purpose": request.purpose.value,
        "messages": [
            {
                "role": message.role.value,
                "content": [{"kind": "text", "text": block.text} for block in message.content],
            }
            for message in request.messages
        ],
        "max_output_tokens": request.max_output_tokens,
        "streaming": request.streaming,
        "structured_output": {
            "schema_name": request.structured_output.schema_name,
            "schema": _json_data(request.structured_output.schema),
        }
        if request.structured_output
        else None,
        "stop_sequences": list(request.stop_sequences),
        "correlation_id": request.correlation_id.value.hex if request.correlation_id else None,
        "metadata": _json_data(request.metadata),
        "temperature": request.temperature,
    }


def _keys(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise LLMContractError("invalid_request_encoding")
    return value


def _uuid(value):
    if type(value) is not str:
        raise LLMContractError("invalid_request_encoding")
    result = UUID(hex=value)
    if result.hex != value:
        raise LLMContractError("invalid_request_encoding")
    return result


def request_from_data(value: dict) -> LLMRequest:
    try:
        required = {
            "invocation_id",
            "model",
            "purpose",
            "messages",
            "max_output_tokens",
            "streaming",
            "structured_output",
            "stop_sequences",
            "correlation_id",
            "metadata",
        }
        if (
            type(value) is not dict
            or not required <= set(value)
            or (set(value) - required) - {"temperature"}
        ):
            raise LLMContractError("invalid_request_encoding")
        data = dict(value)
        data.setdefault("temperature", None)
        model = _keys(data["model"], {"provider_id", "model_id"})
        if type(data["messages"]) is not list:
            raise LLMContractError("invalid_request_encoding")
        messages = []
        for message in data["messages"]:
            _keys(message, {"role", "content"})
            if type(message["content"]) is not list:
                raise LLMContractError("invalid_request_encoding")
            blocks = []
            for block in message["content"]:
                _keys(block, {"kind", "text"})
                if block["kind"] != "text":
                    raise LLMContractError("unsupported_content_kind")
                blocks.append(TextContent(block["text"]))
            messages.append(LLMMessage(MessageRole(message["role"]), tuple(blocks)))
        structured = data["structured_output"]
        if structured is not None:
            _keys(structured, {"schema_name", "schema"})
            structured = StructuredOutputRequest(structured["schema_name"], structured["schema"])
        return LLMRequest(
            invocation_id=InvocationId(_uuid(data["invocation_id"])),
            model=ModelRef(ProviderId(model["provider_id"]), model["model_id"]),
            purpose=LLMPurpose(data["purpose"]),
            messages=tuple(messages),
            max_output_tokens=data["max_output_tokens"],
            streaming=data["streaming"],
            structured_output=structured,
            stop_sequences=data["stop_sequences"],
            correlation_id=CorrelationId(_uuid(data["correlation_id"]))
            if data["correlation_id"] is not None
            else None,
            metadata=data["metadata"],
            temperature=data["temperature"],
        )
    except (ValueError, TypeError, KeyError, AttributeError):
        raise LLMContractError("invalid_request_encoding") from None
