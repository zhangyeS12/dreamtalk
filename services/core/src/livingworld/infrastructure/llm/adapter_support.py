"""Protocol-neutral adapter helpers; token policies remain provider-specific."""

from collections.abc import Callable
from re import Pattern

from livingworld.application.llm import LLMError, LLMErrorCode, LLMFailure, LLMRequest
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
