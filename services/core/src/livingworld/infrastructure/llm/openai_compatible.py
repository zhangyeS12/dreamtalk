"""One-shot Chat Completions translation with opt-in structured modes; no provider SDK."""

import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from time import perf_counter
from urllib.parse import unquote, urlsplit

import httpx

from livingworld.application.llm import (
    FinishReason,
    LLMContractError,
    LLMError,
    LLMErrorCode,
    LLMFailure,
    LLMRequest,
    LLMResponse,
    LLMStreamEvent,
    LLMUsage,
    MessageRole,
    ModelCapabilities,
    ModelRef,
    ProviderDiagnostics,
    StructuredOutputMode,
    TextContent,
)
from livingworld.application.llm_config import CredentialProvider, ProviderConfig, SecretValue
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
    "prompt_tokens_details": ("cached_tokens", "audio_tokens"),
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
    structured_output_mode: StructuredOutputMode = StructuredOutputMode.NONE

    def __post_init__(self):
        if type(self.supports_n) is not bool:
            raise LLMContractError("invalid_chat_profile")
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
    return LLMUsage(
        input_tokens=_count(value.get("prompt_tokens")),
        output_tokens=_count(value.get("completion_tokens")),
        total_tokens=_count(value.get("total_tokens")),
        details=details,
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
    )


def _status_failure(response, request, secret):
    status = response.status_code
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
    )


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
        self.capabilities = ModelCapabilities(
            text_generation=True,
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

    def _error(self, request, code, diagnostics=None, *, attempt=None, structured_detail=None):
        if self._logger is not None:
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
            )
        )

    def _payload(self, request):
        if not isinstance(request, LLMRequest):
            raise LLMContractError("invalid_llm_request")
        if request.model.provider_id != self._config.provider_id:
            raise self._error(request, LLMErrorCode.CONFIGURATION)
        if request.streaming or (
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
            "stream": False,
        }
        if request.stop_sequences:
            payload["stop"] = list(request.stop_sequences)
        if self._profile.supports_n:
            payload["n"] = 1
        return payload

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
            else:
                payload["response_format"] = {"type": "json_object"}
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
        wire = None
        response = None
        failure_code = None
        try:
            wire = self._client.build_request(
                "POST", self._endpoint, json=payload, headers={"Authorization": f"Bearer {secret}"}
            )
            wire.headers.pop("cookie", None)
            started = perf_counter()
            try:
                response = await self._client.send(wire, follow_redirects=False)
            except httpx.TimeoutException:
                failure_code = LLMErrorCode.TIMEOUT
            except httpx.InvalidURL:
                failure_code = LLMErrorCode.CONFIGURATION
            except httpx.HTTPError:
                failure_code = LLMErrorCode.PROVIDER_UNAVAILABLE
            latency_ms = max(0, int((perf_counter() - started) * 1000))
            if failure_code is not None:
                raise self._error(request, failure_code)
            if not 200 <= response.status_code < 300:
                failure = _status_failure(response, request, secret)
                raise self._error(request, failure.code, failure.diagnostics)
            malformed = False
            try:
                result = _response(response, request, secret, latency_ms)
            except _InvalidResponse:
                malformed = True
            if malformed:
                raise self._error(request, LLMErrorCode.MALFORMED_RESPONSE)
            if isinstance(result, LLMFailure):
                raise self._error(request, result.code, result.diagnostics)
            if validator is not None:
                result = process_structured(request.structured_output, validator, result)
                if isinstance(result, LLMFailure):
                    raise self._error(
                        request,
                        result.code,
                        attempt=result.attempt,
                        structured_detail=result.structured_detail,
                    )
            if self._logger is not None:
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
        raise self._error(request, LLMErrorCode.UNSUPPORTED_CAPABILITY)
        yield  # Unreachable: retain the port's async-iterator shape without fake chunks.
