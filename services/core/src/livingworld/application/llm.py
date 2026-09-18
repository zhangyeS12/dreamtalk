"""LivingWorld-owned text generation contracts. No providers, IO or world capabilities."""

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from livingworld.domain.errors import DomainInvariantError
from livingworld.domain.identifiers import CorrelationId
from livingworld.domain.values import JsonValue, freeze_json


class LLMContractError(ValueError):
    """Reports structural labels only, never the rejected value or provider exception."""


def _type(value, expected, label):
    if not isinstance(value, expected):
        raise LLMContractError(f"invalid_{label}")


def _text(value, label):
    if type(value) is not str or not value.strip():
        raise LLMContractError(f"invalid_{label}")


def _count(value, label, *, minimum=0):
    if type(value) is not int or value < minimum:
        raise LLMContractError(f"invalid_{label}")


def _json_object(value):
    if not isinstance(value, Mapping):
        raise LLMContractError("invalid_json_object")
    try:
        return freeze_json(value)
    except DomainInvariantError:
        raise LLMContractError("invalid_json_object") from None


@dataclass(frozen=True, slots=True)
class ProviderId:
    value: str

    def __post_init__(self):
        _text(self.value, "provider_id")


@dataclass(frozen=True, slots=True)
class LLMPurpose:
    """An explicit application label, open to new uses without an exhaustive enum."""

    value: str

    def __post_init__(self):
        _text(self.value, "purpose")


@dataclass(frozen=True, slots=True)
class InvocationId:
    value: UUID

    def __post_init__(self):
        _type(self.value, UUID, "invocation_id")


@dataclass(frozen=True, slots=True)
class ModelRef:
    provider_id: ProviderId
    model_id: str

    def __post_init__(self):
        _type(self.provider_id, ProviderId, "provider_id")
        _text(self.model_id, "model_id")


class MessageRole(StrEnum):
    SYSTEM = "system"
    DEVELOPER = "developer"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class TextContent:
    text: str = field(repr=False)

    def __post_init__(self):
        if type(self.text) is not str:
            raise LLMContractError("invalid_text_content")


# A closed typed union can gain new LivingWorld blocks later; no opaque provider block.
type LLMContent = TextContent


def _content(value):
    if not isinstance(value, (list, tuple)) or any(
        not isinstance(item, TextContent) for item in value
    ):
        raise LLMContractError("invalid_content_blocks")
    return tuple(value)


@dataclass(frozen=True, slots=True)
class LLMMessage:
    role: MessageRole
    content: tuple[LLMContent, ...] = field(repr=False)

    def __post_init__(self):
        _type(self.role, MessageRole, "message_role")
        object.__setattr__(self, "content", _content(self.content))
        if not self.content:
            raise LLMContractError("empty_message_content")


@dataclass(frozen=True, slots=True)
class StructuredOutputRequest:
    schema_name: str
    schema: Mapping[str, JsonValue] = field(repr=False)

    def __post_init__(self):
        _text(self.schema_name, "schema_name")
        object.__setattr__(self, "schema", _json_object(self.schema))
        # This carries a JSON Schema document; schema/instance validation is C-005C.


@dataclass(frozen=True, slots=True, kw_only=True)
class LLMRequest:
    invocation_id: InvocationId
    model: ModelRef
    purpose: LLMPurpose
    messages: tuple[LLMMessage, ...] = field(repr=False)
    max_output_tokens: int
    streaming: bool = False
    structured_output: StructuredOutputRequest | None = field(default=None, repr=False)
    stop_sequences: tuple[str, ...] = field(default=(), repr=False)
    correlation_id: CorrelationId | None = None
    metadata: Mapping[str, JsonValue] = field(default_factory=dict, repr=False)

    def __post_init__(self):
        _type(self.invocation_id, InvocationId, "invocation_id")
        _type(self.model, ModelRef, "model_ref")
        _type(self.purpose, LLMPurpose, "purpose")
        _count(self.max_output_tokens, "output_budget", minimum=1)
        if type(self.streaming) is not bool:
            raise LLMContractError("invalid_streaming_flag")
        if self.structured_output is not None:
            _type(self.structured_output, StructuredOutputRequest, "structured_output")
        if self.correlation_id is not None:
            _type(self.correlation_id, CorrelationId, "correlation_id")
        if not isinstance(self.messages, (list, tuple)) or not self.messages:
            raise LLMContractError("invalid_messages")
        for message in self.messages:
            _type(message, LLMMessage, "message")
        object.__setattr__(self, "messages", tuple(self.messages))
        if not isinstance(self.stop_sequences, (list, tuple)):
            raise LLMContractError("invalid_stop_sequences")
        for stop in self.stop_sequences:
            _text(stop, "stop_sequence")
        object.__setattr__(self, "stop_sequences", tuple(self.stop_sequences))
        object.__setattr__(self, "metadata", _json_object(self.metadata))


