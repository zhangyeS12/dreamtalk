"""One-shot Chat Completions translation with opt-in structured modes; no provider SDK."""

import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from time import perf_counter
from urllib.parse import unquote, urlsplit

import httpx

from livingworld.application.chat_event_annotations import CHAT_ANNOTATION_ENCODING
from livingworld.application.llm import (
    DispatchState,
    FinishReason,
    LLMContractError,
    LLMError,
    LLMErrorCode,
    LLMFailure,
    LLMRequest,
    LLMResponse,
    LLMStreamCompletion,
    LLMStreamEvent,
    LLMUsage,
    MessageRole,
    ModelCapabilities,
    ModelRef,
    ProviderDiagnostics,
    ReasoningTokenRelation,
    StreamCompleted,
    StreamFailed,
    StreamOutcome,
    StreamStarted,
    StructuredOutputMode,
    TextContent,
    TextDelta,
    UsageUpdate,
)
from livingworld.application.llm_config import CredentialProvider, ProviderConfig, SecretValue
from livingworld.infrastructure.llm.http_transport import (
    bounded_body,
    is_event_stream,
    normalize_retry_after,
    normalize_transport_failure,
)
from livingworld.infrastructure.llm.sse import SSEDecoder, SSEProtocolError, StreamLimits
from livingworld.infrastructure.llm.structured import (
    InvalidStructuredSchema,
    prepare_schema,
    process_structured,
)
from livingworld.infrastructure.logging import StructuredLogger

_ROLES = frozenset({MessageRole.SYSTEM, MessageRole.USER, MessageRole.ASSISTANT})
_MAX_STOPS = 4
_DIAGNOSTIC = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")
_CONTEXT_CODES = frozenset({"context_length_exceeded", "context_window_exceeded"})
_FINISH = {
    "stop": FinishReason.STOP,
    "length": FinishReason.OUTPUT_LIMIT,
    "content_filter": FinishReason.REFUSAL,
    "refusal": FinishReason.REFUSAL,
}
_DETAILS = {
    "prompt_tokens_details": ("cached_tokens", "cache_write_tokens", "audio_tokens"),
    "completion_tokens_details": (
        "reasoning_tokens",
        "audio_tokens",
        "accepted_prediction_tokens",
        "rejected_prediction_tokens",
    ),
}


@dataclass(frozen=True, slots=True)
class ChatCompletionsProfile:
    """Explicit target capabilities; never inferred from host or model name."""

    supports_n: bool = False
    supports_streaming: bool = False
    supports_stream_usage: bool = False
    structured_output_mode: StructuredOutputMode = StructuredOutputMode.NONE

    def __post_init__(self):
        if any(
            type(value) is not bool
            for value in (self.supports_n, self.supports_streaming, self.supports_stream_usage)
        ):
            raise LLMContractError("invalid_chat_profile")
        if self.supports_stream_usage and not self.supports_streaming:
            raise LLMContractError("stream_usage_requires_streaming")
        if not isinstance(self.structured_output_mode, StructuredOutputMode):
            raise LLMContractError("invalid_chat_profile")


class _InvalidResponse(Exception):
    """Internal structural failure; never carries rejected provider data."""


def _endpoint(config: ProviderConfig) -> httpx.URL:
    if config.endpoint is None:
        raise LLMContractError("chat_endpoint_required")
    base = config.endpoint.base_url
    # EndpointConfig rejects userinfo, query, fragment, whitespace and bad ports.
    # Reject additional shapes HTTPX would normalize into a different base path.
    parsed = urlsplit(base)
    if (
        parsed.netloc.endswith(":")
        or re.search(r"%(?![0-9a-fA-F]{2})", base)
        or any(unquote(part) in {".", ".."} for part in parsed.path.split("/"))
    ):
        raise LLMContractError("invalid_chat_endpoint")
    invalid = False
    try:
        url = httpx.URL(base.rstrip("/") + "/chat/completions")
        host = url.raw_host.decode("ascii")
        if ":" not in host and any(
            not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
            for label in host.rstrip(".").split(".")
        ):
            invalid = True
    except (ValueError, httpx.InvalidURL):
        invalid = True
    if invalid:
        raise LLMContractError("invalid_chat_endpoint")
    return url


