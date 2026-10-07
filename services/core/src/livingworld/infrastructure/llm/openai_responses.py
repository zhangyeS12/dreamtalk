"""Native OpenAI Responses transport; one HTTP attempt, no SDK or provider state."""

import asyncio
import hashlib
import json
import re
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, replace
from time import perf_counter
from urllib.parse import unquote, urlsplit

import httpx

from livingworld.application.llm import (
    AdapterKind,
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
    ProviderContinuationArtifact,
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

OPENAI_RESPONSES_DEFAULT_BASE_URL = "https://api.openai.com"
OPENAI_RESPONSES_PATH = "/v1/responses"
OPENAI_RESPONSES_CONTINUATION_SCHEMA_VERSION = 1
_MAX_CONTINUATION_BYTES = 4 * 1024 * 1024
_DIAGNOSTIC = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")
_TOKEN = re.compile(r"[^\s\x00-\x1f\x7f]{8,4096}\Z")
_SCHEMA_NAME = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
_QUOTA_CODES = frozenset(
    {
        "insufficient_quota",
        "billing_hard_limit_reached",
        "billing_not_active",
        "usage_limit_reached",
        "quota_exceeded",
    }
)
_FILTER_REASONS = frozenset({"content_filter", "content_filtered", "safety", "policy_violation"})
_KNOWN_EVENTS = frozenset(
    {
        "response.created",
        "response.in_progress",
        "response.output_item.added",
        "response.output_item.done",
        "response.content_part.added",
        "response.content_part.done",
        "response.output_text.delta",
        "response.output_text.done",
        "response.refusal.delta",
        "response.refusal.done",
        "response.reasoning_text.delta",
        "response.reasoning_text.done",
        "response.reasoning_summary_part.added",
        "response.reasoning_summary_part.done",
        "response.reasoning_summary_text.delta",
        "response.reasoning_summary_text.done",
        "response.completed",
        "response.incomplete",
        "response.failed",
        "error",
    }
)


class _InvalidResponse(Exception):
    """Internal structural failure carrying no provider-controlled data."""


class _UnsupportedResult(Exception):
    """Known provider semantic outside the approved text-only subset."""


class _ContinuationInvalid(Exception):
    """Local opaque-state validation failed before credential or network access."""


class _StreamProviderFailure(Exception):
    def __init__(self, failure: LLMFailure):
        self.failure = failure


@dataclass(frozen=True, slots=True, kw_only=True)
class OpenAIResponsesProfile:
    """Explicit configured capabilities; model names never imply behavior."""

    supports_streaming: bool = False
    supports_native_structured_output: bool = False
    supports_temperature: bool = False
    supports_reasoning_continuation: bool = False
    default_max_output_tokens: int | None = None
    max_output_tokens: int | None = None

    def __post_init__(self):
        if any(
            type(value) is not bool
            for value in (
                self.supports_streaming,
                self.supports_native_structured_output,
                self.supports_temperature,
                self.supports_reasoning_continuation,
            )
        ):
            raise LLMContractError("invalid_openai_responses_profile")
        for value in (self.default_max_output_tokens, self.max_output_tokens):
            if value is not None and (type(value) is not int or value < 1):
                raise LLMContractError("invalid_openai_responses_profile")
        if (
            self.default_max_output_tokens is not None
            and self.max_output_tokens is not None
            and self.default_max_output_tokens > self.max_output_tokens
        ):
            raise LLMContractError("invalid_openai_responses_profile")


def _endpoint(config: ProviderConfig) -> httpx.URL:
    base = (
        config.endpoint.base_url
        if config.endpoint is not None
        else OPENAI_RESPONSES_DEFAULT_BASE_URL
    )
    parsed = urlsplit(base)
    if (
        parsed.netloc.endswith(":")
        or re.search(r"%(?![0-9a-fA-F]{2})", base)
        or any(unquote(part) in {".", ".."} for part in parsed.path.split("/"))
    ):
        raise LLMContractError("invalid_openai_responses_endpoint")
    invalid = False
    try:
        url = httpx.URL(base.rstrip("/") + OPENAI_RESPONSES_PATH)
        host = url.raw_host.decode("ascii")
        if ":" not in host and any(
            not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
            for label in host.rstrip(".").split(".")
        ):
            invalid = True
    except (ValueError, httpx.InvalidURL):
        invalid = True
    if invalid:
        raise LLMContractError("invalid_openai_responses_endpoint")
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


def _json(value):
    try:
        return json.loads(
            value,
            parse_constant=_invalid_constant,
            object_pairs_hook=_unique_object,
        )
    except (ValueError, UnicodeError, RecursionError):
        raise _InvalidResponse from None


def _plain(value):
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


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
        return None
    if type(value) is not dict:
        raise _InvalidResponse
    input_tokens = _count(value.get("input_tokens"))
    output_tokens = _count(value.get("output_tokens"))
    total_tokens = _count(value.get("total_tokens"))
    input_details = value.get("input_tokens_details", {})
    output_details = value.get("output_tokens_details", {})
    if type(input_details) is not dict or type(output_details) is not dict:
        raise _InvalidResponse
    cached = _count(input_details.get("cached_tokens"))
    reasoning = _count(output_details.get("reasoning_tokens"))
    uncached = None
    if input_tokens is not None and cached is not None:
        if cached > input_tokens:
            raise _InvalidResponse
        uncached = input_tokens - cached
    try:
        return LLMUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cached_input_tokens=cached,
            uncached_input_tokens=uncached,
            reasoning_output_tokens=reasoning,
            reasoning_token_relation=ReasoningTokenRelation.INCLUDED_IN_OUTPUT,
        )
    except LLMContractError:
        raise _InvalidResponse from None


