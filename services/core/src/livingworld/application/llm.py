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
        # Schema/dialect validation belongs to the infrastructure validator.


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
    STRUCTURED_OUTPUT_FAILED = "structured_output_failed"


class StructuredOutputMode(StrEnum):
    NONE = "none"
    NATIVE_JSON_SCHEMA = "native_json_schema"
    JSON_OBJECT_LOCAL_VALIDATE = "json_object_local_validate"


class StructuredFailureReason(StrEnum):
    JSON_PARSE_FAILED = "json_parse_failed"
    SCHEMA_VALIDATION_FAILED = "schema_validation_failed"
    OUTPUT_TRUNCATED = "output_truncated"
    EMPTY_OUTPUT = "empty_output"


@dataclass(frozen=True, slots=True)
class StructuredFailureDetail:
    """Bounded locations: object keys are redacted, array indices remain useful."""

    reason: StructuredFailureReason
    instance_path: tuple[str | int, ...] = ()
    schema_path: tuple[str | int, ...] = ()
    validator_keyword: str | None = None

    def __post_init__(self):
        _type(self.reason, StructuredFailureReason, "structured_failure_reason")
        for label in ("instance_path", "schema_path"):
            path = getattr(self, label)
            if (
                type(path) is not tuple
                or len(path) > 16
                or any(
                    part != "*" and (type(part) is not int or not 0 <= part <= 2**31 - 1)
                    for part in path
                )
            ):
                raise LLMContractError("invalid_validation_path")
        if self.validator_keyword is not None and self.validator_keyword not in {
            "$ref",
            "$dynamicRef",
            "type",
            "required",
            "properties",
            "patternProperties",
            "additionalProperties",
            "unevaluatedProperties",
            "propertyNames",
            "items",
            "prefixItems",
            "unevaluatedItems",
            "contains",
            "minContains",
            "maxContains",
            "minItems",
            "maxItems",
            "uniqueItems",
            "minProperties",
            "maxProperties",
            "minLength",
            "maxLength",
            "pattern",
            "minimum",
            "maximum",
            "exclusiveMinimum",
            "exclusiveMaximum",
            "multipleOf",
            "enum",
            "const",
            "allOf",
            "anyOf",
            "oneOf",
            "not",
            "if",
            "dependentRequired",
            "dependentSchemas",
        }:
            raise LLMContractError("invalid_validator_keyword")


@dataclass(frozen=True, slots=True)
class LLMAttemptSummary:
    """Content-free facts from a completed generation, never a retry workspace.

    Usage details are projected onto a closed set of accounting counters. Arbitrary
    LLMUsage metadata cannot survive even explicit serialization of this object.
    Provider request IDs are deliberately omitted until a safe use requires them.
    """

    model: ModelRef
    usage: LLMUsage | None
    finish_reason: FinishReason
    latency_ms: int | None

    def __post_init__(self):
        _type(self.model, ModelRef, "model_ref")
        _type(self.finish_reason, FinishReason, "finish_reason")
        if self.latency_ms is not None:
            _count(self.latency_ms, "latency")
        if self.usage is not None:
            _type(self.usage, LLMUsage, "usage")
            details = {}
            for group, names in {
                "prompt_tokens_details": ("cached_tokens", "audio_tokens"),
                "completion_tokens_details": (
                    "reasoning_tokens",
                    "audio_tokens",
                    "accepted_prediction_tokens",
                    "rejected_prediction_tokens",
                ),
                "": ("prompt_cache_hit_tokens", "prompt_cache_miss_tokens"),
            }.items():
                source = self.usage.details.get(group, {}) if group else self.usage.details
                if not isinstance(source, Mapping):
                    raise LLMContractError("invalid_attempt_usage")
                selected = {}
                for name in names:
                    if name in source:
                        value = source[name]
                        if value is not None:
                            _count(value, "attempt_usage_counter")
                        selected[name] = value
                if selected:
                    if group:
                        details[group] = selected
                    else:
                        details.update(selected)
            object.__setattr__(
                self,
                "usage",
                LLMUsage(
                    self.usage.input_tokens,
                    self.usage.output_tokens,
                    self.usage.total_tokens,
                    details,
                ),
            )


@dataclass(frozen=True, slots=True)
class LLMFailure:
    code: LLMErrorCode
    invocation_id: InvocationId
    diagnostics: ProviderDiagnostics = field(default_factory=ProviderDiagnostics, repr=False)
    attempt: LLMAttemptSummary | None = field(default=None, repr=False)
    structured_detail: StructuredFailureDetail | None = None

    def __post_init__(self):
        _type(self.code, LLMErrorCode, "error_code")
        _type(self.invocation_id, InvocationId, "invocation_id")
        _type(self.diagnostics, ProviderDiagnostics, "provider_diagnostics")
        if self.attempt is not None:
            _type(self.attempt, LLMAttemptSummary, "attempt_summary")
        if self.structured_detail is not None:
            _type(self.structured_detail, StructuredFailureDetail, "structured_failure_detail")
            if self.code is not LLMErrorCode.STRUCTURED_OUTPUT_FAILED:
                raise LLMContractError("structured_detail_requires_structured_failure")


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
    structured_output_mode: StructuredOutputMode = StructuredOutputMode.NONE

    def __post_init__(self):
        for label in (
            "text_generation",
            "streaming",
            "structured_output",
            "vision",
            "tool_calling",
            "reasoning_controls",
        ):
            if type(getattr(self, label)) is not bool:
                raise LLMContractError("invalid_capability_flag")
        _type(self.structured_output_mode, StructuredOutputMode, "structured_output_mode")
        if (
            self.structured_output_mode is not StructuredOutputMode.NONE
            and not self.structured_output
        ):
            raise LLMContractError("structured_mode_requires_capability")


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