def _safe_diagnostic(value, secret: str, request: LLMRequest) -> str | None:
    if type(value) is not str or not _DIAGNOSTIC.fullmatch(value) or secret in value:
        return None
    # Also reject reflected full message/stop strings. This is a bounded subset,
    # not a claim that arbitrary provider strings can be universally sanitized.
    protected = [block.text for message in request.messages for block in message.content]
    protected.extend(request.stop_sequences)
    if any(text and text in value for text in protected):
        return None
    return value


def _count(value) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise _InvalidResponse
    return value


def _usage(value) -> LLMUsage | None:
    if value is None:
        return None
    if type(value) is not dict:
        raise _InvalidResponse
    details = {}
    for group, fields in _DETAILS.items():
        reported = value.get(group)
        if reported is not None:
            if type(reported) is not dict:
                raise _InvalidResponse
            selected = {key: _count(reported[key]) for key in fields if key in reported}
            if selected:
                details[group] = selected
    for field in ("prompt_cache_hit_tokens", "prompt_cache_miss_tokens"):
        if field in value:
            details[field] = _count(value[field])
    input_tokens = _count(value.get("prompt_tokens"))
    prompt = details.get("prompt_tokens_details", {})
    cached = prompt.get("cached_tokens")
    cache_write = prompt.get("cache_write_tokens")
    hit, miss = details.get("prompt_cache_hit_tokens"), details.get("prompt_cache_miss_tokens")
    uncached = None
    if hit is not None:
        if cached is not None and cached != hit:
            raise _InvalidResponse
        cached = hit
    if miss is not None:
        uncached = miss
    if (
        hit is not None
        and miss is not None
        and input_tokens is not None
        and hit + miss != input_tokens
    ):
        raise _InvalidResponse
    if all(v is not None for v in (input_tokens, cached, cache_write)):
        derived = input_tokens - cached - cache_write
        if derived < 0 or uncached is not None and derived != uncached:
            raise _InvalidResponse
        uncached = derived
    try:
        return LLMUsage(
            input_tokens=input_tokens,
            output_tokens=_count(value.get("completion_tokens")),
            total_tokens=_count(value.get("total_tokens")),
            details=details,
            cached_input_tokens=cached,
            cache_write_input_tokens=cache_write,
            uncached_input_tokens=uncached,
            reasoning_output_tokens=details.get("completion_tokens_details", {}).get(
                "reasoning_tokens"
            ),
            reasoning_token_relation=ReasoningTokenRelation.INCLUDED_IN_OUTPUT,
        )
    except LLMContractError:
        raise _InvalidResponse from None


def _tier(data):
    # Only documented response values; never request hints, arbitrary strings or auto.
    value = data.get("service_tier")
    return (
        value
        if type(value) is str and value in {"default", "flex", "scale", "priority", "fast"}
        else None
    )


def _json(response: httpx.Response):
    invalid = False
    try:
        data = json.loads(response.content, parse_constant=_invalid_json_constant)
    except (ValueError, UnicodeError):
        invalid = True
    if invalid:
        raise _InvalidResponse
    return data


def _invalid_json_constant(_):
    raise ValueError("invalid_json_constant")


def _diagnostics(response, data, request, secret, code=None):
    body_id = data.get("id") if type(data) is dict else None
    provider_id = _safe_diagnostic(response.headers.get("x-request-id"), secret, request)
    if provider_id is None:
        provider_id = _safe_diagnostic(body_id, secret, request)
    return ProviderDiagnostics(provider_request_id=provider_id, diagnostic_code=code)


