"""One direct Character reply through the governed LLM and durable chat boundary."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Protocol
from uuid import uuid4

from livingworld.application.chat_context import DirectChatContextBuilder
from livingworld.application.chat_messages import ChatMessage, ChatMessageService, PlayerSend
from livingworld.application.llm import (
    FinishReason,
    InvocationId,
    LLMError,
    LLMPurpose,
    LLMRequest,
    LLMResponse,
    ModelRef,
)
from livingworld.application.llm_accounting import AccountingInfrastructureError
from livingworld.application.llm_budget import (
    BoundGuarantee,
    BudgetAdmissionError,
    BudgetIntegrityError,
    PreflightUsageBounder,
)
from livingworld.application.llm_chat_turn_budget import ChatTurnTokenBudget, TurnTokenBudgetError
from livingworld.application.llm_execution import ExecutionDeadlineError
from livingworld.application.llm_routing import ModelSelection, RoutingError


class ChatReplyValidationError(ValueError):
    """Stable local label; never includes model text or prompt data."""


class ChatReplyUnavailableError(RuntimeError):
    """The configured route or its credentials cannot be used for this turn."""


class ChatReplyBudgetError(ValueError):
    """Trusted token or financial admission cannot authorize a physical attempt."""


class ChatReplyGenerationError(RuntimeError):
    """Provider execution failed after the durable one-time claim."""


class ChatReplyIntegrityError(RuntimeError):
    """Local accounting or budget integrity prevented reliable continuation."""


class DirectChatGateway(Protocol):
    def plan(self, request: LLMRequest, *, selection: ModelSelection | None = None): ...

    async def generate(
        self,
        request: LLMRequest,
        *,
        selection: ModelSelection | None = None,
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
        available: Callable[[], bool] | None = None,
        selection: ModelSelection | None = None,
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
        self._available = available or (lambda: True)
        self._selection = selection

    @property
    def available(self) -> bool:
        return self._available()

    async def reply(self, sent: PlayerSend) -> ChatMessage:
        if not isinstance(sent, PlayerSend):
            raise ValueError("chat_send_required")
        if not self.available:
            raise ChatReplyUnavailableError("chat_model_unavailable")
        context = await self._context.build(sent)
        request = LLMRequest(
            invocation_id=InvocationId(uuid4()),
            model=self._model,
            purpose=LLMPurpose("character_dialogue"),
            messages=context.messages,
            max_output_tokens=min(sent.token_ceiling, self._max_output_tokens),
        )
        try:
            plan = self._gateway.plan(request, selection=self._selection)
        except RoutingError:
            raise ChatReplyUnavailableError("chat_model_unavailable") from None
        bounds = tuple(
            self._token_bounder.bound(replace(request, model=model)) for model in plan.candidates
        )
        if not bounds or any(
            bound is None or bound.guarantee is not BoundGuarantee.HARD_UPPER_BOUND
            for bound in bounds
        ):
            raise ChatReplyBudgetError("turn_input_bound_unavailable")
        remaining_for_output = sent.token_ceiling - max(bound.input_tokens for bound in bounds)
        if remaining_for_output < 1:
            raise ChatReplyBudgetError("turn_token_limit_exceeded")
        if request.max_output_tokens > remaining_for_output:
            request = replace(request, max_output_tokens=remaining_for_output)
            bounds = tuple(
                self._token_bounder.bound(replace(request, model=model))
                for model in plan.candidates
            )
        if any(
            bound is None
            or bound.guarantee is not BoundGuarantee.HARD_UPPER_BOUND
            or bound.input_tokens + bound.output_tokens > sent.token_ceiling
            for bound in bounds
        ):
            raise ChatReplyBudgetError("turn_token_limit_exceeded")
        claim = await self._messages.claim_direct(sent.message.conversation_id, sent.turn_id)
        if claim.player_message != sent.message or claim.token_ceiling != sent.token_ceiling:
            raise ChatReplyValidationError("chat_send_changed")
        budget = ChatTurnTokenBudget(claim.token_ceiling)
        try:
            response = await self._gateway.generate(
                request, selection=self._selection, turn_budget=budget
            )
        except (BudgetAdmissionError, TurnTokenBudgetError):
            raise ChatReplyBudgetError("chat_admission_denied") from None
        except (BudgetIntegrityError, AccountingInfrastructureError):
            raise ChatReplyIntegrityError("chat_accounting_unavailable") from None
        except RoutingError:
            raise ChatReplyUnavailableError("chat_model_unavailable") from None
        except ExecutionDeadlineError:
            raise ChatReplyUnavailableError("chat_route_deadline_exhausted") from None
        except LLMError:
            raise ChatReplyGenerationError("chat_generation_failed") from None
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
