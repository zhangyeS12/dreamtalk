"""Provider failures retain safe categories across direct, group and SSE replies."""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from livingworld.adapters.http.chat_messages import _stream_failure
from livingworld.application.chat_reply import (
    ChatReplyGenerationError,
    _generation_error,
    generation_failure_code,
)
from livingworld.application.group_chat_reply import GroupChatReplyService
from livingworld.application.llm import InvocationId, LLMError, LLMErrorCode, LLMFailure


@pytest.mark.parametrize(
    "category, code",
    [
        (LLMErrorCode.AUTHENTICATION, "chat_provider_authentication"),
        (LLMErrorCode.PERMISSION_DENIED, "chat_provider_permission_denied"),
        (LLMErrorCode.NOT_FOUND, "chat_provider_not_found"),
        (LLMErrorCode.RATE_LIMITED, "chat_provider_rate_limited"),
        (LLMErrorCode.QUOTA_EXHAUSTED, "chat_provider_quota_exhausted"),
        (LLMErrorCode.TIMEOUT, "chat_provider_timeout"),
        (LLMErrorCode.CONTEXT_LIMIT, "chat_provider_context_limit"),
        (LLMErrorCode.UNSUPPORTED_CAPABILITY, "chat_provider_unsupported"),
    ],
)
def test_safe_provider_category_survives_generation_and_stream(category, code):
    failure = LLMFailure(category, InvocationId(uuid4()))
    error = _generation_error(failure)
    assert generation_failure_code(error) == code
    assert _stream_failure(error)[1] == code


def test_arbitrary_provider_details_cannot_be_returned_as_error_codes():
    error = ChatReplyGenerationError("PRIVATE-PROVIDER-DETAIL-CANARY")
    assert generation_failure_code(error) == "chat_generation_failed"
    assert "CANARY" not in str(_stream_failure(error))


def test_group_selector_preserves_provider_failure_instead_of_raising_attribute_error():
    async def run():
        calls = []

        class RejectingGateway:
            async def generate(self, request, **kwargs):
                calls.append(request)
                raise LLMError(LLMFailure(LLMErrorCode.AUTHENTICATION, request.invocation_id))

        service = SimpleNamespace(_gateway=RejectingGateway(), _selection=None)
        request = SimpleNamespace(invocation_id=InvocationId(uuid4()))
        with pytest.raises(ChatReplyGenerationError, match="^chat_provider_authentication$"):
            await GroupChatReplyService._generate(service, request, None)
        assert calls == [request]

    asyncio.run(run())