def _response(response, request, secret, latency_ms):
    data = _json(response)
    if type(data) is not dict or data.get("object") != "chat.completion":
        raise _InvalidResponse
    model = data.get("model")
    choices = data.get("choices")
    if (
        type(model) is not str
        or not model.strip()
        or secret in model
        or type(choices) is not list
        or not choices
    ):
        raise _InvalidResponse
    # Use exactly the first array member; never combine distinct completions.
    choice = choices[0]
    if type(choice) is not dict:
        raise _InvalidResponse
    index = choice.get("index")
    if type(index) is not int or index < 0:
        raise _InvalidResponse
    message = choice.get("message")
    finish = choice.get("finish_reason")
    if (
        type(message) is not dict
        or message.get("role") != "assistant"
        or finish is not None
        and type(finish) is not str
    ):
        raise _InvalidResponse
    if (
        finish in {"tool_calls", "function_call"}
        or message.get("tool_calls")
        or message.get("function_call")
    ):
        return LLMFailure(
            LLMErrorCode.UNSUPPORTED_CAPABILITY,
            request.invocation_id,
            _diagnostics(response, data, request, secret, "unexpected_tool_call"),
        )
    if "content" not in message:
        raise _InvalidResponse
    text = message["content"]
    refusal = message.get("refusal")
    if (text is not None and type(text) is not str) or (
        refusal is not None and type(refusal) is not str
    ):
        raise _InvalidResponse
    reason = _FINISH.get(finish, FinishReason.UNKNOWN)
    if refusal:
        reason = FinishReason.REFUSAL
    if (
        text is None
        and reason is not FinishReason.REFUSAL
        and not (request.structured_output is not None and reason is FinishReason.OUTPUT_LIMIT)
    ):
        raise _InvalidResponse
    output = text if text is not None else refusal or ""
    if secret in output:
        raise _InvalidResponse
    diagnostic = None
    if reason is FinishReason.UNKNOWN:
        safe_finish = _safe_diagnostic(finish, secret, request)
        diagnostic = "finish:" + safe_finish if safe_finish is not None else "unknown_finish_reason"
    return LLMResponse(
        invocation_id=request.invocation_id,
        model_used=ModelRef(request.model.provider_id, model),
        content=(TextContent(output),),
        finish_reason=reason,
        usage=_usage(data.get("usage")),
        diagnostics=_diagnostics(response, data, request, secret, diagnostic),
        latency_ms=latency_ms,
        processing_tier=_tier(data),
    )


_UNREAD = object()


def _retry_after(value, *, now_utc=None):
    return normalize_retry_after(value, now_utc=now_utc)


def _transport_failure(error, *, response_received=False):
    return normalize_transport_failure(error, response_received=response_received)


def _status_failure(response, request, secret, *, data=_UNREAD):
    status = response.status_code
    if data is _UNREAD:
        data = None
        try:
            data = _json(response)
        except _InvalidResponse:
            pass
    code = LLMErrorCode.CONFIGURATION
    if status in {401, 403}:
        code = LLMErrorCode.AUTHENTICATION
    elif status == 429:
        code = LLMErrorCode.RATE_LIMITED
    elif status == 408:
        code = LLMErrorCode.TIMEOUT
    elif status >= 500:
        code = LLMErrorCode.PROVIDER_UNAVAILABLE
    elif status in {400, 422}:
        code = LLMErrorCode.INVALID_REQUEST
        error = data.get("error") if type(data) is dict else None
        if type(error) is dict and any(
            error.get(field) in _CONTEXT_CODES
            for field in ("code", "type")
            if type(error.get(field)) is str
        ):
            code = LLMErrorCode.CONTEXT_LIMIT
    return LLMFailure(
        code,
        request.invocation_id,
        _diagnostics(response, data, request, secret, f"http:{status}"),
        dispatch_state=DispatchState.HTTP_RESPONSE_RECEIVED,
        http_status=status,
        retry_after_seconds=_retry_after(response.headers.get("retry-after"))
        if status == 429 or status == 408 or status >= 500
        else None,
    )


def _event_stream_type(value):
    return is_event_stream(value)


async def _bounded_error_body(response, limit):
    body = await bounded_body(response, limit)
    if body is None:
        return None
    try:
        return json.loads(body, parse_constant=_invalid_json_constant)
    except (ValueError, UnicodeError, RecursionError):
        return None


class _UnsupportedStream(Exception):
    """Unsupported tool semantics; no arguments or raw payload."""


@dataclass(frozen=True, slots=True)
class _StreamChunk:
    model: ModelRef
    text: str
    usage: LLMUsage | None
    finish_reason: FinishReason | None
    outcome: StreamOutcome
    provider_request_id: str | None
    processing_tier: str | None


def _unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _InvalidResponse
        result[key] = value
    return result


