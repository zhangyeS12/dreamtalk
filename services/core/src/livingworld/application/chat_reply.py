"""One direct Character reply through the governed LLM and durable chat boundary."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import aclosing, asynccontextmanager
from dataclasses import dataclass, field, replace
from typing import Protocol
from uuid import uuid4

from anyio import CancelScope

from livingworld.application.chat_capacity import ContextCapacityError, fit_chat_context
from livingworld.application.chat_context import DirectChatContextBuilder
from livingworld.application.chat_event_annotations import (
    AnnotatedDialogue,
    CharacterEvolutionProposal,
    DialogueFormatError,
    annotate_request,
    annotation_request,
    completed_reply,
    decode_dialogue,
    decode_optional_dialogue,
    optional_annotation_request,
    partial_optional_reply,
    partial_reply,
)
from livingworld.application.chat_media import media_request
from livingworld.application.chat_messages import ChatMessage, ChatMessageService, PlayerSend
from livingworld.application.chat_speaker_labels import SpeakerReplyText
from livingworld.application.errors import EntityNotFoundError
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
    BudgetAdmissionError,
    BudgetIntegrityError,
    PreflightUsageBounder,
)
from livingworld.application.llm_chat_turn_budget import ChatTurnTokenBudget, TurnTokenBudgetError
from livingworld.application.llm_execution import ExecutionDeadlineError
from livingworld.application.llm_routing import ModelSelection, RoutePlan, RoutingError
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


@asynccontextmanager
async def claimed_reply_execution(messages, sent):
    """Only the caller which actually acquired the claim may mark its failure."""
    try:
        yield
    except BaseException as error:
        # A transport/accounting/cancellation result remains unknown. A complete
        # but locally rejected dialogue can authorize a user-created new attempt.
        with CancelScope(shield=True):
            try:
                await messages.fail_reply_execution(
                    sent, isinstance(error, ChatReplyValidationError)
                )
            except Exception:
                pass  # Remains running, and cannot authorize a retry in this process.
        raise


class ChatGateway(Protocol):
    def plan(
        self, request: LLMRequest, *, selection: ModelSelection | None = None
    ) -> RoutePlan: ...

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
    ) -> AsyncGenerator[LLMStreamEvent, None]: ...


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


PROVIDER_FAILURE_CODES = {
    LLMErrorCode.AUTHENTICATION: "chat_provider_authentication",
    LLMErrorCode.PERMISSION_DENIED: "chat_provider_permission_denied",
    LLMErrorCode.NOT_FOUND: "chat_provider_not_found",
    LLMErrorCode.RATE_LIMITED: "chat_provider_rate_limited",
    LLMErrorCode.QUOTA_EXHAUSTED: "chat_provider_quota_exhausted",
    LLMErrorCode.TIMEOUT: "chat_provider_timeout",
    LLMErrorCode.CONTEXT_LIMIT: "chat_provider_context_limit",
    LLMErrorCode.UNSUPPORTED_CAPABILITY: "chat_provider_unsupported",
}


def generation_failure_code(failure):
    code = str(failure)
    return code if code in PROVIDER_FAILURE_CODES.values() else "chat_generation_failed"


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
    code = PROVIDER_FAILURE_CODES.get(failure.code, "chat_generation_failed")
    return ChatReplyGenerationError(code)


def _reply_size(text: str) -> int:
    try:
        return len(text.encode("utf-8"))
    except UnicodeEncodeError:
        raise ChatReplyValidationError("chat_reply_format_invalid") from None


async def dialogue_text(
    gateway: ChatGateway,
    request: LLMRequest,
    budget: ChatTurnTokenBudget,
    selection: ModelSelection | None,
    progress: ChatProgressSink | None,
    speaker: CharacterId,
    *,
    format_failure: Callable[[str], None] | None = None,
) -> str | AnnotatedDialogue:
    """Reuse governed execution; stream deltas stay provisional until settlement."""
    visible = ""
    speaker_name = request.metadata.get("reply_speaker_name")
    speaker_text = (
        SpeakerReplyText(speaker_name, speaker)
        if isinstance(speaker_name, str) and speaker_name
        else None
    )
    try:
        if request.streaming:
            pieces: list[str] = []
            size = 0
            preview_diverged = False
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
                        size += _reply_size(event.text)
                        if size > 65536:
                            raise ChatReplyValidationError("chat_reply_invalid")
                        if event.text:
                            pieces.append(event.text)
                            if progress is not None:
                                if preview_diverged:
                                    continue
                                if annotation_request(request):
                                    decoded = (
                                        partial_optional_reply("".join(pieces))
                                        if optional_annotation_request(request)
                                        else partial_reply("".join(pieces))
                                    )
                                else:
                                    decoded = "".join(pieces)
                                if decoded is not None and speaker_text is not None:
                                    decoded = speaker_text.preview(decoded)
                                if decoded is None:
                                    continue
                                if not decoded.startswith(visible):
                                    if optional_annotation_request(request):
                                        # Stop provisional deltas; a validated terminal
                                        # message replaces the preview on the client.
                                        preview_diverged = True
                                        continue
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
    limit_reply = None
    if finish is FinishReason.OUTPUT_LIMIT:
        limit_reply = completed_reply(text) if optional_annotation_request(request) else None
        if limit_reply is None:
            raise ChatReplyValidationError("chat_reply_output_limit")
    if not text.strip():
        raise ChatReplyValidationError("chat_reply_empty")
    if (
        finish not in {FinishReason.STOP, FinishReason.REFUSAL}
        and limit_reply is None
        or not text.strip()
        or _reply_size(text) > 65536
    ):
        raise ChatReplyValidationError("chat_reply_invalid")
    if annotation_request(request):
        try:
            annotated = (
                AnnotatedDialogue(limit_reply)
                if limit_reply is not None
                else decode_optional_dialogue(text)
                if optional_annotation_request(request)
                else decode_dialogue(text)
            )
            if speaker_text is not None:
                body = speaker_text.complete(annotated.text)
                if not body.strip():
                    raise DialogueFormatError("empty_reply")
                annotated = replace(
                    annotated,
                    text=body,
                    events=tuple(item for item in annotated.events if item.quote in body),
                    memories=tuple(
                        item
                        for item in annotated.memories
                        if item.source != "reply" or item.quote in body
                    ),
                )
            if (
                request.streaming
                and progress is not None
                and visible
                and annotated.text != visible
                and not optional_annotation_request(request)
            ):
                raise ValueError()
        except ValueError as error:
            if format_failure is not None:
                format_failure(
                    error.reason if isinstance(error, DialogueFormatError) else "stream_mismatch"
                )
            raise ChatReplyValidationError("chat_reply_format_invalid") from None
        if request.streaming and progress is not None and not visible:
            # Ambiguous prose prefixes and fenced envelopes are withheld until
            # terminal validation, so metadata never becomes a displayed delta.
            await progress(ChatProgress("delta", speaker, annotated.text))
        return annotated
    if speaker_text is not None:
        text = speaker_text.complete(text)
        if not text.strip():
            raise ChatReplyValidationError("chat_reply_empty")
    return text


class ChatReplyConfiguration[ChatContext]:
    """Shared route configuration; each reply service owns its execution pipeline."""

    def __init__(
        self,
        messages: ChatMessageService,
        context: ChatContext,
        gateway: ChatGateway,
        token_bounder: PreflightUsageBounder,
        model: ModelRef,
        max_output_tokens: int,
        available: Callable[[], bool] | None = None,
        selection: ModelSelection | None = None,
        input_token_reservation: int | None = None,
        event_capture: bool = False,
        journal=None,
        logger=None,
        evolution_writer=None,
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
        self._media = getattr(messages, "media", None)
        self._logger = logger
        self._evolution_writer = evolution_writer

    async def _save_character_updates(self, world_id, root_import_id, player_id, updates) -> None:
        if self._evolution_writer is None or root_import_id is None:
            return
        for update in updates:
            if not isinstance(update, CharacterEvolutionProposal):
                continue
            scope = f"player:{player_id.value}" if update.scope == "player" else "global"
            try:
                await self._evolution_writer(
                    world_id,
                    root_import_id,
                    field=update.field,
                    scope=scope,
                    text=update.text,
                )
            except (EntityNotFoundError, ValueError):
                # A model proposal is auxiliary to the reply. Invalid or stale
                # proposals must never turn a valid dialogue into a failed turn.
                continue
            except Exception:
                # A storage outage is also auxiliary; the durable chat reply has
                # already completed and must remain successful.
                continue

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


class DirectChatReplyService(ChatReplyConfiguration[DirectChatContextBuilder]):
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
        if self._media is not None:
            media_context = await self._media.context(sent, context.character_id)
            if media_context["media_allowed"]:
                if not self._event_capture:
                    request = annotate_request(request)
            request = media_request(request, media_context, context.layout)
        request = dialogue_request(self._gateway, request, self._selection, progress)
        try:
            request, report = await fit_chat_context(
                request,
                context.layout,
                self._gateway,
                self._token_bounder,
                self._selection,
                sent.token_ceiling,
            )
        except RoutingError:
            raise ChatReplyUnavailableError("chat_model_unavailable") from None
        except ContextCapacityError as error:
            raise ChatReplyBudgetError(str(error)) from None
        if self._media is not None:
            self._media.packed_context_facts(request)
        claim = await self._messages.claim_direct(sent.message.conversation_id, sent.turn_id)
        async with claimed_reply_execution(self._messages, sent):
            if claim.player_message != sent.message or claim.token_ceiling != sent.token_ceiling:
                raise ChatReplyValidationError("chat_send_changed")
            await self._messages.save_context_report(sent, claim.character_id, report)
            budget = ChatTurnTokenBudget(claim.token_ceiling)
            if progress is not None:
                await progress(ChatProgress("replying", claim.character_id))
            text = await dialogue_text(
                self._gateway,
                request,
                budget,
                self._selection,
                progress,
                claim.character_id,
                format_failure=self._media.reply_format_failure
                if self._media is not None and request.metadata.get("chat_media_requested")
                else None,
            )
            media = (
                await self._media.resolve(sent, claim.character_id, text.media)
                if self._media is not None and isinstance(text, AnnotatedDialogue)
                else None
            )
            only_media = media is not None and media.only_media
            message = (
                await self._messages.complete_direct(
                    claim,
                    text.text,
                    events=() if only_media else text.events,
                    memories=() if only_media else text.memories,
                    media=media,
                )
                if isinstance(text, AnnotatedDialogue)
                else await self._messages.complete_direct(claim, text)
            )
            if isinstance(text, AnnotatedDialogue) and not only_media:
                await self._save_character_updates(
                    sent.message.conversation_id.world_id,
                    context.root_import_id,
                    claim.player_id,
                    text.character_updates,
                )
            if progress is not None:
                await progress(ChatProgress("message", message=message))
            return message
