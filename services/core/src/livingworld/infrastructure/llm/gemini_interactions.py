"""Native stable-v1 Gemini Interactions transport; one HTTP attempt, no SDK."""

import hashlib
import json
import re
from collections.abc import AsyncIterator
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

GEMINI_DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com"
GEMINI_INTERACTIONS_PATH = "/v1/interactions"
GEMINI_CONTINUATION_SCHEMA_VERSION = 1
_MAX_CONTINUATION_BYTES = 4 * 1024 * 1024
_DIAGNOSTIC = re.compile(r"[A-Za-z0-9_.:/-]{1,128}\Z")
_TOKEN = re.compile(r"[^\s\x00-\x1f\x7f]{8,4096}\Z")
_KNOWN_EVENTS = frozenset(
    {
        "interaction.created",
        "interaction.status_update",
        "step.start",
        "step.delta",
        "step.stop",
        "interaction.completed",
        "error",
        "done",
    }
)
_POLICY_CODES = frozenset(
    {"blocked", "content_filter", "content_filtered", "safety", "prohibited_content", "recitation"}
)


class _InvalidResponse(Exception):
    """Internal structural failure carrying no provider-controlled data."""


class _UnsupportedResult(Exception):
    """Known interaction semantic outside the approved text-only subset."""


class _ContinuationInvalid(Exception):
    """Local opaque-state validation failed before credential or network access."""


class _StreamProviderFailure(Exception):
    def __init__(self, failure: LLMFailure):
        self.failure = failure


@dataclass(frozen=True, slots=True, kw_only=True)
class GeminiInteractionsProfile:
    """Explicit configured capabilities; no model-name inference."""

    supports_streaming: bool = False
    supports_native_structured_output: bool = False
    supports_assistant_prefill: bool = False
    default_max_output_tokens: int | None = None
    max_output_tokens: int | None = None

    def __post_init__(self):
        if any(
            type(value) is not bool
            for value in (
                self.supports_streaming,
                self.supports_native_structured_output,
                self.supports_assistant_prefill,
            )
        ):
            raise LLMContractError("invalid_gemini_profile")
        for value in (self.default_max_output_tokens, self.max_output_tokens):
            if value is not None and (type(value) is not int or value < 1):
                raise LLMContractError("invalid_gemini_profile")
        if (
            self.default_max_output_tokens is not None
            and self.max_output_tokens is not None
            and self.default_max_output_tokens > self.max_output_tokens
        ):
            raise LLMContractError("invalid_gemini_profile")


def _endpoint(config: ProviderConfig) -> httpx.URL:
    base = config.endpoint.base_url if config.endpoint is not None else GEMINI_DEFAULT_BASE_URL
    parsed = urlsplit(base)
    if (
        parsed.netloc.endswith(":")
        or re.search(r"%(?![0-9a-fA-F]{2})", base)
        or any(unquote(part) in {".", ".."} for part in parsed.path.split("/"))
    ):
        raise LLMContractError("invalid_gemini_endpoint")
    invalid = False
    try:
        url = httpx.URL(base.rstrip("/") + GEMINI_INTERACTIONS_PATH)
        host = url.raw_host.decode("ascii")
        if ":" not in host and any(
            not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
            for label in host.rstrip(".").split(".")
        ):
            invalid = True
    except (ValueError, httpx.InvalidURL):
        invalid = True
    if invalid:
        raise LLMContractError("invalid_gemini_endpoint")
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
    input_tokens = _count(value.get("total_input_tokens"))
    cached = _count(value.get("total_cached_tokens"))
    output = _count(value.get("total_output_tokens"))
    thought = _count(value.get("total_thought_tokens"))
    total = _count(value.get("total_tokens"))
    uncached = None
    if input_tokens is not None and cached is not None:
        if cached > input_tokens:
            raise _InvalidResponse
        uncached = input_tokens - cached
    try:
        return LLMUsage(
            input_tokens=input_tokens,
            output_tokens=output,
            total_tokens=total,
            cached_input_tokens=cached,
            uncached_input_tokens=uncached,
            reasoning_output_tokens=thought,
            reasoning_token_relation=ReasoningTokenRelation.ADDITIVE_TO_OUTPUT,
        )
    except LLMContractError:
        raise _InvalidResponse from None