def _stream_chunk(payload, request, secret, limits):
    invalid = False
    try:
        data = json.loads(
            payload, parse_constant=_invalid_json_constant, object_pairs_hook=_unique_fields
        )
    except (ValueError, RecursionError):
        invalid = True
    if invalid or type(data) is not dict or data.get("object") != "chat.completion.chunk":
        raise _InvalidResponse
    model = data.get("model")
    if type(model) is not str or not model.strip() or secret in model:
        raise _InvalidResponse
    try:
        if len(model.encode("utf-8")) > limits.max_model_bytes:
            raise _InvalidResponse
    except UnicodeError:
        raise _InvalidResponse from None
    if any(
        block.text and block.text in model
        for message in request.messages
        for block in message.content
    ):
        raise _InvalidResponse
    choices = data.get("choices")
    if type(choices) is not list or any(
        type(choice) is not dict or type(choice.get("index")) is not int or choice["index"] < 0
        for choice in choices
    ):
        raise _InvalidResponse
    selected = [choice for choice in choices if choice["index"] == 0]
    usage = _usage(data.get("usage"))
    if (choices and len(selected) != 1) or (not choices and usage is None):
        raise _InvalidResponse
    text = ""
    finish = None
    outcome = StreamOutcome.NORMAL
    if selected:
        choice = selected[0]
        delta = choice.get("delta")
        if type(delta) is not dict or ("role" in delta and delta["role"] != "assistant"):
            raise _InvalidResponse
        finish = choice.get("finish_reason")
        if finish is not None and (type(finish) is not str or not finish.strip()):
            raise _InvalidResponse
        if (
            finish in {"tool_calls", "function_call"}
            or delta.get("tool_calls")
            or delta.get("function_call")
        ):
            raise _UnsupportedStream
        content, refusal = delta.get("content"), delta.get("refusal")
        if any(value is not None and type(value) is not str for value in (content, refusal)):
            raise _InvalidResponse
        if content and secret in content:
            raise _InvalidResponse
        try:
            if content:
                content.encode("utf-8")
            if refusal:
                refusal.encode("utf-8")
        except UnicodeError:
            raise _InvalidResponse from None
        if finish == "content_filter":
            outcome = StreamOutcome.CONTENT_FILTERED
        elif refusal or finish == "refusal":
            outcome = StreamOutcome.REFUSAL
        if outcome is StreamOutcome.NORMAL:
            text = content or ""
        # refusal/reasoning/tool data is neither emitted nor copied to stream state.
    identifier = _safe_diagnostic(data.get("id"), secret, request)
    if identifier is not None and selected:
        if any(
            type(value) is str and value and value in identifier
            for value in (
                delta.get("content"),
                delta.get("refusal"),
                delta.get("reasoning_content"),
            )
        ):
            identifier = None
    return _StreamChunk(
        ModelRef(request.model.provider_id, model),
        text,
        usage,
        _FINISH.get(finish, FinishReason.UNKNOWN) if finish is not None else None,
        outcome,
        identifier,
        _tier(data),
    )


class _StreamState:
    """Only bounded terminal state. No answer, reasoning or delta history."""

    __slots__ = (
        "model",
        "reported_model",
        "finish_reason",
        "outcome",
        "usage",
        "provider_request_id",
        "processing_tier",
    )

    def __init__(self, model):
        self.model = model
        self.reported_model = False
        self.finish_reason = None
        self.outcome = StreamOutcome.NORMAL
        self.usage = None
        self.provider_request_id = None
        self.processing_tier = None

    def accept(self, chunk):
        if chunk.processing_tier is not None:
            if self.processing_tier is not None and self.processing_tier != chunk.processing_tier:
                raise _InvalidResponse
            self.processing_tier = chunk.processing_tier
        if self.reported_model and chunk.model != self.model:
            raise _InvalidResponse
        self.model, self.reported_model = chunk.model, True
        if self.finish_reason is not None and (
            chunk.text
            or chunk.outcome is not StreamOutcome.NORMAL
            or chunk.finish_reason not in {None, self.finish_reason}
        ):
            raise _InvalidResponse
        if chunk.outcome is StreamOutcome.CONTENT_FILTERED or (
            self.outcome is StreamOutcome.NORMAL and chunk.outcome is StreamOutcome.REFUSAL
        ):
            self.outcome = chunk.outcome
        if chunk.finish_reason is not None:
            self.finish_reason = (
                chunk.finish_reason
                if self.outcome is StreamOutcome.NORMAL
                else FinishReason.REFUSAL
            )
        if self.provider_request_id is None:
            self.provider_request_id = chunk.provider_request_id
        if (
            chunk.text
            and self.provider_request_id is not None
            and chunk.text in self.provider_request_id
        ):
            self.provider_request_id = None
        usage = chunk.usage if chunk.usage is not None and chunk.usage != self.usage else None
        if chunk.usage is not None:
            self.usage = chunk.usage
        return chunk.text if self.outcome is StreamOutcome.NORMAL else "", usage