def _tier(value):
    return value if value in {"default", "auto", "flex", "priority"} else None


def _schema_wire_name(value):
    if _SCHEMA_NAME.fullmatch(value):
        return value
    return "lw_" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]


def _machine_error(data):
    error = data.get("error") if type(data) is dict else None
    if error is None and type(data) is dict and data.get("type") == "error":
        error = data
    if error is None:
        return None
    if type(error) is not dict:
        raise _InvalidResponse
    candidates = (error.get("code"), error.get("type"))
    for candidate in candidates:
        if candidate is not None:
            if type(candidate) is not str or not _DIAGNOSTIC.fullmatch(candidate):
                raise _InvalidResponse
            return candidate.lower()
    return None


def _error_code(machine_code, status=None):
    code = machine_code.lower() if type(machine_code) is str else None
    if code in _QUOTA_CODES:
        return LLMErrorCode.QUOTA_EXHAUSTED
    if code in {"authentication_error", "invalid_api_key"} or status == 401:
        return LLMErrorCode.AUTHENTICATION
    if code in {"permission_denied", "permission_error"} or status == 403:
        return LLMErrorCode.PERMISSION_DENIED
    if code in {"model_not_found", "not_found_error"} or status == 404:
        return LLMErrorCode.NOT_FOUND
    if code in {"context_length_exceeded", "context_window_exceeded"}:
        return LLMErrorCode.CONTEXT_LIMIT
    if code in {"rate_limit_exceeded", "rate_limit_error"} or status == 429:
        return LLMErrorCode.RATE_LIMITED
    if code in {"request_timeout", "timeout"} or status in {408, 504}:
        return LLMErrorCode.TIMEOUT
    if code in {"server_error", "api_error", "overloaded_error"} or status in {
        500,
        502,
        503,
    }:
        return LLMErrorCode.PROVIDER_UNAVAILABLE
    if code in {"invalid_request_error", "invalid_parameter", "invalid_value"} or status == 400:
        return LLMErrorCode.INVALID_REQUEST
    return (
        LLMErrorCode.PROVIDER_UNAVAILABLE
        if status is not None and status >= 500
        else LLMErrorCode.CONFIGURATION
    )


def _attempt(model, usage, finish, latency_ms, tier):
    return LLMAttemptSummary(model, usage, finish, latency_ms, tier)