def _tier(value):
    return value if value in {"standard", "priority", "flex"} else None


def _machine_codes(data):
    errors = data.get("errors") if type(data) is dict else None
    if errors is None:
        return ()
    if type(errors) is not list:
        raise _InvalidResponse
    result = []
    for error in errors:
        code = error.get("code") if type(error) is dict else None
        if type(code) is not str or not code or len(code) > 128:
            raise _InvalidResponse
        normalized = code.rsplit("/", 1)[-1].lower()
        if not _DIAGNOSTIC.fullmatch(normalized):
            raise _InvalidResponse
        result.append(normalized)
    return tuple(result)


def _policy_blocked(data):
    return any(code in _POLICY_CODES for code in _machine_codes(data))


def _error_code(machine_code, status=None):
    code = machine_code.rsplit("/", 1)[-1].lower() if type(machine_code) is str else None
    if code in {"invalid_argument", "parameter_error", "out_of_range"} or status == 400:
        return LLMErrorCode.INVALID_REQUEST
    if code in {"unauthenticated", "authentication_error"} or status == 401:
        return LLMErrorCode.AUTHENTICATION
    if code in {"permission_denied", "permission_error"} or status == 403:
        return LLMErrorCode.PERMISSION_DENIED
    if code in {"not_found", "model_not_found"} or status == 404:
        return LLMErrorCode.NOT_FOUND
    if code in {"quota_exceeded", "billing_quota_exceeded"}:
        return LLMErrorCode.QUOTA_EXHAUSTED
    if code in {"rate_limit_exceeded", "too_many_requests"} or status == 429:
        return LLMErrorCode.RATE_LIMITED
    if code == "failed_precondition" or status == 412:
        return LLMErrorCode.FAILED_PRECONDITION
    if code in {"deadline_exceeded", "timeout"} or status in {408, 504}:
        return LLMErrorCode.TIMEOUT
    if code in {"unimplemented", "not_implemented"} or status == 501:
        return LLMErrorCode.UNSUPPORTED_CAPABILITY
    if code in {"service_unavailable", "internal", "api_error"} or status in {
        500,
        502,
        503,
    }:
        return LLMErrorCode.PROVIDER_UNAVAILABLE
    return (
        LLMErrorCode.PROVIDER_UNAVAILABLE
        if status and status >= 500
        else LLMErrorCode.CONFIGURATION
    )


