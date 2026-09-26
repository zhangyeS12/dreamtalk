"""One claimed group turn: select speakers and generate under one token ceiling."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from uuid import UUID, uuid4

from livingworld.application.chat_messages import (
    ChatMessageService,
    ClaimedGroupTurn,
    GroupTurnView,
    PlayerSend,
)
from livingworld.application.chat_reply import (
    ChatGateway,
    ChatReplyBudgetError,
    ChatReplyGenerationError,
    ChatReplyIntegrityError,
    ChatReplyUnavailableError,
    ChatReplyValidationError,
)
from livingworld.application.group_chat_context import GroupChatContextBuilder
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
from livingworld.domain.identifiers import CharacterId

_MAX_GROUP_REPLIES = 32
_SELECT_OUTPUT_TOKENS = 64
_PURPOSE = LLMPurpose("character_dialogue")


class GroupChatReplyService:
    """Speaker scheduling stays separate from Director and WorldEvent commits."""

    def __init__(
        self,
        messages: ChatMessageService,
        context: GroupChatContextBuilder,
        gateway: ChatGateway,
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

    def _request(self, messages, output_tokens: int) -> LLMRequest:
        return LLMRequest(
            invocation_id=InvocationId(uuid4()),
            model=self._model,
            purpose=_PURPOSE,
            messages=messages,
            max_output_tokens=output_tokens,
        )

    def _preflight(self, request: LLMRequest, remaining: int) -> LLMRequest:
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
        output_room = remaining - max(bound.input_tokens for bound in bounds)
        if output_room < 1:
            raise ChatReplyBudgetError("turn_token_limit_exceeded")
        if request.max_output_tokens > output_room:
            request = replace(request, max_output_tokens=output_room)
            bounds = tuple(
                self._token_bounder.bound(replace(request, model=model))
                for model in plan.candidates
            )
        if any(
            bound is None
            or bound.guarantee is not BoundGuarantee.HARD_UPPER_BOUND
            or bound.input_tokens + bound.output_tokens > remaining
            for bound in bounds
        ):
            raise ChatReplyBudgetError("turn_token_limit_exceeded")
        return request

    async def _generate(self, request: LLMRequest, budget: ChatTurnTokenBudget) -> LLMResponse:
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
        if response.invocation_id != request.invocation_id:
            raise ChatReplyValidationError("chat_reply_invalid")
        return response

    async def _select(
        self, source: PlayerSend | ClaimedGroupTurn, budget: ChatTurnTokenBudget
    ) -> CharacterId | None:
        context = await self._context.build_selection(source)
        request = self._preflight(
            self._request(context.messages, _SELECT_OUTPUT_TOKENS), budget.remaining
        )
        response = await self._generate(request, budget)
        if response.finish_reason is not FinishReason.STOP:
            raise ChatReplyValidationError("group_selection_invalid")
        choice = response.text.strip()
        if choice == "STOP":
            return None
        try:
            identity = CharacterId(source.turn_id.world_id, UUID(choice))
        except ValueError:
            raise ChatReplyValidationError("group_selection_invalid") from None
        if isinstance(source, ClaimedGroupTurn) and identity not in source.character_ids:
            raise ChatReplyValidationError("group_selection_invalid")
        return identity

    async def _reply(
        self,
        source: PlayerSend | ClaimedGroupTurn,
        speaker: CharacterId,
        budget: ChatTurnTokenBudget,
        *,
        prepared: LLMRequest | None = None,
    ) -> str:
        if budget.closed or budget.remaining < 1:
            raise ChatReplyBudgetError("turn_token_limit_exceeded")
        if prepared is None:
            context = await self._context.build_reply(source, speaker)
            prepared = self._preflight(
                self._request(context.messages, min(self._max_output_tokens, budget.remaining)),
                budget.remaining,
            )
        response = await self._generate(prepared, budget)
        if (
            response.finish_reason not in {FinishReason.STOP, FinishReason.REFUSAL}
            or not response.text.strip()
            or len(response.text.encode("utf-8")) > 65536
        ):
            raise ChatReplyValidationError("chat_reply_invalid")
        return response.text

    async def reply(self, sent: PlayerSend) -> GroupTurnView:
        if not isinstance(sent, PlayerSend):
            raise ValueError("chat_send_required")
        if not self.available:
            raise ChatReplyUnavailableError("chat_model_unavailable")
        budget = ChatTurnTokenBudget(sent.token_ceiling)
        try:
            mentioned = await self._context.mentioned_character(sent)
        except ValueError:
            raise ChatReplyValidationError("group_mention_ambiguous") from None
        first_request = None
        if mentioned is not None:
            context = await self._context.build_reply(sent, mentioned)
            first_request = self._preflight(
                self._request(context.messages, min(self._max_output_tokens, budget.remaining)),
                budget.remaining,
            )
        else:
            # A route/usage-bound failure must not consume the one-time claim.
            selection = await self._context.build_selection(sent)
            first_request = self._preflight(
                self._request(selection.messages, _SELECT_OUTPUT_TOKENS), budget.remaining
            )
        claim = await self._messages.claim_group(sent.message.conversation_id, sent.turn_id)
        if claim.player_message != sent.message or claim.token_ceiling != sent.token_ceiling:
            raise ChatReplyValidationError("chat_send_changed")
        if mentioned is None:
            assert first_request is not None
            choice = await self._generate(first_request, budget)
            if choice.finish_reason is not FinishReason.STOP:
                raise ChatReplyValidationError("group_selection_invalid")
            try:
                speaker = CharacterId(claim.turn_id.world_id, UUID(choice.text.strip()))
            except ValueError:
                raise ChatReplyValidationError("group_selection_invalid") from None
            if speaker not in claim.character_ids:
                raise ChatReplyValidationError("group_selection_invalid")
            if budget.closed or budget.remaining < 1:
                raise ChatReplyBudgetError("turn_token_limit_exceeded")
            first_request = None
        else:
            speaker = mentioned
            if speaker not in claim.character_ids:
                raise ChatReplyValidationError("group_selection_invalid")
        for ordinal in range(_MAX_GROUP_REPLIES):
            try:
                text = await self._reply(
                    claim, speaker, budget, prepared=first_request if ordinal == 0 else None
                )
            except ChatReplyBudgetError:
                if ordinal:
                    return await self._messages.finish_group(claim)
                raise
            await self._messages.complete_group_reply(claim, speaker, ordinal, text)
            if budget.closed or budget.remaining < 1 or ordinal + 1 == _MAX_GROUP_REPLIES:
                return await self._messages.finish_group(claim)
            try:
                next_speaker = await self._select(claim, budget)
            except ChatReplyBudgetError:
                return await self._messages.finish_group(claim)
            if next_speaker is None:
                return await self._messages.finish_group(claim)
            speaker = next_speaker
        raise AssertionError("group_reply_loop_unreachable")
