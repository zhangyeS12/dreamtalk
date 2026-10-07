"""Native Anthropic Messages transport. One HTTP attempt, no SDK or hidden fallback."""

import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from math import isfinite
from time import perf_counter
from urllib.parse import unquote, urlsplit

import httpx

from livingworld.application.llm import (
    DispatchState,
    FinishReason,
    LLMAttemptSummary,
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
from livingworld.application.llm_config import CredentialProvider, ProviderConfig
from livingworld.infrastructure.llm.adapter_support import (
    error_from_failure,
    resolve_adapter_secret,
)
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

ANTHROPIC_API_VERSION = "2023-06-01"
ANTHROPIC_DEFAULT_BASE_URL = "https://api.anthropic.com"
_DIAGNOSTIC = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")
_TOKEN = re.compile(r"[A-Za-z0-9._~+/-]+=*\Z")
_WORKSPACE = re.compile(r"wrkspc_[A-Za-z0-9_-]{1,120}\Z")
_KNOWN_EVENTS = frozenset(
    {
        "message_start",
        "content_block_start",
        "content_block_delta",
        "content_block_stop",
        "message_delta",
        "message_stop",
        "ping",
        "error",
    }
)


class _InvalidResponse(Exception):
    """Internal fixed failure; never carries provider content."""


class _UnsupportedResult(Exception):
    """Known provider semantics outside the approved LivingWorld subset."""


class _StreamProviderFailure(Exception):
    def __init__(self, failure: LLMFailure):
        self.failure = failure


@dataclass(frozen=True, slots=True)
class AnthropicWorkspaceId:
    value: str

    def __post_init__(self):
        if type(self.value) is not str or not _WORKSPACE.fullmatch(self.value):
            raise LLMContractError("invalid_anthropic_workspace_id")


@dataclass(frozen=True, slots=True)
class AnthropicTemperaturePolicy:
    """Explicit documented interval; None on the model profile means unsupported."""

    minimum: float = 0.0
    maximum: float = 1.0

    def __post_init__(self):
        invalid_number = any(
            type(value) not in {int, float} or not isfinite(value)
            for value in (self.minimum, self.maximum)
        )
        if invalid_number or not 0 <= self.minimum <= self.maximum <= 1:
            raise LLMContractError("invalid_anthropic_temperature_policy")

    def supports(self, value: float) -> bool:
        return self.minimum <= value <= self.maximum


@dataclass(frozen=True, slots=True, kw_only=True)
class AnthropicMessagesProfile:
    """Exact configured model behavior; nothing is inferred from model names."""

    supports_streaming: bool = False
    supports_native_structured_output: bool = False
    supports_assistant_prefill: bool = False
    default_max_output_tokens: int | None = None
    max_output_tokens: int | None = None
    temperature_policy: AnthropicTemperaturePolicy | None = None

    def __post_init__(self):
        if any(
            type(value) is not bool
            for value in (
                self.supports_streaming,
                self.supports_native_structured_output,
                self.supports_assistant_prefill,
            )
        ):
            raise LLMContractError("invalid_anthropic_profile")
        for value in (self.default_max_output_tokens, self.max_output_tokens):
            if value is not None and (type(value) is not int or value < 1):
                raise LLMContractError("invalid_anthropic_profile")
        if (
            self.default_max_output_tokens is not None
            and self.max_output_tokens is not None
            and self.default_max_output_tokens > self.max_output_tokens
        ):
            raise LLMContractError("invalid_anthropic_profile")
        if self.temperature_policy is not None and not isinstance(
            self.temperature_policy, AnthropicTemperaturePolicy
        ):
            raise LLMContractError("invalid_anthropic_profile")


def _endpoint(config: ProviderConfig) -> httpx.URL:
    base = config.endpoint.base_url if config.endpoint is not None else ANTHROPIC_DEFAULT_BASE_URL
    parsed = urlsplit(base)
    if (
        parsed.netloc.endswith(":")
        or re.search(r"%(?![0-9a-fA-F]{2})", base)
        or any(unquote(part) in {".", ".."} for part in parsed.path.split("/"))
    ):
        raise LLMContractError("invalid_anthropic_endpoint")
    invalid = False
    try:
        url = httpx.URL(base.rstrip("/") + "/v1/messages")
        host = url.raw_host.decode("ascii")
        if ":" not in host and any(
            not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
            for label in host.rstrip(".").split(".")
        ):
            invalid = True
    except (ValueError, httpx.InvalidURL):
        invalid = True
    if invalid:
        raise LLMContractError("invalid_anthropic_endpoint")
    return url


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def _invalid_constant(_):
    raise ValueError("invalid_json_constant")


def _json_bytes(value):
    try:
        return json.loads(
            value,
            parse_constant=_invalid_constant,
            object_pairs_hook=_unique_object,
        )
    except (ValueError, UnicodeError, RecursionError):
        raise _InvalidResponse from None


def _safe_identifier(value, secret, request):
    if type(value) is not str or not _DIAGNOSTIC.fullmatch(value) or secret in value:
        return None
    protected = [block.text for message in request.messages for block in message.content]
    protected.extend(request.stop_sequences)
    return None if any(text and text in value for text in protected) else value


def _count(value):
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise _InvalidResponse
    return value


def _usage(value):
    if value is None:
        return None, False
    if type(value) is not dict:
        raise _InvalidResponse
    raw_input = _count(value.get("input_tokens"))
    cache_write = _count(value.get("cache_creation_input_tokens"))
    cache_read = _count(value.get("cache_read_input_tokens"))
    output = _count(value.get("output_tokens"))
    cache = value.get("cache_creation")
    five = one = None
    if cache is not None:
        if type(cache) is not dict:
            raise _InvalidResponse
        five = _count(cache.get("ephemeral_5m_input_tokens"))
        one = _count(cache.get("ephemeral_1h_input_tokens"))
    if cache_write is None and five is not None and one is not None:
        cache_write = five + one
    incomplete = False
    if cache_write is not None and (
        any(item is not None and item > cache_write for item in (five, one))
        or five is not None
        and one is not None
        and five + one != cache_write
    ):
        five = one = None
        incomplete = True
    output_details = value.get("output_tokens_details")
    if output_details is not None and type(output_details) is not dict:
        raise _InvalidResponse
    reasoning = (
        _count(output_details.get("thinking_tokens")) if output_details is not None else None
    )
    total_input = (
        raw_input + (cache_write or 0) + (cache_read or 0) if raw_input is not None else None
    )
    details = {"cache_write_ttl_breakdown_incomplete": 1} if incomplete else {}
    try:
        return (
            LLMUsage(
                input_tokens=total_input,
                output_tokens=output,
                details=details,
                cached_input_tokens=cache_read,
                cache_write_input_tokens=cache_write,
                uncached_input_tokens=raw_input,
                reasoning_output_tokens=reasoning,
                cache_write_5m_input_tokens=five,
                cache_write_1h_input_tokens=one,
                reasoning_token_relation=ReasoningTokenRelation.INCLUDED_IN_OUTPUT,
            ),
            incomplete,
        )
    except LLMContractError:
        raise _InvalidResponse from None


def _tier(value):
    if type(value) is not dict:
        return None
    tier = value.get("service_tier")
    return tier if tier in {"standard", "priority", "batch"} else None


class _UsageAccumulator:
    def __init__(self):
        self._facts = {}
        self.breakdown_incomplete = False

    def accept(self, value):
        if type(value) is not dict:
            raise _InvalidResponse
        for field in (
            "input_tokens",
            "cache_creation_input_tokens",
            "cache_read_input_tokens",
            "output_tokens",
            "service_tier",
        ):
            if field in value:
                self._facts[field] = value[field]
        for field in ("cache_creation", "output_tokens_details"):
            if field in value:
                incoming = value[field]
                if type(incoming) is not dict:
                    raise _InvalidResponse
                current = self._facts.setdefault(field, {})
                if type(current) is not dict:
                    raise _InvalidResponse
                current.update(incoming)
        usage, incomplete = _usage(self._facts)
        self.breakdown_incomplete |= incomplete
        return usage

    @property
    def processing_tier(self):
        return _tier(self._facts)


def _stop_semantics(stop_reason, stop_details):
    if stop_reason is not None and type(stop_reason) is not str:
        raise _InvalidResponse
    if stop_details is not None and type(stop_details) is not dict:
        raise _InvalidResponse
    refusal = stop_reason == "refusal" or (
        type(stop_details) is dict and stop_details.get("type") == "refusal"
    )
    if refusal:
        return FinishReason.REFUSAL, StreamOutcome.REFUSAL, None
    if stop_reason in {"end_turn", "stop_sequence"}:
        return FinishReason.STOP, StreamOutcome.NORMAL, None
    if stop_reason == "max_tokens":
        return FinishReason.OUTPUT_LIMIT, StreamOutcome.NORMAL, None
    if stop_reason == "model_context_window_exceeded":
        return FinishReason.CONTEXT_LIMIT, StreamOutcome.NORMAL, None
    if stop_reason in {"tool_use", "pause_turn", "compaction"}:
        return FinishReason.UNKNOWN, StreamOutcome.NORMAL, "unsupported_terminal"
    return FinishReason.UNKNOWN, StreamOutcome.NORMAL, None


def _attempt(model, usage, finish, latency_ms, tier):
    return LLMAttemptSummary(model, usage, finish, latency_ms, tier)


def _diagnostics(response, request, secret, code=None):
    return ProviderDiagnostics(
        provider_request_id=_safe_identifier(response.headers.get("request-id"), secret, request),
        diagnostic_code=code,
    )


def _response(response, request, secret, latency_ms):
    data = _json_bytes(response.content)
    if (
        type(data) is not dict
        or data.get("type") != "message"
        or data.get("role") != "assistant"
        or type(data.get("model")) is not str
        or not data["model"].strip()
        or secret in data["model"]
        or type(data.get("content")) is not list
    ):
        raise _InvalidResponse
    usage, incomplete = _usage(data.get("usage"))
    finish, outcome, unsupported = _stop_semantics(
        data.get("stop_reason"), data.get("stop_details")
    )
    model = ModelRef(request.model.provider_id, data["model"])
    text = []
    tool_content = False
    for block in data["content"]:
        if type(block) is not dict or type(block.get("type")) is not str:
            raise _InvalidResponse
        kind = block["type"]
        if kind == "text":
            value = block.get("text")
            if type(value) is not str or secret in value:
                raise _InvalidResponse
            text.append(TextContent(value))
        elif kind in {"thinking", "redacted_thinking"}:
            continue
        elif kind == "tool_use":
            tool_content = True
        else:
            raise _InvalidResponse
    diagnostic = (
        "cache_write_ttl_breakdown_incomplete"
        if incomplete
        else "unknown_finish_reason"
        if finish is FinishReason.UNKNOWN and unsupported is None
        else None
    )
    diagnostics = _diagnostics(response, request, secret, diagnostic)
    if tool_content or unsupported is not None:
        return LLMFailure(
            LLMErrorCode.UNSUPPORTED_CAPABILITY,
            request.invocation_id,
            diagnostics,
            attempt=_attempt(model, usage, finish, latency_ms, _tier(data.get("usage"))),
        )
    return LLMResponse(
        invocation_id=request.invocation_id,
        model_used=model,
        content=tuple(text),
        finish_reason=finish,
        usage=usage,
        diagnostics=diagnostics,
        latency_ms=latency_ms,
        processing_tier=_tier(data.get("usage")),
    )


async def _bounded_error_data(response, limit):
    body = await bounded_body(response, limit)
    if body is None:
        return None
    try:
        return _json_bytes(body)
    except _InvalidResponse:
        return None


def _status_failure(response, request, secret, data=None):
    status = response.status_code
    error = data.get("error") if type(data) is dict else None
    error_type = error.get("type") if type(error) is dict else None
    if status == 400 or error_type == "invalid_request_error":
        code = LLMErrorCode.INVALID_REQUEST
    elif status in {401, 403} or error_type in {"authentication_error", "permission_error"}:
        code = LLMErrorCode.AUTHENTICATION
    elif status in {402, 404} or error_type in {"billing_error", "not_found_error"}:
        code = LLMErrorCode.CONFIGURATION
    elif status == 413 or error_type == "request_too_large":
        code = LLMErrorCode.INVALID_REQUEST
    elif status == 429 or error_type == "rate_limit_error":
        code = LLMErrorCode.RATE_LIMITED
    elif status == 504 or error_type == "timeout_error":
        code = LLMErrorCode.TIMEOUT
    elif status >= 500 or error_type in {"api_error", "overloaded_error"}:
        code = LLMErrorCode.PROVIDER_UNAVAILABLE
    else:
        code = LLMErrorCode.CONFIGURATION
    return LLMFailure(
        code,
        request.invocation_id,
        _diagnostics(response, request, secret, f"http:{status}"),
        dispatch_state=DispatchState.HTTP_RESPONSE_RECEIVED,
        http_status=status,
        retry_after_seconds=normalize_retry_after(response.headers.get("retry-after"))
        if status in {408, 429, 500, 502, 503, 504, 529}
        else None,
    )


def _stream_error(data, request, provider_request_id):
    error = data.get("error") if type(data) is dict else None
    error_type = error.get("type") if type(error) is dict else None
    code = {
        "authentication_error": LLMErrorCode.AUTHENTICATION,
        "permission_error": LLMErrorCode.AUTHENTICATION,
        "invalid_request_error": LLMErrorCode.INVALID_REQUEST,
        "rate_limit_error": LLMErrorCode.RATE_LIMITED,
        "timeout_error": LLMErrorCode.TIMEOUT,
    }.get(error_type, LLMErrorCode.PROVIDER_UNAVAILABLE)
    return LLMFailure(
        code,
        request.invocation_id,
        ProviderDiagnostics(provider_request_id, "anthropic_sse_error"),
        dispatch_state=DispatchState.DISPATCHED_OR_UNKNOWN,
    )


class AnthropicMessagesGateway:
    """Native /v1/messages client; lifecycle is borrowed by outer execution/routing."""

    capabilities = ModelCapabilities(text_generation=True)

    def __init__(
        self,
        config: ProviderConfig,
        credentials: CredentialProvider,
        *,
        profile: AnthropicMessagesProfile | None = None,
        workspace_id: AnthropicWorkspaceId | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        logger: StructuredLogger | None = None,
        stream_limits: StreamLimits | None = None,
    ):
        profile = profile if profile is not None else AnthropicMessagesProfile()
        if (
            not isinstance(config, ProviderConfig)
            or not isinstance(profile, AnthropicMessagesProfile)
            or workspace_id is not None
            and not isinstance(workspace_id, AnthropicWorkspaceId)
        ):
            raise LLMContractError("invalid_anthropic_configuration")
        self._config = config
        self._credentials = credentials
        self._profile = profile
        self._workspace_id = workspace_id
        self._endpoint = _endpoint(config)
        self._logger = logger
        self._stream_limits = stream_limits if stream_limits is not None else StreamLimits()
        if not isinstance(self._stream_limits, StreamLimits):
            raise LLMContractError("invalid_stream_limits")
        self.capabilities = ModelCapabilities(
            text_generation=True,
            streaming=profile.supports_streaming,
            structured_output=profile.supports_native_structured_output,
            structured_output_mode=StructuredOutputMode.NATIVE_JSON_SCHEMA
            if profile.supports_native_structured_output
            else StructuredOutputMode.NONE,
        )
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
            self._logger.emit(
                "llm",
                f"anthropic_{code.value}",
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
        return error_from_failure(self._error, request, failure)

    def _payload(self, request, *, streaming=False):
        if not isinstance(request, LLMRequest):
            raise LLMContractError("invalid_llm_request")
        if request.model.provider_id != self._config.provider_id:
            raise self._error(request, LLMErrorCode.CONFIGURATION)
        if request.streaming is not streaming:
            raise self._error(
                request,
                (
                    LLMErrorCode.UNSUPPORTED_CAPABILITY
                    if request.streaming
                    else LLMErrorCode.INVALID_REQUEST
                ),
            )
        if streaming and (
            not self._profile.supports_streaming or request.structured_output is not None
        ):
            raise self._error(request, LLMErrorCode.UNSUPPORTED_CAPABILITY)
        if (
            request.structured_output is not None
            and not self._profile.supports_native_structured_output
        ):
            raise self._error(request, LLMErrorCode.UNSUPPORTED_CAPABILITY)
        max_tokens = (
            request.max_output_tokens
            if request.max_output_tokens is not None
            else self._profile.default_max_output_tokens
        )
        if max_tokens is None:
            raise self._error(request, LLMErrorCode.INVALID_REQUEST)
        if (
            self._profile.max_output_tokens is not None
            and max_tokens > self._profile.max_output_tokens
        ):
            raise self._error(request, LLMErrorCode.INVALID_REQUEST)
        if request.temperature is not None and (
            self._profile.temperature_policy is None
            or not self._profile.temperature_policy.supports(request.temperature)
        ):
            raise self._error(request, LLMErrorCode.UNSUPPORTED_CAPABILITY)
        if len(request.stop_sequences) > 4:
            raise self._error(request, LLMErrorCode.INVALID_REQUEST)
        system, messages, conversation_started = [], [], False
        for message in request.messages:
            if any(
                not isinstance(block, TextContent) or not block.text for block in message.content
            ):
                raise self._error(request, LLMErrorCode.INVALID_REQUEST)
            if message.role is MessageRole.DEVELOPER:
                raise self._error(request, LLMErrorCode.UNSUPPORTED_CAPABILITY)
            blocks = [{"type": "text", "text": block.text} for block in message.content]
            if message.role is MessageRole.SYSTEM:
                if conversation_started:
                    raise self._error(request, LLMErrorCode.UNSUPPORTED_CAPABILITY)
                system.extend(blocks)
                continue
            if message.role not in {MessageRole.USER, MessageRole.ASSISTANT}:
                raise self._error(request, LLMErrorCode.UNSUPPORTED_CAPABILITY)
            conversation_started = True
            messages.append({"role": message.role.value, "content": blocks})
        if not messages:
            raise self._error(request, LLMErrorCode.INVALID_REQUEST)
        if messages[-1]["role"] == MessageRole.ASSISTANT.value and (
            not self._profile.supports_assistant_prefill or request.structured_output is not None
        ):
            raise self._error(request, LLMErrorCode.UNSUPPORTED_CAPABILITY)
        payload = {
            "model": request.model.model_id,
            "max_tokens": max_tokens,
            "messages": messages,
            "stream": streaming,
        }
        if system:
            payload["system"] = system
        if request.stop_sequences:
            payload["stop_sequences"] = list(request.stop_sequences)
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        return payload

    def _headers(self, secret, *, streaming=False):
        headers = {
            "Authorization": f"Bearer {secret}",
            "anthropic-version": ANTHROPIC_API_VERSION,
            "content-type": "application/json",
        }
        if streaming:
            headers["Accept"] = "text/event-stream"
        if self._workspace_id is not None:
            headers["anthropic-workspace-id"] = self._workspace_id.value
        return headers

    async def _secret(self, request):
        return await resolve_adapter_secret(
            request,
            closed=self._client.is_closed,
            config=self._config,
            credentials=self._credentials,
            error=self._error,
            token_pattern=_TOKEN,
        )

    async def generate(self, request: LLMRequest) -> LLMResponse:
        payload = self._payload(request)
        validator = None
        if request.structured_output is not None:
            try:
                validator = prepare_schema(request.structured_output)
            except InvalidStructuredSchema:
                raise self._error(request, LLMErrorCode.INVALID_REQUEST) from None
            payload["output_config"] = {
                "format": {"type": "json_schema", "schema": validator.schema}
            }
        secret = await self._secret(request)
        wire = response = None
        transport_failure = None
        try:
            wire = self._client.build_request(
                "POST", self._endpoint, json=payload, headers=self._headers(secret)
            )
            wire.headers.pop("cookie", None)
            started = perf_counter()
            try:
                response = await self._client.send(wire, follow_redirects=False)
            except (httpx.HTTPError, httpx.InvalidURL) as error:
                transport_failure = normalize_transport_failure(error)
            latency_ms = max(0, int((perf_counter() - started) * 1000))
            if transport_failure is not None:
                code, dispatch = transport_failure
                raise self._error(request, code, dispatch_state=dispatch)
            if not 200 <= response.status_code < 300:
                data = None
                if len(response.content) <= self._stream_limits.max_error_body_bytes:
                    try:
                        data = _json_bytes(response.content)
                    except _InvalidResponse:
                        pass
                raise self._failure_error(request, _status_failure(response, request, secret, data))
            try:
                result = _response(response, request, secret, latency_ms)
            except _InvalidResponse:
                raise self._error(
                    request,
                    LLMErrorCode.MALFORMED_RESPONSE,
                    dispatch_state=DispatchState.HTTP_RESPONSE_RECEIVED,
                    http_status=response.status_code,
                ) from None
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
                self._logger.emit(
                    "llm", "anthropic_completed", trace_id=str(request.invocation_id.value)
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
        wire = response = secret = None
        failure = completion = None
        try:
            payload = self._payload(request, streaming=True)
            secret = await self._secret(request)
            wire = self._client.build_request(
                "POST", self._endpoint, json=payload, headers=self._headers(secret, streaming=True)
            )
            wire.headers.pop("cookie", None)
            started_at = perf_counter()
            response = await self._client.send(wire, stream=True, follow_redirects=False)
            if not 200 <= response.status_code < 300:
                data = await _bounded_error_data(response, self._stream_limits.max_error_body_bytes)
                raise self._failure_error(request, _status_failure(response, request, secret, data))
            if not is_event_stream(response.headers.get("content-type", "")):
                raise self._error(
                    request,
                    LLMErrorCode.MALFORMED_RESPONSE,
                    dispatch_state=DispatchState.HTTP_RESPONSE_RECEIVED,
                    http_status=response.status_code,
                )
            decoder = SSEDecoder(self._stream_limits)
            provider_request_id = _safe_identifier(
                response.headers.get("request-id"), secret, request
            )
            started = False
            model = request.model
            usage = latest_emitted = None
            usage_state = _UsageAccumulator()
            open_blocks = {}
            terminal = None
            diagnostic = None
            async for fragment in response.aiter_bytes():
                for event in decoder.feed_named(fragment):
                    data = _json_bytes(event.data)
                    if type(data) is not dict or type(data.get("type")) is not str:
                        raise _InvalidResponse
                    name = event.event
                    if name not in _KNOWN_EVENTS:
                        if name is None or data["type"] != name:
                            raise _InvalidResponse
                        continue
                    if data["type"] != name:
                        raise _InvalidResponse
                    if name == "ping":
                        continue
                    if name == "error":
                        raise _StreamProviderFailure(
                            _stream_error(data, request, provider_request_id)
                        )
                    if name == "message_start":
                        message = data.get("message")
                        if (
                            started
                            or type(message) is not dict
                            or message.get("type") != "message"
                            or message.get("role") != "assistant"
                            or type(message.get("model")) is not str
                            or not message["model"].strip()
                            or secret in message["model"]
                            or message.get("content") != []
                            or message.get("stop_reason") is not None
                        ):
                            raise _InvalidResponse
                        started = True
                        model = ModelRef(request.model.provider_id, message["model"])
                        if self._logger is not None:
                            self._logger.emit(
                                "llm",
                                "anthropic_stream_started",
                                trace_id=str(request.invocation_id.value),
                            )
                        yield StreamStarted(request.invocation_id, model)
                        if message.get("usage") is not None:
                            usage = usage_state.accept(message["usage"])
                            if usage != latest_emitted:
                                latest_emitted = usage
                                yield UsageUpdate(request.invocation_id, usage)
                        continue
                    if not started:
                        raise _InvalidResponse
                    if name == "content_block_start":
                        index, block = data.get("index"), data.get("content_block")
                        if (
                            type(index) is not int
                            or index < 0
                            or index in open_blocks
                            or type(block) is not dict
                        ):
                            raise _InvalidResponse
                        kind = block.get("type")
                        if kind == "tool_use":
                            raise _UnsupportedResult
                        if kind == "text":
                            if block.get("text") != "":
                                raise _InvalidResponse
                        elif kind not in {"thinking", "redacted_thinking"}:
                            raise _InvalidResponse
                        open_blocks[index] = kind
                        continue
                    if name == "content_block_delta":
                        index, delta = data.get("index"), data.get("delta")
                        if (
                            type(index) is not int
                            or index not in open_blocks
                            or type(delta) is not dict
                        ):
                            raise _InvalidResponse
                        kind = delta.get("type")
                        if kind == "text_delta":
                            text = delta.get("text")
                            if (
                                open_blocks[index] != "text"
                                or type(text) is not str
                                or secret in text
                            ):
                                raise _InvalidResponse
                            yield TextDelta(request.invocation_id, text)
                        elif kind in {"thinking_delta", "signature_delta"}:
                            if open_blocks[index] not in {"thinking", "redacted_thinking"}:
                                raise _InvalidResponse
                        elif kind == "input_json_delta":
                            raise _UnsupportedResult
                        else:
                            raise _InvalidResponse
                        continue
                    if name == "content_block_stop":
                        index = data.get("index")
                        if type(index) is not int or index not in open_blocks:
                            raise _InvalidResponse
                        del open_blocks[index]
                        continue
                    if name == "message_delta":
                        delta = data.get("delta")
                        if type(delta) is not dict:
                            raise _InvalidResponse
                        reason = delta.get("stop_reason")
                        if reason is not None:
                            current = _stop_semantics(reason, delta.get("stop_details"))
                            if current[2] is not None:
                                raise _UnsupportedResult
                            if terminal is not None and terminal != current[:2]:
                                raise _InvalidResponse
                            terminal = current[:2]
                            if current[0] is FinishReason.UNKNOWN:
                                diagnostic = "unknown_finish_reason"
                        if data.get("usage") is not None:
                            usage = usage_state.accept(data["usage"])
                            if usage != latest_emitted:
                                latest_emitted = usage
                                yield UsageUpdate(request.invocation_id, usage)
                        continue
                    if name == "message_stop":
                        if terminal is None or open_blocks:
                            raise _InvalidResponse
                        if usage_state.breakdown_incomplete:
                            diagnostic = "cache_write_ttl_breakdown_incomplete"
                        completion = LLMStreamCompletion(
                            invocation_id=request.invocation_id,
                            model_used=model,
                            finish_reason=terminal[0],
                            outcome=terminal[1],
                            usage=usage,
                            latency_ms=max(0, int((perf_counter() - started_at) * 1000)),
                            diagnostics=ProviderDiagnostics(provider_request_id, diagnostic),
                            processing_tier=usage_state.processing_tier,
                        )
                        break
                if completion is not None:
                    break
            if completion is None:
                raise _InvalidResponse
        except LLMError as error:
            failure = error.failure
        except _StreamProviderFailure as error:
            failure = error.failure
        except (httpx.HTTPError, httpx.InvalidURL) as error:
            code, dispatch = normalize_transport_failure(
                error, response_received=response is not None
            )
            failure = self._error(request, code, dispatch_state=dispatch).failure
        except _UnsupportedResult:
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
                        code, dispatch = normalize_transport_failure(error, response_received=True)
                        failure = self._error(request, code, dispatch_state=dispatch).failure
        if failure is not None:
            yield StreamFailed(failure)
        else:
            if self._logger is not None:
                self._logger.emit(
                    "llm",
                    "anthropic_stream_completed",
                    trace_id=str(request.invocation_id.value),
                )
            yield StreamCompleted(completion)