@dataclass(frozen=True, slots=True)
class LLMUsage:
    """None means unreported, not zero. Details are provider facts, never prices."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    details: Mapping[str, JsonValue] = field(default_factory=dict, repr=False)

    def __post_init__(self):
        for label in ("input_tokens", "output_tokens", "total_tokens"):
            value = getattr(self, label)
            if value is not None:
                _count(value, label)
        # Do not fabricate totals or enforce a provider-specific category relationship.
        object.__setattr__(self, "details", _json_object(self.details))


@dataclass(frozen=True, slots=True)
class ProviderDiagnostics:
    """Selected nonsecret identifiers; no raw headers, bodies or SDK objects."""

    provider_request_id: str | None = field(default=None, repr=False)
    diagnostic_code: str | None = field(default=None, repr=False)

    def __post_init__(self):
        for label in ("provider_request_id", "diagnostic_code"):
            value = getattr(self, label)
            if value is not None:
                _text(value, label)


class FinishReason(StrEnum):
    STOP = "stop"
    OUTPUT_LIMIT = "output_limit"
    REFUSAL = "refusal"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ValidatedStructuredResult:
    """A trusted validator's output claim, not a parser or validator in C-005A."""

    schema_name: str
    value: JsonValue = field(repr=False)

    def __post_init__(self):
        _text(self.schema_name, "schema_name")
        try:
            object.__setattr__(self, "value", freeze_json(self.value))
        except DomainInvariantError:
            raise LLMContractError("invalid_structured_value") from None


@dataclass(frozen=True, slots=True, kw_only=True)
class LLMResponse:
    invocation_id: InvocationId
    model_used: ModelRef
    content: tuple[LLMContent, ...] = field(repr=False)
    finish_reason: FinishReason
    usage: LLMUsage | None = None
    structured_result: ValidatedStructuredResult | None = field(default=None, repr=False)
    diagnostics: ProviderDiagnostics = field(default_factory=ProviderDiagnostics, repr=False)
    latency_ms: int | None = None

    def __post_init__(self):
        _type(self.invocation_id, InvocationId, "invocation_id")
        _type(self.model_used, ModelRef, "model_ref")
        _type(self.finish_reason, FinishReason, "finish_reason")
        object.__setattr__(self, "content", _content(self.content))
        _type(self.diagnostics, ProviderDiagnostics, "provider_diagnostics")
        if self.usage is not None:
            _type(self.usage, LLMUsage, "usage")
        if self.structured_result is not None:
            _type(self.structured_result, ValidatedStructuredResult, "structured_result")
            if self.finish_reason is FinishReason.REFUSAL:
                raise LLMContractError("refusal_cannot_be_validated_result")
        if self.latency_ms is not None:
            _count(self.latency_ms, "latency")

    @property
    def text(self) -> str:
        return "".join(block.text for block in self.content)


class LLMErrorCode(StrEnum):
    AUTHENTICATION = "authentication"
    CONFIGURATION = "configuration"
    UNSUPPORTED_CAPABILITY = "unsupported_capability"
    INVALID_REQUEST = "invalid_request"
    RATE_LIMITED = "rate_limited"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    TIMEOUT = "timeout"
    CONTEXT_LIMIT = "context_limit"
    MALFORMED_RESPONSE = "malformed_response"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class LLMFailure:
    code: LLMErrorCode
    invocation_id: InvocationId
    diagnostics: ProviderDiagnostics = field(default_factory=ProviderDiagnostics, repr=False)

    def __post_init__(self):
        _type(self.code, LLMErrorCode, "error_code")
        _type(self.invocation_id, InvocationId, "invocation_id")
        _type(self.diagnostics, ProviderDiagnostics, "provider_diagnostics")


class LLMError(Exception):
    def __init__(self, failure: LLMFailure):
        _type(failure, LLMFailure, "llm_failure")
        self.failure = failure
        super().__init__(failure.code.value)


@dataclass(frozen=True, slots=True)
class ModelCapabilities:
    text_generation: bool = False
    streaming: bool = False
    structured_output: bool = False
    vision: bool = False
    tool_calling: bool = False
    reasoning_controls: bool = False

    def __post_init__(self):
        for label in self.__slots__:
            if type(getattr(self, label)) is not bool:
                raise LLMContractError("invalid_capability_flag")


class ModelCatalog(Protocol):
    def capabilities(self, model: ModelRef) -> ModelCapabilities | None: ...


@dataclass(frozen=True, slots=True)
class StreamStarted:
    invocation_id: InvocationId
    model_used: ModelRef

    def __post_init__(self):
        _type(self.invocation_id, InvocationId, "invocation_id")
        _type(self.model_used, ModelRef, "model_ref")


@dataclass(frozen=True, slots=True)
class TextDelta:
    invocation_id: InvocationId
    text: str = field(repr=False)

    def __post_init__(self):
        _type(self.invocation_id, InvocationId, "invocation_id")
        if type(self.text) is not str:
            raise LLMContractError("invalid_text_delta")


@dataclass(frozen=True, slots=True)
class UsageUpdate:
    invocation_id: InvocationId
    usage: LLMUsage

    def __post_init__(self):
        _type(self.invocation_id, InvocationId, "invocation_id")
        _type(self.usage, LLMUsage, "usage")


@dataclass(frozen=True, slots=True)
class StreamCompleted:
    response: LLMResponse

    def __post_init__(self):
        _type(self.response, LLMResponse, "response")


@dataclass(frozen=True, slots=True)
class StreamFailed:
    failure: LLMFailure

    def __post_init__(self):
        _type(self.failure, LLMFailure, "llm_failure")


type LLMStreamEvent = StreamStarted | TextDelta | UsageUpdate | StreamCompleted | StreamFailed


class ModelGateway(Protocol):
    """Cancellation propagates via asyncio; stream returns an async iterator directly."""

    async def generate(self, request: LLMRequest) -> LLMResponse: ...
    def stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamEvent]: ...
