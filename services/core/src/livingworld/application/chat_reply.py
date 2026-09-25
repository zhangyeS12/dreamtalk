"""One direct Character reply through the governed LLM and durable chat boundary."""

from __future__ import annotations

from dataclasses import replace
from typing import Protocol
from uuid import uuid4

from livingworld.application.chat_context import DirectChatContextBuilder
from livingworld.application.chat_messages import ChatMessage, ChatMessageService, PlayerSend
from livingworld.application.llm import (
    FinishReason,
    InvocationId,
    LLMPurpose,
    LLMRequest,
    LLMResponse,
    ModelRef,
)
from livingworld.application.llm_budget import BoundGuarantee, PreflightUsageBounder
from livingworld.application.llm_chat_turn_budget import ChatTurnTokenBudget, TurnTokenBudgetError


class ChatReplyValidationError(ValueError):
    """Stable local label; never includes model text or prompt data."""


class DirectChatGateway(Protocol):
    def plan(self, request: LLMRequest): ...

    async def generate(
        self,
        request: LLMRequest,
        *,
        turn_budget: ChatTurnTokenBudget,
    ) -> LLMResponse: ...


class DirectChatReplyService:
    def __init__(
        self,
        messages: ChatMessageService,
        context: DirectChatContextBuilder,
        gateway: DirectChatGateway,
        token_bounder: PreflightUsageBounder,
        model: ModelRef,
        max_output_tokens: int,
    ) -> None:
        if (
            not isinstance(model, ModelRef)
            or type(max_output_tokens) is not int
            or max_output_tokens < 1
            or not callable(getattr(token_bounder, "bound", None))
        ):
            raise ValueError("chat_generation_configuration_invalid")
        self._messages = messages
        self._context = context
        self._gateway = gateway
        self._token_bounder = token_bounder
        self._model = model
        self._max_output_tokens = max_output_tokens

    async def reply(self, sent: PlayerSend) -> ChatMessage:
        if not isinstance(sent, PlayerSend):
            raise ValueError("chat_send_required")
        context = await self._context.build(sent)
        request = LLMRequest(
            invocation_id=InvocationId(uuid4()),
            model=self._model,
            purpose=LLMPurpose("character_dialogue"),
            messages=context.messages,
            max_output_tokens=min(sent.token_ceiling, self._max_output_tokens),
        )
        bound = self._token_bounder.bound(request)
        if bound is None or bound.guarantee is not BoundGuarantee.HARD_UPPER_BOUND:
            raise TurnTokenBudgetError("turn_input_bound_unavailable")
        remaining_for_output = sent.token_ceiling - bound.input_tokens
        if remaining_for_output < 1:
            raise TurnTokenBudgetError("turn_token_limit_exceeded")
        if request.max_output_tokens > remaining_for_output:
            request = replace(request, max_output_tokens=remaining_for_output)
            bound = self._token_bounder.bound(request)
        if (
            bound is None
            or bound.guarantee is not BoundGuarantee.HARD_UPPER_BOUND
            or bound.input_tokens + bound.output_tokens > sent.token_ceiling
        ):
            raise TurnTokenBudgetError("turn_token_limit_exceeded")
        # Reject missing route/capability before consuming the one-time claim.
        self._gateway.plan(request)
        claim = await self._messages.claim_direct(sent.message.conversation_id, sent.turn_id)
        if claim.player_message != sent.message or claim.token_ceiling != sent.token_ceiling:
            raise ChatReplyValidationError("chat_send_changed")
        budget = ChatTurnTokenBudget(claim.token_ceiling)
        response = await self._gateway.generate(request, turn_budget=budget)
        if budget.bound_violated:
            raise ChatReplyValidationError("chat_token_bound_violated")
        if (
            response.invocation_id != request.invocation_id
            or response.finish_reason not in {FinishReason.STOP, FinishReason.REFUSAL}
            or not response.text.strip()
            or len(response.text.encode("utf-8")) > 65536
        ):
            raise ChatReplyValidationError("chat_reply_invalid")
        return await self._messages.complete_direct(claim, response.text)
