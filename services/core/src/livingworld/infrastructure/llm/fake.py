"""Deterministic test adapter; no provider translation, validation, prices or persistence."""

import asyncio
from collections.abc import AsyncIterator, Mapping
from types import MappingProxyType

from livingworld.application.llm import (
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
    ModelCapabilities,
    ModelRef,
    StreamCompleted,
    StreamFailed,
    StreamOutcome,
    StreamStarted,
    TextContent,
    TextDelta,
    UsageUpdate,
    _type,
)


class StaticModelCatalog:
    def __init__(self, entries: Mapping[ModelRef, ModelCapabilities]):
        copied = dict(entries)
        for model, capabilities in copied.items():
            _type(model, ModelRef, "model_ref")
            _type(capabilities, ModelCapabilities, "capabilities")
        self._entries = MappingProxyType(copied)

    def capabilities(self, model: ModelRef) -> ModelCapabilities | None:
        _type(model, ModelRef, "model_ref")
        return self._entries.get(model)


class FakeModelGateway:
    def __init__(
        self,
        *,
        chunks: tuple[str, ...] = ("synthetic", " response"),
        usage: LLMUsage | None = None,
        finish_reason: FinishReason = FinishReason.STOP,
        error: LLMErrorCode | None = None,
    ):
        if not isinstance(chunks, (list, tuple)) or any(type(chunk) is not str for chunk in chunks):
            raise LLMContractError("invalid_fake_chunks")
        _type(finish_reason, FinishReason, "finish_reason")
        if usage is not None:
            _type(usage, LLMUsage, "usage")
        if error is not None:
            _type(error, LLMErrorCode, "error_code")
        self._chunks, self._usage, self._finish, self._error = (
            tuple(chunks),
            usage,
            finish_reason,
            error,
        )

    def _request(self, request, *, streaming):
        _type(request, LLMRequest, "llm_request")
        if request.streaming is not streaming:
            raise LLMError(LLMFailure(LLMErrorCode.INVALID_REQUEST, request.invocation_id))

    def _response(self, request):
        return LLMResponse(
            invocation_id=request.invocation_id,
            model_used=request.model,
            content=(TextContent("".join(self._chunks)),),
            finish_reason=self._finish,
            usage=self._usage,
            structured_result=None,
            latency_ms=0,
        )

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self._request(request, streaming=False)
        await asyncio.sleep(0)  # Cooperative cancellation, not artificial latency.
        if self._error is not None:
            raise LLMError(LLMFailure(self._error, request.invocation_id))
        return self._response(request)

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamEvent]:
        try:
            self._request(request, streaming=True)
        except LLMError as error:
            yield StreamFailed(error.failure)
            return
        if request.structured_output is not None:
            yield StreamFailed(
                LLMFailure(LLMErrorCode.UNSUPPORTED_CAPABILITY, request.invocation_id)
            )
            return
        await asyncio.sleep(0)
        yield StreamStarted(request.invocation_id, request.model)
        if self._error is not None:
            yield StreamFailed(LLMFailure(self._error, request.invocation_id))
            return
        if self._finish is not FinishReason.REFUSAL:
            for chunk in self._chunks:
                await asyncio.sleep(0)
                if chunk:
                    yield TextDelta(request.invocation_id, chunk)
        if self._usage is not None:
            yield UsageUpdate(request.invocation_id, self._usage)
        yield StreamCompleted(
            LLMStreamCompletion(
                invocation_id=request.invocation_id,
                model_used=request.model,
                finish_reason=self._finish,
                outcome=StreamOutcome.REFUSAL
                if self._finish is FinishReason.REFUSAL
                else StreamOutcome.NORMAL,
                usage=self._usage,
                latency_ms=0,
            )
        )