def _artifact(layout, digest):
    payload = json.dumps(
        {"steps": layout},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    if not payload or len(payload) > _MAX_CONTINUATION_BYTES:
        raise _InvalidResponse
    return payload, digest.hexdigest()


def _plain_artifact(provider_id, steps):
    layout = []
    visible = hashlib.sha256()
    content = []
    for step in steps:
        if type(step) is not dict or type(step.get("type")) is not str:
            raise _InvalidResponse
        kind = step["type"]
        if kind == "thought":
            signature = step.get("signature")
            if type(signature) is not str or not signature:
                raise _InvalidResponse
            layout.append({"type": "thought", "signature": signature})
            continue
        if kind != "model_output":
            raise _UnsupportedResult
        blocks = step.get("content")
        if type(blocks) is not list:
            raise _InvalidResponse
        encoded = []
        for block in blocks:
            if type(block) is not dict or block.get("type") != "text":
                raise _UnsupportedResult
            text = block.get("text")
            if type(text) is not str:
                raise _InvalidResponse
            raw = text.encode("utf-8")
            visible.update(raw)
            encoded.append({"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
            content.append(TextContent(text))
        layout.append({"type": "model_output", "blocks": encoded})
    payload, digest = _artifact(layout, visible)
    return (
        tuple(content),
        ProviderContinuationArtifact(
            AdapterKind.GEMINI,
            provider_id,
            GEMINI_CONTINUATION_SCHEMA_VERSION,
            payload,
            digest,
        ),
    )


def _continuation_steps(message, provider_id):
    artifact = message.continuation
    if artifact is None or (
        artifact.adapter_kind is not AdapterKind.GEMINI or artifact.provider_id != provider_id
    ):
        return None
    if (
        artifact.artifact_schema_version != GEMINI_CONTINUATION_SCHEMA_VERSION
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
    if type(data) is not dict or set(data) != {"steps"} or type(data["steps"]) is not list:
        raise _ContinuationInvalid
    steps, offset = [], 0
    if len(data["steps"]) > 4096:
        raise _ContinuationInvalid
    for item in data["steps"]:
        if type(item) is not dict or item.get("type") not in {"thought", "model_output"}:
            raise _ContinuationInvalid
        if item["type"] == "thought":
            if (
                set(item) != {"type", "signature"}
                or type(item["signature"]) is not str
                or not item["signature"]
            ):
                raise _ContinuationInvalid
            steps.append({"type": "thought", "signature": item["signature"]})
            continue
        blocks = item.get("blocks")
        if set(item) != {"type", "blocks"} or type(blocks) is not list or len(blocks) > 4096:
            raise _ContinuationInvalid
        content = []
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
            content.append({"type": "text", "text": text})
            offset += length
        steps.append({"type": "model_output", "content": content})
    if offset != len(visible):
        raise _ContinuationInvalid
    return steps


class _StreamArtifact:
    """Incremental layout/hash state; it never retains visible output text."""

    def __init__(self, provider_id):
        self.provider_id = provider_id
        self.layout = []
        self.visible = hashlib.sha256()
        self.active = None

    def start(self, kind, step):
        if self.active is not None:
            raise _InvalidResponse
        if kind == "thought":
            item = {"type": "thought", "signature": step.get("signature")}
            if item["signature"] is not None and type(item["signature"]) is not str:
                raise _InvalidResponse
            self.active = item
            return ()
        if kind != "model_output":
            raise _UnsupportedResult
        self.active = {"type": "model_output", "blocks": []}
        blocks = step.get("content", [])
        if type(blocks) is not list:
            raise _InvalidResponse
        texts = []
        for block in blocks:
            if type(block) is not dict or block.get("type") != "text":
                raise _UnsupportedResult
            text = block.get("text")
            if type(text) is not str:
                raise _InvalidResponse
            self._new_block(text)
            texts.append(text)
        return tuple(texts)

    def _new_block(self, text):
        raw = text.encode("utf-8")
        self.visible.update(raw)
        self.active["blocks"].append({"bytes": len(raw), "hash": hashlib.sha256(raw), "open": True})

    def text(self, text):
        if self.active is None or self.active["type"] != "model_output" or type(text) is not str:
            raise _InvalidResponse
        raw = text.encode("utf-8")
        blocks = self.active["blocks"]
        if not blocks:
            self._new_block(text)
        else:
            self.visible.update(raw)
            blocks[-1]["bytes"] += len(raw)
            blocks[-1]["hash"].update(raw)

    def signature(self, signature):
        if (
            self.active is None
            or self.active["type"] != "thought"
            or type(signature) is not str
            or not signature
            or self.active["signature"] not in {None, signature}
        ):
            raise _InvalidResponse
        self.active["signature"] = signature

    def stop(self):
        if self.active is None:
            raise _InvalidResponse
        item = self.active
        self.active = None
        if item["type"] == "thought":
            if not item["signature"]:
                raise _InvalidResponse
        else:
            item["blocks"] = [
                {"bytes": block["bytes"], "sha256": block["hash"].hexdigest()}
                for block in item["blocks"]
            ]
        self.layout.append(item)

    def artifact(self):
        if self.active is not None:
            raise _InvalidResponse
        payload, digest = _artifact(self.layout, self.visible)
        return ProviderContinuationArtifact(
            AdapterKind.GEMINI,
            self.provider_id,
            GEMINI_CONTINUATION_SCHEMA_VERSION,
            payload,
            digest,
        )


def _attempt(model, usage, finish, latency_ms, tier):
    return LLMAttemptSummary(model, usage, finish, latency_ms, tier)


def _interaction(data, request, secret, latency_ms, request_id):
    if (
        type(data) is not dict
        or data.get("object") != "interaction"
        or type(data.get("model")) is not str
        or not data["model"].strip()
        or secret in data["model"]
        or type(data.get("status")) is not str
    ):
        raise _InvalidResponse
    model = ModelRef(request.model.provider_id, data["model"])
    usage = _usage(data.get("usage"))
    tier = _tier(data.get("service_tier"))
    status = data["status"]
    finish = FinishReason.STOP if status == "completed" else FinishReason.OUTPUT_LIMIT
    diagnostics = ProviderDiagnostics(request_id)
    if _policy_blocked(data):
        return LLMResponse(
            invocation_id=request.invocation_id,
            model_used=model,
            content=(),
            finish_reason=FinishReason.REFUSAL,
            usage=usage,
            diagnostics=diagnostics,
            latency_ms=latency_ms,
            processing_tier=tier,
        )
    if status in {"completed", "incomplete"}:
        steps = data.get("steps")
        if type(steps) is not list:
            raise _InvalidResponse
        content, continuation = _plain_artifact(request.model.provider_id, steps)
        return LLMResponse(
            invocation_id=request.invocation_id,
            model_used=model,
            content=content,
            finish_reason=finish,
            usage=usage,
            diagnostics=diagnostics,
            latency_ms=latency_ms,
            processing_tier=tier,
            continuation=continuation,
        )
    machine = _machine_codes(data)
    code = (
        LLMErrorCode.UNSUPPORTED_CAPABILITY
        if status == "requires_action"
        else LLMErrorCode.CANCELLED
        if status == "cancelled"
        else _error_code(machine[0] if machine else None)
        if status == "failed"
        else None
    )
    if code is None:
        raise _InvalidResponse
    return LLMFailure(
        code,
        request.invocation_id,
        ProviderDiagnostics(request_id, machine[0] if machine else status),
        attempt=_attempt(model, usage, FinishReason.UNKNOWN, latency_ms, tier),
        dispatch_state=DispatchState.HTTP_RESPONSE_RECEIVED,
    )


async def _bounded_error_data(response, limit):
    body = await bounded_body(response, limit)
    if body is None:
        return None
    try:
        return _json(body)
    except _InvalidResponse:
        return None


class GeminiInteractionsGateway:
    """Native ``POST /v1/interactions`` client with stateless continuation support."""

    capabilities = ModelCapabilities(text_generation=True)

    def __init__(
        self,
        config: ProviderConfig,
        credentials: CredentialProvider,
        *,
        profile: GeminiInteractionsProfile | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        logger: StructuredLogger | None = None,
        stream_limits: StreamLimits | None = None,
    ):
        profile = profile if profile is not None else GeminiInteractionsProfile()
        if not isinstance(config, ProviderConfig) or not isinstance(
            profile, GeminiInteractionsProfile
        ):
            raise LLMContractError("invalid_gemini_configuration")
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
                f"gemini_{code.value}",
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
        # Stable v1 currently exposes no temperature field. Never infer or clamp it.
        if request.temperature is not None:
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
        system = None
        steps = []
        conversation_started = False
        for message in request.messages:
            if any(
                not isinstance(block, TextContent) or not block.text for block in message.content
            ):
                raise self._error(request, LLMErrorCode.INVALID_REQUEST)
            if message.role is MessageRole.DEVELOPER:
                raise self._error(request, LLMErrorCode.UNSUPPORTED_CAPABILITY)
            if message.role is MessageRole.SYSTEM:
                if conversation_started or system is not None:
                    raise self._error(request, LLMErrorCode.UNSUPPORTED_CAPABILITY)
                system = "".join(block.text for block in message.content)
                continue
            if message.role not in {MessageRole.USER, MessageRole.ASSISTANT}:
                raise self._error(request, LLMErrorCode.UNSUPPORTED_CAPABILITY)
            conversation_started = True
            if message.role is MessageRole.USER:
                steps.append(
                    {
                        "type": "user_input",
                        "content": [
                            {"type": "text", "text": block.text} for block in message.content
                        ],
                    }
                )
            else:
                try:
                    prior = _continuation_steps(message, self._config.provider_id)
                except _ContinuationInvalid:
                    raise self._error(request, LLMErrorCode.CONTINUATION_STATE_INVALID) from None
                steps.extend(
                    prior
                    if prior is not None
                    else [
                        {
                            "type": "model_output",
                            "content": [
                                {"type": "text", "text": block.text} for block in message.content
                            ],
                        }
                    ]
                )
        if not steps:
            raise self._error(request, LLMErrorCode.INVALID_REQUEST)
        if request.messages[-1].role is MessageRole.ASSISTANT and (
            not self._profile.supports_assistant_prefill or request.structured_output is not None
        ):
            raise self._error(request, LLMErrorCode.UNSUPPORTED_CAPABILITY)
        generation = {"thinking_summaries": "none"}
        if max_tokens is not None:
            generation["max_output_tokens"] = max_tokens
        if request.stop_sequences:
            generation["stop_sequences"] = list(request.stop_sequences)
        payload = {
            "model": request.model.model_id,
            "input": steps,
            "stream": streaming,
            "store": False,
            "background": False,
            "generation_config": generation,
        }
        if system is not None:
            payload["system_instruction"] = system
        return payload

    def _headers(self, secret, *, streaming=False):
        headers = {"x-goog-api-key": secret, "content-type": "application/json"}
        if streaming:
            headers["Accept"] = "text/event-stream"
        return headers

    async def _secret(self, request):
        if self._client.is_closed or self._config.secret_ref is None:
            raise self._error(request, LLMErrorCode.CONFIGURATION)
        failed = False
        try:
            credential = await self._credentials.resolve(self._config.secret_ref)
        except Exception:
            failed = True
        if failed or not isinstance(credential, SecretValue):
            raise self._error(request, LLMErrorCode.AUTHENTICATION)
        secret = credential.reveal_for_adapter()
        del credential
        if not _TOKEN.fullmatch(secret):
            del secret
            raise self._error(request, LLMErrorCode.AUTHENTICATION)
        return secret

    def _status_failure(self, response, request, secret, data=None):
        error = data.get("error") if type(data) is dict else None
        machine = error.get("code") if type(error) is dict else None
        code = _error_code(machine, response.status_code)
        diagnostic = machine if type(machine) is str and _DIAGNOSTIC.fullmatch(machine) else None
        rejected = code is LLMErrorCode.QUOTA_EXHAUSTED
        return LLMFailure(
            code,
            request.invocation_id,
            ProviderDiagnostics(
                _safe_identifier(response.headers.get("x-request-id"), secret, request),
                diagnostic,
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
            payload["response_format"] = {
                "type": "text",
                "mime_type": "application/json",
                "schema": validator.schema,
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
                result = _interaction(
                    _json(response.content), request, secret, latency_ms, request_id
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
                    "llm", "gemini_completed", trace_id=str(request.invocation_id.value)
                )
            return result
        finally:
            if wire is not None:
                wire.headers.pop("x-goog-api-key", None)
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
            interaction_id = None
            request_id = _safe_identifier(response.headers.get("x-request-id"), secret, request)
            artifact = _StreamArtifact(request.model.provider_id)
            open_index = None
            seen_indices = set()
            usage = None
            async for fragment in response.aiter_bytes():
                for event in decoder.feed_named(fragment):
                    name = event.event
                    if name == "done" and event.data == "[DONE]":
                        continue
                    data = _json(event.data)
                    if type(data) is not dict or type(data.get("event_type")) is not str:
                        raise _InvalidResponse
                    if name is None or data["event_type"] != name:
                        raise _InvalidResponse
                    if name not in _KNOWN_EVENTS:
                        continue
                    if name == "error":
                        error = data.get("error")
                        machine = error.get("code") if type(error) is dict else None
                        normalized_machine = (
                            machine.rsplit("/", 1)[-1].lower()
                            if type(machine) is str and 0 < len(machine) <= 128
                            else None
                        )
                        if normalized_machine is not None and not _DIAGNOSTIC.fullmatch(
                            normalized_machine
                        ):
                            normalized_machine = None
                        raise _StreamProviderFailure(
                            LLMFailure(
                                _error_code(normalized_machine),
                                request.invocation_id,
                                ProviderDiagnostics(
                                    request_id,
                                    normalized_machine or "gemini_sse_error",
                                ),
                                dispatch_state=DispatchState.DISPATCHED_OR_UNKNOWN,
                            )
                        )
                    if name == "interaction.created":
                        interaction = data.get("interaction")
                        if (
                            started
                            or type(interaction) is not dict
                            or interaction.get("object") != "interaction"
                            or interaction.get("status") != "in_progress"
                            or type(interaction.get("id")) is not str
                            or not _DIAGNOSTIC.fullmatch(interaction["id"])
                            or type(interaction.get("model")) is not str
                            or not interaction["model"].strip()
                            or secret in interaction["model"]
                        ):
                            raise _InvalidResponse
                        interaction_id = interaction["id"]
                        model = ModelRef(request.model.provider_id, interaction["model"])
                        started = True
                        yield StreamStarted(request.invocation_id, model)
                        continue
                    if not started:
                        raise _InvalidResponse
                    if name == "interaction.status_update":
                        if data.get("interaction_id") != interaction_id or data.get(
                            "status"
                        ) not in {
                            "in_progress",
                            "completed",
                            "incomplete",
                            "requires_action",
                            "failed",
                            "cancelled",
                        }:
                            raise _InvalidResponse
                        continue
                    if name == "step.start":
                        index, step = data.get("index"), data.get("step")
                        if (
                            type(index) is not int
                            or index < 0
                            or index in seen_indices
                            or open_index is not None
                            or type(step) is not dict
                        ):
                            raise _InvalidResponse
                        seen_indices.add(index)
                        open_index = index
                        texts = artifact.start(step.get("type"), step)
                        for text in texts:
                            yield TextDelta(request.invocation_id, text)
                        continue
                    if name == "step.delta":
                        index, delta = data.get("index"), data.get("delta")
                        if (
                            index != open_index
                            or type(delta) is not dict
                            or type(delta.get("type")) is not str
                        ):
                            raise _InvalidResponse
                        kind = delta["type"]
                        if kind == "text":
                            text = delta.get("text")
                            if type(text) is not str or secret in text:
                                raise _InvalidResponse
                            artifact.text(text)
                            yield TextDelta(request.invocation_id, text)
                        elif kind == "thought_signature":
                            artifact.signature(delta.get("signature"))
                        elif kind == "thought_summary":
                            continue
                        else:
                            raise _UnsupportedResult
                        continue
                    if name == "step.stop":
                        if data.get("index") != open_index:
                            raise _InvalidResponse
                        artifact.stop()
                        open_index = None
                        continue
                    if name == "interaction.completed":
                        interaction = data.get("interaction")
                        if (
                            open_index is not None
                            or type(interaction) is not dict
                            or interaction.get("id") != interaction_id
                            or interaction.get("object") != "interaction"
                            or interaction.get("model") != model.model_id
                            or type(interaction.get("status")) is not str
                        ):
                            raise _InvalidResponse
                        usage = _usage(interaction.get("usage"))
                        if usage is not None:
                            yield UsageUpdate(request.invocation_id, usage)
                        status = interaction["status"]
                        policy = _policy_blocked(interaction)
                        if status in {"completed", "incomplete"} or policy:
                            outcome = (
                                StreamOutcome.CONTENT_FILTERED if policy else StreamOutcome.NORMAL
                            )
                            finish = (
                                FinishReason.REFUSAL
                                if policy
                                else FinishReason.STOP
                                if status == "completed"
                                else FinishReason.OUTPUT_LIMIT
                            )
                            completion = LLMStreamCompletion(
                                invocation_id=request.invocation_id,
                                model_used=model,
                                finish_reason=finish,
                                outcome=outcome,
                                usage=usage,
                                latency_ms=max(0, int((perf_counter() - started_at) * 1000)),
                                diagnostics=ProviderDiagnostics(request_id),
                                processing_tier=_tier(interaction.get("service_tier")),
                                continuation=artifact.artifact(),
                            )
                            break
                        machine = _machine_codes(interaction)
                        code = (
                            LLMErrorCode.UNSUPPORTED_CAPABILITY
                            if status == "requires_action"
                            else LLMErrorCode.CANCELLED
                            if status == "cancelled"
                            else _error_code(machine[0] if machine else None)
                        )
                        raise _StreamProviderFailure(
                            LLMFailure(
                                code,
                                request.invocation_id,
                                ProviderDiagnostics(request_id, machine[0] if machine else status),
                                attempt=_attempt(
                                    model,
                                    usage,
                                    FinishReason.UNKNOWN,
                                    max(0, int((perf_counter() - started_at) * 1000)),
                                    _tier(interaction.get("service_tier")),
                                ),
                                dispatch_state=DispatchState.HTTP_RESPONSE_RECEIVED,
                                http_status=response.status_code,
                            )
                        )
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
                wire.headers.pop("x-goog-api-key", None)
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
                    "llm", "gemini_stream_completed", trace_id=str(request.invocation_id.value)
                )
            yield StreamCompleted(completion)
