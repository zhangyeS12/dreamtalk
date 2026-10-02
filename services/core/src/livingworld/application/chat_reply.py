"""One direct Character reply through the governed LLM and durable chat boundary."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import aclosing
from dataclasses import dataclass, field, replace
from typing import Protocol
from uuid import uuid4

from livingworld.application.chat_context import DirectChatContextBuilder
from livingworld.application.chat_event_annotations import (
    AnnotatedDialogue,
    annotate_request,
    annotation_request,
    decode_dialogue,
    partial_reply,
)
from livingworld.application.chat_messages import ChatMessage, ChatMessageService, PlayerSend
from livingworld.application.llm import (
    FinishReason,
    InvocationId,
    LLMContractError,
    LLMError,
    LLMErrorCode,
    LLMPurpose,
    LLMRequest,
    LLMResponse,
    LLMStreamEvent,
    ModelRef,
    StreamCompleted,
    StreamFailed,
    StructuredFailureReason,
    TextDelta,
)
from livingworld.application.llm_accounting import AccountingInfrastructureError
from livingworld.application.llm_budget import (
    BoundGuarantee,
    BudgetAdmissionError,
    BudgetIntegrityError,
    PreflightUsageBounder,
    prepare_usage_bound,
)
from livingworld.application.llm_chat_turn_budget import ChatTurnTokenBudget, TurnTokenBudgetError
from livingworld.application.llm_execution import ExecutionDeadlineError
from livingworld.application.llm_routing import ModelSelection, RoutingError
from livingworld.domain.identifiers import CharacterId


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


class ChatGateway(Protocol):
    def plan(self, request: LLMRequest, *, selection: ModelSelection | None = None): ...

    async def generate(
        self,
        request: LLMRequest,
        *,
        selection: ModelSelection | None = None,
        turn_budget: ChatTurnTokenBudget,
    ) -> LLMResponse: ...

    def stream(
        self,
        request: LLMRequest,
        *,
        selection: ModelSelection | None = None,
        turn_budget: ChatTurnTokenBudget,
    ) -> AsyncIterator[LLMStreamEvent]: ...


@dataclass(frozen=True, slots=True)
class ChatProgress:
    """Ephemeral player-facing progress; never a message or knowledge exposure."""

    kind: str
    speaker: CharacterId | None = None
    text: str = field(default="", repr=False)
    message: ChatMessage | None = field(default=None, repr=False)


type ChatProgressSink = Callable[[ChatProgress], Awaitable[None]]


def dialogue_request(gateway, request, selection, progress) -> LLMRequest:
    """Choose transport before dispatch; never replay a failed stream as generate."""
    if progress is None:
        return request
    streamed = replace(request, streaming=True)
    try:
        gateway.plan(streamed, selection=selection)
    except RoutingError:
        return request
    return streamed


def _generation_error(failure):
    if failure.code is LLMErrorCode.STRUCTURED_OUTPUT_FAILED:
        reason = failure.structured_detail.reason if failure.structured_detail else None
        code = (
            "chat_reply_output_limit"
            if reason is StructuredFailureReason.OUTPUT_TRUNCATED
            else "chat_reply_empty"
            if reason is StructuredFailureReason.EMPTY_OUTPUT
            else "chat_reply_format_invalid"
        )
        return ChatReplyValidationError(code)
    return ChatReplyGenerationError("chat_generation_failed")


async def dialogue_text(
    gateway: ChatGateway,
    request: LLMRequest,
    budget: ChatTurnTokenBudget,
    selection: ModelSelection | None,
    progress: ChatProgressSink | None,
    speaker: CharacterId,
) -> str | AnnotatedDialogue:
    """Reuse governed execution; stream deltas stay provisional until settlement."""
    try:
        if request.streaming:
            pieces: list[str] = []
            size = 0
            visible = ""
            completion = None
            async with aclosing(
                gateway.stream(request, selection=selection, turn_budget=budget)
            ) as events:
                async for event in events:
                    identity = (
                        event.completion.invocation_id
                        if isinstance(event, StreamCompleted)
                        else event.failure.invocation_id
                        if isinstance(event, StreamFailed)
                        else event.invocation_id
                    )
                    if identity != request.invocation_id:
                        raise ChatReplyValidationError("chat_reply_invalid")
                    if isinstance(event, StreamFailed):
                        raise _generation_error(event.failure)
                    if isinstance(event, TextDelta):
                        size += len(event.text.encode("utf-8"))
                        if size > 65536:
                            raise ChatReplyValidationError("chat_reply_invalid")
                        if event.text:
                            pieces.append(event.text)
                            if progress is not None:
                                delta = event.text
                                if annotation_request(request):
                                    decoded = partial_reply("".join(pieces))
                                    if decoded is None:
                                        continue
                                    if not decoded.startswith(visible):
                                        raise ChatReplyValidationError("chat_reply_invalid")
                                    delta, visible = decoded[len(visible) :], decoded
                                if delta:
                                    await progress(ChatProgress("delta", speaker, delta))
                    elif isinstance(event, StreamCompleted):
                        # Governed streaming settles usage before yielding completion.
                        completion = event.completion
                        break
            if completion is None:
                raise ChatReplyValidationError("chat_reply_invalid")
            text, finish = "".join(pieces), completion.finish_reason
        else:
            response = await gateway.generate(request, selection=selection, turn_budget=budget)
            if response.invocation_id != request.invocation_id:
                raise ChatReplyValidationError("chat_reply_invalid")
            text, finish = response.text, response.finish_reason
    except (BudgetAdmissionError, TurnTokenBudgetError):
        raise ChatReplyBudgetError("chat_admission_denied") from None
    except (BudgetIntegrityError, AccountingInfrastructureError):
        raise ChatReplyIntegrityError("chat_accounting_unavailable") from None
    except RoutingError:
        raise ChatReplyUnavailableError("chat_model_unavailable") from None
    except ExecutionDeadlineError:
        raise ChatReplyUnavailableError("chat_route_deadline_exhausted") from None
    except LLMError as error:
        raise _generation_error(error.failure) from None
    except LLMContractError:
        raise ChatReplyValidationError("chat_reply_invalid") from None
    if budget.bound_violated:
        raise ChatReplyValidationError("chat_token_bound_violated")
    if finish is FinishReason.OUTPUT_LIMIT:
        raise ChatReplyValidationError("chat_reply_output_limit")
    if not text.strip():
        raise ChatReplyValidationError("chat_reply_empty")
    if (
        finish not in {FinishReason.STOP, FinishReason.REFUSAL}
        or not text.strip()
        or len(text.encode("utf-8")) > 65536
    ):
        raise ChatReplyValidationError("chat_reply_invalid")
    if annotation_request(request):
        try:
            annotated = decode_dialogue(text)
            if request.streaming and progress is not None and annotated.text != visible:
                raise ValueError()
            return annotated
        except ValueError:
            raise ChatReplyValidationError("chat_reply_format_invalid") from None
    return text


class DirectChatReplyService:
    def __init__(
        self,
        messages: ChatMessageService,
        context: DirectChatContextBuilder,
        gateway: ChatGateway,
        token_bounder: PreflightUsageBounder,
        model: ModelRef,
        max_output_tokens: int,
        available: Callable[[], bool] | None = None,
        selection: ModelSelection | None = None,
        input_token_reservation: int | None = None,
        event_capture: bool = False,
        journal=None,
    ) -> None:
        if (
            not isinstance(model, ModelRef)
            or type(max_output_tokens) is not int
            or max_output_tokens < 1
            or not callable(getattr(token_bounder, "bound", None))
            or input_token_reservation is not None
            and (type(input_token_reservation) is not int or input_token_reservation < 1)
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
        self._input_token_reservation = input_token_reservation
        self._event_capture, self._journal = event_capture, journal

    @property
    def input_token_reservation(self) -> int | None:
        """Configured route-wide reservation for UI guidance, never admission authority."""
        return self._input_token_reservation

    @property
    def max_output_tokens(self) -> int:
        return self._max_output_tokens

    @property
    def available(self) -> bool:
        return self._available()

    async def reply(
        self, sent: PlayerSend, *, progress: ChatProgressSink | None = None
    ) -> ChatMessage:
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
        if self._journal is not None:
            request = replace(
                request,
                messages=request.messages
                + await self._journal.prompt_context(sent, context.character_id),
            )
        if self._event_capture:
            request = annotate_request(request)
        request = dialogue_request(self._gateway, request, self._selection, progress)
        try:
            plan = self._gateway.plan(request, selection=self._selection)
        except RoutingError:
            raise ChatReplyUnavailableError("chat_model_unavailable") from None
        bounds = [
            await prepare_usage_bound(self._token_bounder, replace(request, model=model))
            for model in plan.candidates
        ]
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
            bounds = [
                await prepare_usage_bound(self._token_bounder, replace(request, model=model))
                for model in plan.candidates
            ]
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
        if progress is not None:
            await progress(ChatProgress("replying", claim.character_id))
        text = await dialogue_text(
            self._gateway, request, budget, self._selection, progress, claim.character_id
        )
        message = (
            await self._messages.complete_direct(claim, text.text, events=text.events)
            if isinstance(text, AnnotatedDialogue)
            else await self._messages.complete_direct(claim, text)
        )
        if progress is not None:
            await progress(ChatProgress("message", message=message))
        return message
