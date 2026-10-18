"""Protocol-neutral adapter helpers; token policies remain provider-specific."""

from collections.abc import Callable
from re import Pattern

from livingworld.application.llm import (
    DispatchState,
    LLMAttemptSummary,
    LLMError,
    LLMErrorCode,
    LLMFailure,
    LLMRequest,
    ProviderDiagnostics,
    StructuredFailureDetail,
)
from livingworld.application.llm_config import CredentialProvider, ProviderConfig, SecretValue


def error_from_failure(
    error: Callable[..., LLMError], request: LLMRequest, failure: LLMFailure
) -> LLMError:
    return error(
        request,
        failure.code,
        failure.diagnostics,
        attempt=failure.attempt,
        structured_detail=failure.structured_detail,
        dispatch_state=failure.dispatch_state,
        http_status=failure.http_status,
        retry_after_seconds=failure.retry_after_seconds,
    )


async def resolve_adapter_secret(
    request: LLMRequest,
    *,
    closed: bool,
    config: ProviderConfig,
    credentials: CredentialProvider,
    error: Callable[..., LLMError],
    token_pattern: Pattern[str],
) -> str:
    if closed or config.secret_ref is None:
        raise error(request, LLMErrorCode.CONFIGURATION)
    credential: SecretValue | None = None
    failed = False
    try:
        credential = await credentials.resolve(config.secret_ref)
    except Exception:
        failed = True
    # Raise outside the resolver exception handler; never attach credential errors.
    if failed or not isinstance(credential, SecretValue):
        raise error(request, LLMErrorCode.AUTHENTICATION)
    secret = credential.reveal_for_adapter()
    del credential
    if not token_pattern.fullmatch(secret):
        del secret
        raise error(request, LLMErrorCode.AUTHENTICATION)
    return secret


def response_count(value: object, invalid: type[Exception]) -> int | None:
    """A reported token counter is nullable, integral and nonnegative; bool is invalid."""
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise invalid
    return value


def safe_diagnostic_identifier(
    value: object,
    secret: str,
    request: LLMRequest,
    pattern: Pattern[str],
) -> str | None:
    """Reject identifiers containing credentials or submitted text before diagnostics."""
    if type(value) is not str or not pattern.fullmatch(value) or secret in value:
        return None
    protected = [block.text for message in request.messages for block in message.content]
    protected.extend(request.stop_sequences)
    return None if any(text and text in value for text in protected) else value


def adapter_error(
    request: LLMRequest,
    code: LLMErrorCode,
    diagnostics: ProviderDiagnostics | None = None,
    *,
    attempt: LLMAttemptSummary | None = None,
    structured_detail: StructuredFailureDetail | None = None,
    dispatch_state: DispatchState = DispatchState.NOT_DISPATCHED,
    http_status: int | None = None,
    retry_after_seconds: float | None = None,
) -> LLMError:
    """One content-free failure envelope; protocol-specific classification stays in adapters."""
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