def _artifact_payload(layout, digest):
    payload = json.dumps(
        {"items": layout}, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    if not payload or len(payload) > _MAX_CONTINUATION_BYTES:
        raise _InvalidResponse
    return payload, digest.hexdigest()


def _artifact_item_fields(item, secret):
    item_id = item.get("id")
    status = item.get("status")
    if item_id is not None and (
        type(item_id) is not str or not _DIAGNOSTIC.fullmatch(item_id) or secret in item_id
    ):
        raise _InvalidResponse
    if status is not None and status not in {"in_progress", "completed", "incomplete"}:
        raise _InvalidResponse
    result = {}
    if item_id is not None:
        result["id"] = item_id
    if status is not None:
        result["status"] = status
    return result


def _parse_output(
    items,
    *,
    provider_id,
    secret,
    continuation_enabled,
    stream_visible=None,
):
    if type(items) is not list or len(items) > 4096:
        raise _InvalidResponse
    content = []
    layout = []
    visible = hashlib.sha256()
    refusal = False
    terminal_keys = set()
    for output_index, item in enumerate(items):
        if type(item) is not dict or type(item.get("type")) is not str:
            raise _InvalidResponse
        kind = item["type"]
        if kind == "reasoning":
            if continuation_enabled:
                encrypted = item.get("encrypted_content")
                if type(encrypted) is not str or not encrypted or secret in encrypted:
                    raise _InvalidResponse
                stored = {
                    "type": "reasoning",
                    **_artifact_item_fields(item, secret),
                    "encrypted_content": encrypted,
                }
                layout.append(stored)
            continue
        if kind != "message":
            raise _UnsupportedResult
        if item.get("role") != "assistant":
            raise _InvalidResponse
        blocks = item.get("content")
        if type(blocks) is not list or len(blocks) > 4096:
            raise _InvalidResponse
        encoded = []
        for content_index, block in enumerate(blocks):
            if type(block) is not dict or type(block.get("type")) is not str:
                raise _InvalidResponse
            block_type = block["type"]
            if block_type == "refusal":
                if type(block.get("refusal")) is not str:
                    raise _InvalidResponse
                refusal = True
                continue
            if block_type != "output_text":
                raise _UnsupportedResult
            text = block.get("text")
            if type(text) is not str or secret in text:
                raise _InvalidResponse
            raw = text.encode("utf-8")
            visible.update(raw)
            key = (output_index, content_index)
            terminal_keys.add(key)
            if stream_visible is not None:
                stream_visible.verify(key, raw)
            else:
                content.append(TextContent(text))
            encoded.append({"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
        if continuation_enabled:
            layout.append(
                {
                    "type": "message",
                    **_artifact_item_fields(item, secret),
                    "blocks": encoded,
                }
            )
    if stream_visible is not None:
        stream_visible.finish(terminal_keys, visible.hexdigest())
    continuation = None
    if continuation_enabled and not refusal:
        payload, digest = _artifact_payload(layout, visible)
        continuation = ProviderContinuationArtifact(
            AdapterKind.OPENAI_RESPONSES,
            provider_id,
            OPENAI_RESPONSES_CONTINUATION_SCHEMA_VERSION,
            payload,
            digest,
        )
    return tuple(content), continuation, refusal


def _continuation_items(message, provider_id):
    artifact = message.continuation
    if artifact is None or (
        artifact.adapter_kind is not AdapterKind.OPENAI_RESPONSES
        or artifact.provider_id != provider_id
    ):
        return None
    if (
        artifact.artifact_schema_version != OPENAI_RESPONSES_CONTINUATION_SCHEMA_VERSION
        or len(artifact.opaque_payload) > _MAX_CONTINUATION_BYTES
    ):
        raise _ContinuationInvalid
    visible = "".join(block.text for block in message.content).encode("utf-8")
    if hashlib.sha256(visible).hexdigest() != artifact.visible_content_sha256:
        raise _ContinuationInvalid
    try:
        data = _json(artifact.opaque_payload)
    except _InvalidResponse:
        raise _ContinuationInvalid from None
    if type(data) is not dict or set(data) != {"items"} or type(data["items"]) is not list:
        raise _ContinuationInvalid
    if len(data["items"]) > 4096:
        raise _ContinuationInvalid
    result = []
    offset = 0
    for item in data["items"]:
        if type(item) is not dict or item.get("type") not in {"reasoning", "message"}:
            raise _ContinuationInvalid
        if item["type"] == "reasoning":
            allowed = {"type", "id", "status", "encrypted_content"}
            if not set(item) <= allowed or set(item) - {"id", "status"} != {
                "type",
                "encrypted_content",
            }:
                raise _ContinuationInvalid
            encrypted = item["encrypted_content"]
            if type(encrypted) is not str or not encrypted:
                raise _ContinuationInvalid
            restored = {
                "type": "reasoning",
                "encrypted_content": encrypted,
                "summary": [],
            }
            if "id" in item:
                restored["id"] = item["id"]
            if "status" in item:
                restored["status"] = item["status"]
            result.append(restored)
            continue
        allowed = {"type", "id", "status", "blocks"}
        if not set(item) <= allowed or set(item) - {"id", "status"} != {"type", "blocks"}:
            raise _ContinuationInvalid
        blocks = item["blocks"]
        if type(blocks) is not list or len(blocks) > 4096:
            raise _ContinuationInvalid
        restored_blocks = []
        for block in blocks:
            if type(block) is not dict or set(block) != {"bytes", "sha256"}:
                raise _ContinuationInvalid
            length, digest = block["bytes"], block["sha256"]
            if type(length) is not int or length < 0 or type(digest) is not str:
                raise _ContinuationInvalid
            raw = visible[offset : offset + length]
            if len(raw) != length or hashlib.sha256(raw).hexdigest() != digest:
                raise _ContinuationInvalid
            try:
                text = raw.decode("utf-8", errors="strict")
            except UnicodeError:
                raise _ContinuationInvalid from None
            restored_blocks.append({"type": "output_text", "text": text})
            offset += length
        restored = {"type": "message", "role": "assistant", "content": restored_blocks}
        if "id" in item:
            restored["id"] = item["id"]
        if "status" in item:
            restored["status"] = item["status"]
        result.append(restored)
    if offset != len(visible):
        raise _ContinuationInvalid
    return result


class _StreamVisible:
    """Hashes deltas incrementally and never retains generated text."""

    def __init__(self):
        self._blocks = {}
        self._overall = hashlib.sha256()

    def delta(self, key, text):
        if (
            type(key) is not tuple
            or len(key) != 2
            or any(type(index) is not int or index < 0 for index in key)
            or type(text) is not str
        ):
            raise _InvalidResponse
        raw = text.encode("utf-8")
        state = self._blocks.setdefault(key, [0, hashlib.sha256()])
        state[0] += len(raw)
        state[1].update(raw)
        self._overall.update(raw)

    def verify(self, key, raw):
        state = self._blocks.get(key)
        if state is None:
            if raw:
                raise _InvalidResponse
            return
        if state[0] != len(raw) or state[1].hexdigest() != hashlib.sha256(raw).hexdigest():
            raise _InvalidResponse

    def finish(self, terminal_keys, terminal_digest):
        if set(self._blocks) != terminal_keys or self._overall.hexdigest() != terminal_digest:
            raise _InvalidResponse


def _diagnostics(request_id, response_id=None, code=None):
    return ProviderDiagnostics(
        provider_request_id=request_id,
        diagnostic_code=code,
        provider_response_id=response_id,
    )


def _incomplete_reason(data):
    details = data.get("incomplete_details")
    if type(details) is not dict or type(details.get("reason")) is not str:
        raise _InvalidResponse
    reason = details["reason"].lower()
    if not _DIAGNOSTIC.fullmatch(reason):
        raise _InvalidResponse
    return reason


def _response(data, request, secret, latency_ms, request_id, continuation_enabled):
    if (
        type(data) is not dict
        or data.get("object") != "response"
        or type(data.get("status")) is not str
        or type(data.get("model")) is not str
        or not data["model"].strip()
        or secret in data["model"]
    ):
        raise _InvalidResponse
    response_id = _safe_identifier(data.get("id"), secret, request)
    model = ModelRef(request.model.provider_id, data["model"])
    usage = _usage(data.get("usage"))
    tier = _tier(data.get("service_tier"))
    status = data["status"]
    diagnostics = _diagnostics(request_id, response_id)
    if status == "failed":
        machine = _machine_error(data)
        return LLMFailure(
            _error_code(machine),
            request.invocation_id,
            _diagnostics(request_id, response_id, machine or "response_failed"),
            attempt=_attempt(model, usage, FinishReason.UNKNOWN, latency_ms, tier),
            dispatch_state=DispatchState.HTTP_RESPONSE_RECEIVED,
        )
    if status not in {"completed", "incomplete"}:
        raise _InvalidResponse
    content, continuation, refusal = _parse_output(
        data.get("output"),
        provider_id=request.model.provider_id,
        secret=secret,
        continuation_enabled=continuation_enabled,
    )
    if status == "incomplete":
        reason = _incomplete_reason(data)
        if reason in _FILTER_REASONS:
            refusal = True
        elif reason != "max_output_tokens":
            raise _InvalidResponse
    finish = (
        FinishReason.REFUSAL
        if refusal
        else FinishReason.STOP
        if status == "completed"
        else FinishReason.OUTPUT_LIMIT
    )
    return LLMResponse(
        invocation_id=request.invocation_id,
        model_used=model,
        content=() if refusal else content,
        finish_reason=finish,
        usage=usage,
        diagnostics=diagnostics,
        latency_ms=latency_ms,
        processing_tier=tier,
        continuation=None if refusal else continuation,
    )


async def _bounded_error_data(response, limit):
    body = await bounded_body(response, limit)
    if body is None:
        return None
    try:
        return _json(body)
    except _InvalidResponse:
        return None


class OpenAIResponsesGateway:
    """Native ``POST /v1/responses`` client with local stateless continuation."""

    capabilities = ModelCapabilities(text_generation=True)

    def __init__(
        self,
        config: ProviderConfig,
        credentials: CredentialProvider,
        *,
        profile: OpenAIResponsesProfile | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        logger: StructuredLogger | None = None,
        stream_limits: StreamLimits | None = None,
    ):
        profile = profile if profile is not None else OpenAIResponsesProfile()
        if not isinstance(config, ProviderConfig) or not isinstance(
            profile, OpenAIResponsesProfile
        ):
            raise LLMContractError("invalid_openai_responses_configuration")
        self._config = config
        self._credentials = credentials
        self._profile = profile
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
                f"openai_responses_{code.value}",
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
                LLMErrorCode.UNSUPPORTED_CAPABILITY
                if request.streaming
                else LLMErrorCode.INVALID_REQUEST,
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
        if request.temperature is not None and not self._profile.supports_temperature:
            raise self._error(request, LLMErrorCode.UNSUPPORTED_CAPABILITY)
        if request.stop_sequences:
            raise self._error(request, LLMErrorCode.UNSUPPORTED_CAPABILITY)
        max_tokens = (
            request.max_output_tokens
            if request.max_output_tokens is not None
            else self._profile.default_max_output_tokens
        )
        if (
            max_tokens is not None
            and self._profile.max_output_tokens is not None
            and max_tokens > self._profile.max_output_tokens
        ):
            raise self._error(request, LLMErrorCode.INVALID_REQUEST)
        inputs = []
        for message in request.messages:
            prior = None
            if (
                message.role is MessageRole.ASSISTANT
                and self._profile.supports_reasoning_continuation
            ):
                try:
                    prior = _continuation_items(message, self._config.provider_id)
                except _ContinuationInvalid:
                    raise self._error(request, LLMErrorCode.CONTINUATION_STATE_INVALID) from None
            if prior is not None:
                inputs.extend(prior)
                continue
            inputs.append(
                {
                    "type": "message",
                    "role": message.role.value,
                    "content": [
                        {
                            "type": "input_text",
                            "text": block.text,
                        }
                        for block in message.content
                    ],
                }
            )
        payload = {
            "model": request.model.model_id,
            "input": inputs,
            "stream": streaming,
            "store": False,
            "background": False,
            "truncation": "disabled",
        }
        if max_tokens is not None:
            payload["max_output_tokens"] = max_tokens
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if self._profile.supports_reasoning_continuation:
            payload["include"] = ["reasoning.encrypted_content"]
        return payload

    @property
    def supports_input_count(self) -> bool:
        # Same-named proxy models cannot inherit the direct service guarantee.
        return str(self._endpoint) == "https://api.openai.com/v1/responses"

    def token_reservation_payload(self, request: LLMRequest) -> dict | None:
        """Use the actual stateless text input; no approximate local template."""
        if (
            not self.supports_input_count
            or request.structured_output is not None
            or any(message.continuation is not None for message in request.messages)
        ):
            return None
        payload = self._payload(request, streaming=request.streaming)
        return {key: payload[key] for key in ("model", "input", "truncation")}

    async def count_input_tokens(self, request: LLMRequest, payload: dict) -> int | None:
        """One bounded count request, never generation, retries or arbitrary URLs."""
        if payload != self.token_reservation_payload(request):
            return None
        secret = None
        try:
            async with asyncio.timeout(5):
                secret = await self._secret(request)
                wire = self._client.build_request(
                    "POST",
                    "https://api.openai.com/v1/responses/input_tokens",
                    headers=self._headers(secret),
                    json=payload,
                )
                response = await self._client.send(wire, stream=True, follow_redirects=False)
                try:
                    if response.status_code != 200:
                        return None
                    body = await bounded_body(response, 4096)
                    data = _json(body) if body is not None else None
                    if type(data) is not dict or data.get("object") != "response.input_tokens":
                        return None
                    count = data.get("input_tokens")
                    return count if type(count) is int and 0 <= count <= 2**63 - 1 else None
                finally:
                    await response.aclose()
        except (TimeoutError, httpx.HTTPError, LLMError, LLMContractError, _InvalidResponse):
            return None
        finally:
            # Neither the body, raw errors, cookies nor the credential are cached.
            self._client.cookies.clear()
            del secret

    def _headers(self, secret, *, streaming=False):
        headers = {"Authorization": f"Bearer {secret}", "content-type": "application/json"}
        if streaming:
            headers["Accept"] = "text/event-stream"
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

    def _status_failure(self, response, request, secret, data=None):
        machine = _machine_error(data) if type(data) is dict else None
        code = _error_code(machine, response.status_code)
        rejected = code is LLMErrorCode.QUOTA_EXHAUSTED
        return LLMFailure(
            code,
            request.invocation_id,
            _diagnostics(
                _safe_identifier(response.headers.get("x-request-id"), secret, request),
                code=machine,
            ),
            dispatch_state=DispatchState.REJECTED_BEFORE_EXECUTION
            if rejected
            else DispatchState.HTTP_RESPONSE_RECEIVED,
            http_status=response.status_code,
            retry_after_seconds=normalize_retry_after(response.headers.get("retry-after"))
            if response.status_code in {408, 429, 500, 502, 503, 504}
            else None,
        )

    async def generate(self, request: LLMRequest) -> LLMResponse:
        payload = self._payload(request)
        validator = None
        if request.structured_output is not None:
            try:
                validator = prepare_schema(request.structured_output)
            except InvalidStructuredSchema:
                raise self._error(request, LLMErrorCode.INVALID_REQUEST) from None
            payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": _schema_wire_name(request.structured_output.schema_name),
                    "schema": _plain(request.structured_output.schema),
                    "strict": True,
                }
            }
        secret = await self._secret(request)
        wire = response = None
        try:
            wire = self._client.build_request(
                "POST", self._endpoint, json=payload, headers=self._headers(secret)
            )
            wire.headers.pop("cookie", None)
            started = perf_counter()
            try:
                response = await self._client.send(wire, follow_redirects=False)
            except (httpx.HTTPError, httpx.InvalidURL) as error:
                code, dispatch = normalize_transport_failure(error)
                raise self._error(request, code, dispatch_state=dispatch) from None
            latency_ms = max(0, int((perf_counter() - started) * 1000))
            if not 200 <= response.status_code < 300:
                data = None
                if len(response.content) <= self._stream_limits.max_error_body_bytes:
                    try:
                        data = _json(response.content)
                    except _InvalidResponse:
                        pass
                raise self._failure_error(
                    request, self._status_failure(response, request, secret, data)
                )
            request_id = _safe_identifier(response.headers.get("x-request-id"), secret, request)
            try:
                result = _response(
                    _json(response.content),
                    request,
                    secret,
                    latency_ms,
                    request_id,
                    self._profile.supports_reasoning_continuation,
                )
            except _UnsupportedResult:
                raise self._error(
                    request,
                    LLMErrorCode.UNSUPPORTED_CAPABILITY,
                    dispatch_state=DispatchState.HTTP_RESPONSE_RECEIVED,
                    http_status=response.status_code,
                ) from None
            except _InvalidResponse:
                raise self._error(
                    request,
                    LLMErrorCode.MALFORMED_RESPONSE,
                    dispatch_state=DispatchState.HTTP_RESPONSE_RECEIVED,
                    http_status=response.status_code,
                ) from None
            if isinstance(result, LLMFailure):
                raise self._failure_error(
                    request, replace(result, http_status=response.status_code)
                )
            if validator is not None and result.finish_reason is not FinishReason.REFUSAL:
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
                    "llm", "openai_responses_completed", trace_id=str(request.invocation_id.value)
                )
            return result
        finally:
            if wire is not None:
                wire.headers.pop("Authorization", None)
            self._client.cookies.clear()
            if response is not None:
                await response.aclose()
            secret = None

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
                raise self._failure_error(
                    request, self._status_failure(response, request, secret, data)
                )
            if not is_event_stream(response.headers.get("content-type", "")):
                raise self._error(
                    request,
                    LLMErrorCode.MALFORMED_RESPONSE,
                    dispatch_state=DispatchState.HTTP_RESPONSE_RECEIVED,
                    http_status=response.status_code,
                )
            decoder = SSEDecoder(self._stream_limits)
            started = False
            model = request.model
            response_id = None
            request_id = _safe_identifier(response.headers.get("x-request-id"), secret, request)
            visible = _StreamVisible()
            refusal_seen = False
            async for fragment in response.aiter_bytes():
                for event in decoder.feed_named(fragment):
                    data = _json(event.data)
                    if type(data) is not dict or type(data.get("type")) is not str:
                        raise _InvalidResponse
                    name = event.event or data["type"]
                    if data["type"] != name:
                        raise _InvalidResponse
                    if name not in _KNOWN_EVENTS:
                        continue
                    if name == "error":
                        machine = _machine_error(data)
                        raise _StreamProviderFailure(
                            LLMFailure(
                                _error_code(machine),
                                request.invocation_id,
                                _diagnostics(
                                    request_id,
                                    response_id,
                                    machine or "openai_responses_sse_error",
                                ),
                                dispatch_state=DispatchState.DISPATCHED_OR_UNKNOWN,
                            )
                        )
                    if name == "response.created":
                        current = data.get("response")
                        if (
                            started
                            or type(current) is not dict
                            or current.get("object") != "response"
                            or current.get("status") not in {"queued", "in_progress"}
                            or type(current.get("model")) is not str
                            or not current["model"].strip()
                            or secret in current["model"]
                        ):
                            raise _InvalidResponse
                        response_id = _safe_identifier(current.get("id"), secret, request)
                        if response_id is None:
                            raise _InvalidResponse
                        model = ModelRef(request.model.provider_id, current["model"])
                        started = True
                        yield StreamStarted(request.invocation_id, model)
                        continue
                    if not started:
                        raise _InvalidResponse
                    if name in {"response.in_progress"}:
                        current = data.get("response")
                        if type(current) is not dict or current.get("id") != response_id:
                            raise _InvalidResponse
                        continue
                    if name in {"response.output_item.added", "response.output_item.done"}:
                        item = data.get("item")
                        if type(item) is not dict or item.get("type") not in {
                            "reasoning",
                            "message",
                        }:
                            if type(item) is dict and type(item.get("type")) is str:
                                raise _UnsupportedResult
                            raise _InvalidResponse
                        continue
                    if name in {"response.content_part.added", "response.content_part.done"}:
                        part = data.get("part")
                        if type(part) is not dict or part.get("type") not in {
                            "output_text",
                            "refusal",
                        }:
                            if type(part) is dict and type(part.get("type")) is str:
                                raise _UnsupportedResult
                            raise _InvalidResponse
                        if part["type"] == "refusal":
                            refusal_seen = True
                        continue
                    if name == "response.output_text.delta":
                        text = data.get("delta")
                        if type(text) is not str or secret in text:
                            raise _InvalidResponse
                        key = (data.get("output_index"), data.get("content_index"))
                        visible.delta(key, text)
                        yield TextDelta(request.invocation_id, text)
                        continue
                    if name == "response.output_text.done":
                        text = data.get("text")
                        if type(text) is not str or secret in text:
                            raise _InvalidResponse
                        key = (data.get("output_index"), data.get("content_index"))
                        visible.verify(key, text.encode("utf-8"))
                        continue
                    if name in {"response.refusal.delta", "response.refusal.done"}:
                        field = "delta" if name.endswith(".delta") else "refusal"
                        if type(data.get(field)) is not str:
                            raise _InvalidResponse
                        refusal_seen = True
                        continue
                    if name.startswith("response.reasoning_"):
                        # Provider reasoning text/summary is deliberately discarded.
                        if name.endswith((".delta", ".done")) and not name.endswith(
                            ("part.added", "part.done")
                        ):
                            field = "delta" if name.endswith(".delta") else "text"
                            if type(data.get(field)) is not str:
                                raise _InvalidResponse
                        elif name.endswith(("part.added", "part.done")):
                            part = data.get("part")
                            if type(part) is not dict or part.get("type") != "summary_text":
                                raise _InvalidResponse
                        continue
                    if name in {"response.completed", "response.incomplete", "response.failed"}:
                        current = data.get("response")
                        if (
                            type(current) is not dict
                            or current.get("object") != "response"
                            or current.get("id") != response_id
                            or current.get("model") != model.model_id
                        ):
                            raise _InvalidResponse
                        usage = _usage(current.get("usage"))
                        tier = _tier(current.get("service_tier"))
                        latency_ms = max(0, int((perf_counter() - started_at) * 1000))
                        if usage is not None:
                            yield UsageUpdate(request.invocation_id, usage)
                        if name == "response.failed":
                            if current.get("status") != "failed":
                                raise _InvalidResponse
                            machine = _machine_error(current)
                            raise _StreamProviderFailure(
                                LLMFailure(
                                    _error_code(machine),
                                    request.invocation_id,
                                    _diagnostics(
                                        request_id,
                                        response_id,
                                        machine or "response_failed",
                                    ),
                                    attempt=_attempt(
                                        model, usage, FinishReason.UNKNOWN, latency_ms, tier
                                    ),
                                    dispatch_state=DispatchState.HTTP_RESPONSE_RECEIVED,
                                    http_status=response.status_code,
                                )
                            )
                        expected_status = (
                            "completed" if name == "response.completed" else "incomplete"
                        )
                        if current.get("status") != expected_status:
                            raise _InvalidResponse
                        _, continuation, terminal_refusal = _parse_output(
                            current.get("output"),
                            provider_id=request.model.provider_id,
                            secret=secret,
                            continuation_enabled=self._profile.supports_reasoning_continuation,
                            stream_visible=visible,
                        )
                        refused = refusal_seen or terminal_refusal
                        if name == "response.incomplete":
                            reason = _incomplete_reason(current)
                            if reason in _FILTER_REASONS:
                                refused = True
                            elif reason != "max_output_tokens":
                                raise _InvalidResponse
                        finish = (
                            FinishReason.REFUSAL
                            if refused
                            else FinishReason.STOP
                            if name == "response.completed"
                            else FinishReason.OUTPUT_LIMIT
                        )
                        completion = LLMStreamCompletion(
                            invocation_id=request.invocation_id,
                            model_used=model,
                            finish_reason=finish,
                            outcome=StreamOutcome.REFUSAL
                            if refused and terminal_refusal
                            else StreamOutcome.CONTENT_FILTERED
                            if refused
                            else StreamOutcome.NORMAL,
                            usage=usage,
                            latency_ms=latency_ms,
                            diagnostics=_diagnostics(request_id, response_id),
                            processing_tier=tier,
                            continuation=None if refused else continuation,
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
                wire.headers.pop("Authorization", None)
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
                    "openai_responses_stream_completed",
                    trace_id=str(request.invocation_id.value),
                )
            yield StreamCompleted(completion)