class OpenAICompatibleChatGateway:
    """Owns one reusable client (and injected transport). Close after in-flight calls."""

    capabilities = ModelCapabilities(text_generation=True)

    def __init__(
        self,
        config: ProviderConfig,
        credentials: CredentialProvider,
        *,
        profile: ChatCompletionsProfile | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        logger: StructuredLogger | None = None,
        stream_limits: StreamLimits | None = None,
    ):
        profile = profile if profile is not None else ChatCompletionsProfile()
        if not isinstance(config, ProviderConfig) or not isinstance(
            profile, ChatCompletionsProfile
        ):
            raise LLMContractError("invalid_chat_configuration")
        self._endpoint = _endpoint(config)
        self._config = config
        self._credentials = credentials
        self._profile = profile
        self._stream_limits = stream_limits if stream_limits is not None else StreamLimits()
        if not isinstance(self._stream_limits, StreamLimits):
            raise LLMContractError("invalid_stream_limits")
        self.capabilities = ModelCapabilities(
            text_generation=True,
            streaming=profile.supports_streaming,
            structured_output=profile.structured_output_mode is not StructuredOutputMode.NONE,
            structured_output_mode=profile.structured_output_mode,
        )
        self._logger = logger
        self._client = httpx.AsyncClient(
            transport=transport,
            timeout=config.timeout_ms / 1000,
            follow_redirects=False,
            verify=config.verify_tls,
            trust_env=False,
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.aclose()

    async def aclose(self):
        await self._client.aclose()

    def _error(
        self,
        request,
        code,
        diagnostics=None,
        *,
        attempt=None,
        structured_detail=None,
        dispatch_state=DispatchState.NOT_DISPATCHED,
        http_status=None,
        retry_after_seconds=None,
    ):
        if self._logger is not None:
            if structured_detail is not None:
                try:
                    usage = attempt.usage if attempt is not None else None
                    self._logger.emit_llm_reply_facts(
                        trace_id=str(request.invocation_id.value),
                        reason=structured_detail.reason.value,
                        finish_reason=attempt.finish_reason.value if attempt is not None else None,
                        input_tokens=usage.input_tokens if usage is not None else None,
                        output_tokens=usage.output_tokens if usage is not None else None,
                        reasoning_output_tokens=(
                            usage.reasoning_output_tokens if usage is not None else None
                        ),
                        max_output_tokens=request.max_output_tokens,
                        http_status=http_status,
                        transport="prompt_json"
                        if self._prompt_json_dialogue(request)
                        else "native_json",
                    )
                except Exception:
                    pass  # Optional diagnostics cannot alter settlement or cause a replay.
                self._logger.emit(
                    "llm",
                    "chat_structured_" + structured_detail.reason.value,
                    level="WARNING",
                    trace_id=str(request.invocation_id.value),
                )
            self._logger.emit(
                "llm",
                f"chat_{code.value}",
                level="WARNING",
                trace_id=str(request.invocation_id.value),
            )
        return LLMError(
            LLMFailure(
                code,
                request.invocation_id,
                diagnostics or ProviderDiagnostics(),
                attempt,
                structured_detail,
                dispatch_state,
                http_status,
                retry_after_seconds,
            )
        )

    def _failure_error(self, request, failure):
        return self._error(
            request,
            failure.code,
            failure.diagnostics,
            attempt=failure.attempt,
            structured_detail=failure.structured_detail,
            dispatch_state=failure.dispatch_state,
            http_status=failure.http_status,
            retry_after_seconds=failure.retry_after_seconds,
        )

    def _prompt_json_dialogue(self, request):
        # Native JSON decoding can return empty content on official DeepSeek.
        # Dialogue annotations are parsed locally. Provider structured-output
        # enforcement stays reserved for tasks that require it. No replay.
        return (
            (
                request.metadata.get("chat_reply_encoding") == CHAT_ANNOTATION_ENCODING
                or request.structured_output is not None
                and request.structured_output.schema_name == "chat_event_reply"
            )
            and request.purpose.value == "character_dialogue"
            and self._profile.structured_output_mode
            is StructuredOutputMode.JSON_OBJECT_LOCAL_VALIDATE
            and self._config.endpoint.base_url.rstrip("/")
            in {"https://api.deepseek.com", "https://api.deepseek.com/v1"}
        )

    def _payload(self, request, *, streaming=False):
        if not isinstance(request, LLMRequest):
            raise LLMContractError("invalid_llm_request")
        if request.model.provider_id != self._config.provider_id:
            raise self._error(request, LLMErrorCode.CONFIGURATION)
        if request.streaming is not streaming:
            code = (
                LLMErrorCode.UNSUPPORTED_CAPABILITY
                if request.streaming
                else LLMErrorCode.INVALID_REQUEST
            )
            raise self._error(request, code)
        if request.max_output_tokens is None:
            raise self._error(request, LLMErrorCode.INVALID_REQUEST)
        if request.temperature is not None:
            raise self._error(request, LLMErrorCode.UNSUPPORTED_CAPABILITY)
        if streaming and (
            not self._profile.supports_streaming
            or (
                request.structured_output is not None
                and self._profile.structured_output_mode
                is not StructuredOutputMode.JSON_OBJECT_LOCAL_VALIDATE
            )
        ):
            raise self._error(request, LLMErrorCode.UNSUPPORTED_CAPABILITY)
        if (
            request.structured_output is not None
            and self._profile.structured_output_mode is StructuredOutputMode.NONE
        ):
            raise self._error(request, LLMErrorCode.UNSUPPORTED_CAPABILITY)
        if len(request.stop_sequences) > _MAX_STOPS:
            raise self._error(request, LLMErrorCode.UNSUPPORTED_CAPABILITY)
        messages = []
        for message in request.messages:
            if message.role not in _ROLES or any(
                not isinstance(block, TextContent) for block in message.content
            ):
                raise self._error(request, LLMErrorCode.UNSUPPORTED_CAPABILITY)
            messages.append(
                {"role": message.role.value, "content": "".join(b.text for b in message.content)}
            )
        payload = {
            "model": request.model.model_id,
            "messages": messages,
            "max_tokens": request.max_output_tokens,
            "stream": streaming,
        }
        if (
            request.structured_output is not None
            and self._profile.structured_output_mode
            is StructuredOutputMode.JSON_OBJECT_LOCAL_VALIDATE
        ):
            if request.structured_output.schema.get("type") != "object":
                raise self._error(request, LLMErrorCode.UNSUPPORTED_CAPABILITY)
            if not self._prompt_json_dialogue(request):
                payload["response_format"] = {"type": "json_object"}
        # Keep the established small-task reasoning policy when optional chat
        # annotations no longer require a provider structured-output contract.
        if (
            self._config.endpoint.base_url.rstrip("/")
            in {"https://api.deepseek.com", "https://api.deepseek.com/v1"}
            and request.model.model_id in {"deepseek-flash", "deepseek-v4-pro"}
            and (
                self._prompt_json_dialogue(request)
                or request.structured_output is not None
                and self._profile.structured_output_mode
                is StructuredOutputMode.JSON_OBJECT_LOCAL_VALIDATE
                and request.structured_output.schema_name
                in {"chat_event_reply", "world_news_batch"}
            )
        ):
            payload["thinking"] = {"type": "disabled"}
        if streaming and self._profile.supports_stream_usage:
            payload["stream_options"] = {"include_usage": True}
        if request.stop_sequences:
            payload["stop"] = list(request.stop_sequences)
        if self._profile.supports_n:
            payload["n"] = 1
        return payload

    def token_reservation_payload(self, request: LLMRequest) -> dict | None:
        """The actual text request body, with no credentials or dispatch capability."""
        if (
            request.structured_output is not None
            and self._profile.structured_output_mode
            is not StructuredOutputMode.JSON_OBJECT_LOCAL_VALIDATE
        ):
            return None
        return self._payload(request, streaming=request.streaming)

    async def _secret(self, request):
        if self._client.is_closed or self._config.secret_ref is None:
            raise self._error(request, LLMErrorCode.CONFIGURATION)
        credential_failed = False
        try:
            credential = await self._credentials.resolve(self._config.secret_ref)
        except Exception:
            credential_failed = True
        # Raise outside exception handlers: raw credential/HTTP errors must not
        # survive as LLMError.__context__, even when a caller inspects the object.
        if credential_failed:
            raise self._error(request, LLMErrorCode.AUTHENTICATION)
        if not isinstance(credential, SecretValue):
            raise self._error(request, LLMErrorCode.AUTHENTICATION)
        secret = credential.reveal_for_adapter()
        del credential
        if not re.fullmatch(r"[A-Za-z0-9._~+/-]+=*", secret):
            del secret
            raise self._error(request, LLMErrorCode.AUTHENTICATION)
        return secret

    async def generate(self, request: LLMRequest) -> LLMResponse:
        payload = self._payload(request)
        validator = None
        if request.structured_output is not None:
            invalid = False
            try:
                validator = prepare_schema(request.structured_output)
            except InvalidStructuredSchema:
                invalid = True
            if invalid:
                raise self._error(request, LLMErrorCode.INVALID_REQUEST)
            schema = validator.schema
            # These wire modes require an explicit object root. Do not rewrite
            # arrays/unions/$refs into objects, or claim general schema transport.
            if schema.get("type") != "object" or (
                self._profile.structured_output_mode is StructuredOutputMode.NATIVE_JSON_SCHEMA
                and "anyOf" in schema
            ):
                raise self._error(request, LLMErrorCode.UNSUPPORTED_CAPABILITY)
            if self._profile.structured_output_mode is StructuredOutputMode.NATIVE_JSON_SCHEMA:
                payload["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": request.structured_output.schema_name,
                        "strict": True,
                        "schema": schema,
                    },
                }
            elif not self._prompt_json_dialogue(request):
                payload["response_format"] = {"type": "json_object"}
        secret = await self._secret(request)
        wire = None
        response = None
        transport_failure = None
        try:
            wire = self._client.build_request(
                "POST", self._endpoint, json=payload, headers={"Authorization": f"Bearer {secret}"}
            )
            wire.headers.pop("cookie", None)
            started = perf_counter()
            try:
                response = await self._client.send(wire, follow_redirects=False)
            except (httpx.HTTPError, httpx.InvalidURL) as error:
                transport_failure = _transport_failure(error)
            latency_ms = max(0, int((perf_counter() - started) * 1000))
            if transport_failure is not None:
                code, dispatch = transport_failure
                raise self._error(request, code, dispatch_state=dispatch)
            if not 200 <= response.status_code < 300:
                failure = _status_failure(response, request, secret)
                raise self._failure_error(request, failure)
            malformed = False
            try:
                result = _response(response, request, secret, latency_ms)
            except _InvalidResponse:
                malformed = True
            if malformed:
                raise self._error(
                    request,
                    LLMErrorCode.MALFORMED_RESPONSE,
                    dispatch_state=DispatchState.HTTP_RESPONSE_RECEIVED,
                    http_status=response.status_code,
                )
            if isinstance(result, LLMFailure):
                raise self._failure_error(
                    request,
                    replace(
                        result,
                        dispatch_state=DispatchState.HTTP_RESPONSE_RECEIVED,
                        http_status=response.status_code,
                    ),
                )
            if validator is not None:
                result = process_structured(request.structured_output, validator, result)
                if isinstance(result, LLMFailure):
                    raise self._failure_error(
                        request,
                        replace(
                            result,
                            dispatch_state=DispatchState.HTTP_RESPONSE_RECEIVED,
                            http_status=response.status_code,
                        ),
                    )
            if self._logger is not None:
                if self._prompt_json_dialogue(request) and request.structured_output is None:
                    try:
                        usage = result.usage
                        self._logger.emit_llm_reply_facts(
                            event="chat_annotation_response_facts",
                            trace_id=str(request.invocation_id.value),
                            transport="prompt_json",
                            finish_reason=result.finish_reason.value,
                            input_tokens=usage.input_tokens if usage is not None else None,
                            output_tokens=usage.output_tokens if usage is not None else None,
                            reasoning_output_tokens=(
                                usage.reasoning_output_tokens if usage is not None else None
                            ),
                            max_output_tokens=request.max_output_tokens,
                            http_status=response.status_code,
                        )
                    except Exception:
                        pass  # Optional facts cannot alter settlement or trigger another call.
                self._logger.emit(
                    "llm", "chat_completed", trace_id=str(request.invocation_id.value)
                )
            return result
        finally:
            if wire is not None:
                wire.headers.pop("authorization", None)
            self._client.cookies.clear()
            if response is not None:
                await response.aclose()
            del secret

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamEvent]:
        """One pull-driven HTTP attempt. Caller must close an abandoned iterator."""
        wire = response = secret = None
        failure = None
        completion = None
        try:
            payload = self._payload(request, streaming=True)
            secret = await self._secret(request)
            wire = self._client.build_request(
                "POST",
                self._endpoint,
                json=payload,
                headers={"Authorization": f"Bearer {secret}", "Accept": "text/event-stream"},
            )
            wire.headers.pop("cookie", None)
            started = perf_counter()
            response = await self._client.send(wire, stream=True, follow_redirects=False)
            if not 200 <= response.status_code < 300:
                data = await _bounded_error_body(response, self._stream_limits.max_error_body_bytes)
                failed = _status_failure(response, request, secret, data=data)
                raise self._failure_error(request, failed)
            if not _event_stream_type(response.headers.get("content-type", "")):
                raise self._error(
                    request,
                    LLMErrorCode.MALFORMED_RESPONSE,
                    dispatch_state=DispatchState.HTTP_RESPONSE_RECEIVED,
                    http_status=response.status_code,
                )
            if self._logger is not None:
                self._logger.emit(
                    "llm", "chat_stream_started", trace_id=str(request.invocation_id.value)
                )
            yield StreamStarted(request.invocation_id, request.model)
            decoder = SSEDecoder(self._stream_limits)
            state = _StreamState(request.model)
            state.provider_request_id = _safe_diagnostic(
                response.headers.get("x-request-id"), secret, request
            )
            async for fragment in response.aiter_bytes():
                for data in decoder.feed(fragment):
                    if data == "[DONE]":
                        if state.finish_reason is None:
                            raise _InvalidResponse
                        completion = LLMStreamCompletion(
                            invocation_id=request.invocation_id,
                            model_used=state.model,
                            finish_reason=state.finish_reason,
                            outcome=state.outcome,
                            usage=state.usage,
                            processing_tier=state.processing_tier,
                            latency_ms=max(0, int((perf_counter() - started) * 1000)),
                            diagnostics=ProviderDiagnostics(
                                provider_request_id=state.provider_request_id,
                                diagnostic_code="unknown_finish_reason"
                                if state.finish_reason is FinishReason.UNKNOWN
                                else None,
                            ),
                        )
                        break
                    chunk = _stream_chunk(data, request, secret, self._stream_limits)
                    del data  # Raw payload is not retained alongside progressive content.
                    text, updated_usage = state.accept(chunk)
                    del chunk
                    if text:
                        yield TextDelta(request.invocation_id, text)
                    del text
                    if updated_usage is not None:
                        yield UsageUpdate(request.invocation_id, updated_usage)
                if completion is not None:
                    break
            if completion is None:
                raise _InvalidResponse  # EOF is never a protocol completion.
        except LLMError as error:
            failure = error.failure
        except (httpx.HTTPError, httpx.InvalidURL) as error:
            code, dispatch = _transport_failure(error, response_received=response is not None)
            failure = self._error(request, code, dispatch_state=dispatch).failure
        except _UnsupportedStream:
            failure = self._error(
                request,
                LLMErrorCode.UNSUPPORTED_CAPABILITY,
                dispatch_state=DispatchState.HTTP_RESPONSE_RECEIVED,
                http_status=response.status_code,
            ).failure
        except (_InvalidResponse, SSEProtocolError):
            failure = self._error(
                request,
                LLMErrorCode.MALFORMED_RESPONSE,
                dispatch_state=DispatchState.HTTP_RESPONSE_RECEIVED,
                http_status=response.status_code,
            ).failure
        finally:
            if wire is not None:
                wire.headers.pop("authorization", None)
            self._client.cookies.clear()
            secret = None
            if response is not None:
                try:
                    await response.aclose()
                except httpx.HTTPError as error:
                    if failure is None:
                        code, dispatch = _transport_failure(error, response_received=True)
                        failure = self._error(request, code, dispatch_state=dispatch).failure
        # Close and scrub before delivering the terminal event, even if the
        # consumer never requests another item. CancelledError/GeneratorExit
        # propagate through finally and never reach this terminal delivery.
        if failure is not None:
            yield StreamFailed(failure)
        else:
            if self._logger is not None:
                self._logger.emit(
                    "llm", "chat_stream_completed", trace_id=str(request.invocation_id.value)
                )
            yield StreamCompleted(completion)
