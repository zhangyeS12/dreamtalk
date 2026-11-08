"""One claimed group turn: select speakers and generate under one token ceiling."""

from __future__ import annotations

import asyncio
import json
from contextvars import ContextVar
from dataclasses import dataclass, replace
from time import perf_counter
from uuid import UUID, uuid4

from livingworld.application.chat_capacity import ContextCapacityError, fit_chat_context
from livingworld.application.chat_diagnostics import (
    chat_phase,
    chat_result,
    chat_warning,
    diagnosed_reply,
)
from livingworld.application.chat_event_annotations import AnnotatedDialogue, annotate_request
from livingworld.application.chat_media import media_request
from livingworld.application.chat_messages import (
    ClaimedGroupTurn,
    GroupTurnView,
    PlayerSend,
)
from livingworld.application.chat_privacy import (
    clean_private_dialogue,
    reply_privacy,
    valid_reply_parts,
    visible_text,
)
from livingworld.application.chat_reply import (
    ChatProgress,
    ChatProgressSink,
    ChatReplyBudgetError,
    ChatReplyConfiguration,
    ChatReplyIntegrityError,
    ChatReplyUnavailableError,
    ChatReplyValidationError,
    _generation_error,
    claimed_reply_execution,
    dialogue_request,
    dialogue_text,
)
from livingworld.application.group_chat_context import GroupChatContextBuilder
from livingworld.application.llm import (
    FinishReason,
    InvocationId,
    LLMError,
    LLMPurpose,
    LLMRequest,
    LLMResponse,
)
from livingworld.application.llm_accounting import AccountingInfrastructureError
from livingworld.application.llm_budget import (
    BudgetAdmissionError,
    BudgetIntegrityError,
)
from livingworld.application.llm_chat_turn_budget import ChatTurnTokenBudget, TurnTokenBudgetError
from livingworld.application.llm_execution import ExecutionDeadlineError
from livingworld.application.llm_routing import RoutingError
from livingworld.domain.identifiers import CharacterId

_MAX_GROUP_REPLIES = 32
# Selection also needs room for a reasoning model's internal output. This is
# an upper cap, not a fixed charge; model limits and the shared turn still apply.
_SELECT_OUTPUT_TOKENS = 8192
_PURPOSE = LLMPurpose("character_dialogue")


@dataclass(slots=True)
class _GroupFacts:
    selection_calls: int = 0
    reply_calls: int = 0
    selection_ms: int = 0
    reply_ms: int = 0
    admission_blocks: int = 0
    budget: ChatTurnTokenBudget | None = None


_GROUP_FACTS: ContextVar[_GroupFacts | None] = ContextVar("group_reply_facts", default=None)


def _count_group_fact(name, amount=1):
    if (facts := _GROUP_FACTS.get()) is not None:
        setattr(facts, name, getattr(facts, name) + amount)


class GroupChatReplyService(ChatReplyConfiguration[GroupChatContextBuilder]):
    """Speaker scheduling stays separate from Director and WorldEvent commits."""

    def __init__(self, messages, context, *configuration, scheduler_configuration=None, **options):
        super().__init__(messages, context, *configuration, **options)
        self._scheduler = (
            ChatReplyConfiguration(messages, context, *scheduler_configuration)
            if scheduler_configuration is not None
            else self
        )

    @property
    def available(self):
        return super().available and (self._scheduler is self or self._scheduler.available)

    def _request(self, messages, output_tokens: int) -> LLMRequest:
        return LLMRequest(
            invocation_id=InvocationId(uuid4()),
            model=self._model,
            purpose=_PURPOSE,
            messages=messages,
            max_output_tokens=output_tokens,
        )

    async def _dialogue(self, context, source, speaker, output):
        request = self._request(context.messages, output)
        # Local decoding hint only; adapters do not add request metadata to messages.
        request = replace(
            request, metadata={"reply_speaker_name": context.speaker_name, "chat_kind": "group"}
        )
        if self._journal is not None:
            chat_phase("journal", request=request)
            request = replace(
                request,
                messages=request.messages + await self._journal.prompt_context(source, speaker),
            )
        if getattr(context, "private_context", False):
            return annotate_request(request, private=True)
        if self._event_capture:
            request = annotate_request(request)
        if self._media is not None:
            chat_phase("media_context", request=request)
            media_context = await self._media.context(source, speaker)
            if media_context["media_allowed"]:
                if not self._event_capture:
                    request = annotate_request(request)
            request = media_request(request, media_context, context.layout)
        return request

    async def _preflight(self, request, remaining, layout=None, *, scheduling=False):
        chat_phase("preflight", request=request)
        configured = self._scheduler if scheduling else self
        try:
            result = await fit_chat_context(
                request,
                layout,
                configured._gateway,
                configured._token_bounder,
                configured._selection,
                remaining,
            )
            if self._media is not None:
                self._media.packed_context_facts(result[0])
            return result
        except RoutingError:
            raise ChatReplyUnavailableError("chat_model_unavailable") from None
        except ContextCapacityError as error:
            _count_group_fact("admission_blocks")
            raise ChatReplyBudgetError(str(error)) from None

    async def _generate(self, request: LLMRequest, budget: ChatTurnTokenBudget) -> LLMResponse:
        chat_phase("selection_generate", request=request)
        _count_group_fact("selection_calls")
        started = perf_counter()
        try:
            response = await self._scheduler._gateway.generate(
                request, selection=self._scheduler._selection, turn_budget=budget
            )
        except (BudgetAdmissionError, TurnTokenBudgetError):
            _count_group_fact("admission_blocks")
            raise ChatReplyBudgetError("chat_admission_denied") from None
        except (BudgetIntegrityError, AccountingInfrastructureError):
            raise ChatReplyIntegrityError("chat_accounting_unavailable") from None
        except RoutingError:
            raise ChatReplyUnavailableError("chat_model_unavailable") from None
        except ExecutionDeadlineError:
            raise ChatReplyUnavailableError("chat_route_deadline_exhausted") from None
        except LLMError as failure:
            raise _generation_error(failure.failure) from None
        finally:
            _count_group_fact("selection_ms", int((perf_counter() - started) * 1000))
        chat_result(response.finish_reason)
        if budget.bound_violated:
            raise ChatReplyValidationError("chat_token_bound_violated")
        if response.invocation_id != request.invocation_id:
            raise ChatReplyValidationError("chat_reply_invalid", reason="invocation_mismatch")
        return response

    async def _selection_request(self, context, remaining: int) -> tuple[LLMRequest, dict]:
        return await self._preflight(
            replace(
                self._request(
                    context.messages, min(_SELECT_OUTPUT_TOKENS, self._scheduler._max_output_tokens)
                ),
                model=self._scheduler._model,
            ),
            remaining,
            context.layout,
            scheduling=True,
        )

    @staticmethod
    def _selection_result(
        response: LLMResponse, source: ClaimedGroupTurn, *, allow_stop: bool
    ) -> CharacterId | None:
        chat_phase("selection_decode")
        if response.finish_reason is FinishReason.OUTPUT_LIMIT:
            raise ChatReplyValidationError("group_selection_output_limit")
        if response.finish_reason is not FinishReason.STOP:
            raise ChatReplyValidationError(
                "group_selection_invalid", reason="selection_finish_invalid"
            )
        try:
            size = len(response.text.encode("utf-8"))
        except UnicodeEncodeError:
            raise ChatReplyValidationError(
                "group_selection_invalid", reason="selection_encoding_invalid"
            ) from None
        if size > 1024:
            raise ChatReplyValidationError("group_selection_invalid", reason="selection_oversized")
        choice = response.text.strip()
        if choice.startswith("```"):
            lines = choice.splitlines()
            if (
                len(lines) < 3
                or lines[0].casefold() not in {"```", "```text", "```json"}
                or lines[-1] != "```"
                or "```" in "\n".join(lines[1:-1])
            ):
                raise ChatReplyValidationError("group_selection_invalid")
            choice = "\n".join(lines[1:-1]).strip()
        try:
            # Normalize only whole scalar/object wrappers. Never extract an ID
            # from prose or accept multiple choices, partial output or strangers.
            if choice.startswith(('"', "{")):
                decoded = json.loads(choice, object_pairs_hook=lambda pairs: pairs)
                if isinstance(decoded, list):
                    if len(decoded) != 1 or decoded[0][0] != "character_id":
                        raise ValueError("selection_shape_invalid")
                    decoded = decoded[0][1]
                if not isinstance(decoded, str):
                    raise ValueError("selection_shape_invalid")
                choice = decoded.strip()
            if choice == "STOP":
                if allow_stop:
                    return None
                raise ValueError("first_selection_requires_speaker")
            identity = CharacterId(source.turn_id.world_id, UUID(choice))
        except ValueError as error:
            raise ChatReplyValidationError(
                "group_selection_invalid",
                reason="first_selection_requires_speaker"
                if str(error) == "first_selection_requires_speaker"
                else "selection_shape_invalid",
            ) from None
        if identity not in source.character_ids:
            raise ChatReplyValidationError("group_selection_invalid", reason="selection_not_member")
        return identity

    async def _select(
        self, source: ClaimedGroupTurn, budget: ChatTurnTokenBudget
    ) -> CharacterId | None:
        chat_phase("selection_context")
        if source.player_message.privacy:
            turn = await self._messages.group_turn(source.conversation_id, source.turn_id)
            replied = {str(reply.sender_id.value) for reply in turn.replies}
            targets = dict.fromkeys(span["character_id"] for span in source.player_message.privacy)
            for target in targets:
                if target not in replied:
                    return next(
                        person for person in source.character_ids if str(person.value) == target
                    )
            if not any(
                visible_text(message.text, message.privacy).strip()
                for message in (source.player_message, *turn.replies)
            ):
                return None
        chat_phase("selection_context")
        context = await self._context.build_selection(source)
        request, _report = await self._selection_request(context, budget.remaining)
        response = await self._generate(request, budget)
        return self._selection_result(response, source, allow_stop=True)

    async def _reply(
        self,
        source: PlayerSend | ClaimedGroupTurn,
        speaker: CharacterId,
        budget: ChatTurnTokenBudget,
        *,
        prepared: tuple[LLMRequest, dict] | None = None,
        progress: ChatProgressSink | None = None,
    ) -> str | AnnotatedDialogue:
        if budget.closed or budget.remaining < 1:
            raise ChatReplyBudgetError("turn_token_limit_exceeded")
        if prepared is None:
            context = await self._context.build_reply(source, speaker)
            reply_request, report = await self._preflight(
                dialogue_request(
                    self._gateway,
                    await self._dialogue(
                        context, source, speaker, min(self._max_output_tokens, budget.remaining)
                    ),
                    self._selection,
                    progress,
                ),
                budget.remaining,
                context.layout,
            )
        else:
            reply_request, report = prepared
        chat_phase("context_report", request=reply_request)
        await self._messages.save_context_report(source, speaker, report)
        if progress is not None:
            await progress(ChatProgress("replying", speaker))
        _count_group_fact("reply_calls")
        started = perf_counter()
        try:
            text = await dialogue_text(
                self._gateway,
                reply_request,
                budget,
                self._selection,
                None if reply_request.metadata.get("chat_privacy") else progress,
                speaker,
                format_failure=self._media.reply_format_failure
                if self._media is not None and reply_request.metadata.get("chat_media_requested")
                else None,
            )
            if reply_request.metadata.get("chat_privacy") or (
                isinstance(text, AnnotatedDialogue) and text.private_context
            ):
                chat_phase("privacy")
                text = text if isinstance(text, AnnotatedDialogue) else AnnotatedDialogue(text)
                if not valid_reply_parts(text.privacy_parts, text.text):
                    chat_warning(
                        "chat_private_classification_fallback",
                        reason="classification_missing_or_invalid",
                    )
                if text.events or text.character_updates or text.media is not None:
                    chat_warning("chat_annotation_discarded", reason="private_auxiliary_ignored")
                text = clean_private_dialogue(text, speaker)
                if not text.text.strip():
                    raise ChatReplyValidationError("chat_reply_empty")
                return text
            return text
        except ChatReplyBudgetError:
            _count_group_fact("admission_blocks")
            raise
        finally:
            _count_group_fact("reply_ms", int((perf_counter() - started) * 1000))

    async def _save_completed_character_updates(self, claim, speaker, updates):
        try:
            participants = await self._context._conversations.current_group_characters(
                claim.conversation_id
            )
            root_import_id = next(
                participant.root_import_id
                for participant, _ in participants
                if participant.character_id == speaker
            )
        except Exception as error:
            # Auxiliary metadata must not fail an already durable reply.
            chat_warning("chat_auxiliary_failed", error=error, stage="character_updates")
            return
        await self._save_character_updates(
            claim.conversation_id.world_id, root_import_id, claim.player_id, updates
        )

    @diagnosed_reply("group")
    async def reply(
        self, sent: PlayerSend, *, progress: ChatProgressSink | None = None
    ) -> GroupTurnView:
        chat_phase("availability")
        facts = _GroupFacts()
        token = _GROUP_FACTS.set(facts)
        started, outcome = perf_counter(), "failed"
        try:
            result = await self._reply_turn(sent, progress=progress)
            outcome = "completed"
            return result
        except asyncio.CancelledError:
            outcome = "cancelled"
            raise
        finally:
            _GROUP_FACTS.reset(token)
            if self._logger is not None:
                try:
                    self._logger.emit_group_reply_facts(
                        outcome=outcome,
                        elapsed_ms=int((perf_counter() - started) * 1000),
                        selection_calls=facts.selection_calls,
                        reply_calls=facts.reply_calls,
                        selection_ms=facts.selection_ms,
                        reply_ms=facts.reply_ms,
                        admission_blocks=facts.admission_blocks,
                        reserved_attempts=facts.budget.reserved_attempts if facts.budget else 0,
                    )
                except (OSError, ValueError):
                    pass

    async def _reply_turn(
        self, sent: PlayerSend, *, progress: ChatProgressSink | None = None
    ) -> GroupTurnView:
        if not isinstance(sent, PlayerSend):
            raise ValueError("chat_send_required")
        if not self.available:
            raise ChatReplyUnavailableError("chat_model_unavailable")
        budget = ChatTurnTokenBudget(sent.token_ceiling)
        if (facts := _GROUP_FACTS.get()) is not None:
            facts.budget = budget
        chat_phase("context")
        try:
            mentioned = await self._context.mentioned_character(sent)
        except ValueError:
            raise ChatReplyValidationError("group_mention_ambiguous") from None
        first_request: tuple[LLMRequest, dict] | None = None
        first_selection: LLMRequest | None = None
        if mentioned is not None:
            chat_phase("context")
            context = await self._context.build_reply(sent, mentioned)
            first_request = await self._preflight(
                dialogue_request(
                    self._gateway,
                    await self._dialogue(
                        context, sent, mentioned, min(self._max_output_tokens, budget.remaining)
                    ),
                    self._selection,
                    progress,
                ),
                budget.remaining,
                context.layout,
            )
        else:
            # A route/usage-bound failure must not consume the one-time claim.
            chat_phase("selection_context")
            selection = await self._context.build_selection(sent)
            first_selection, _report = await self._selection_request(selection, budget.remaining)
        chat_phase("claim")
        claim = await self._messages.claim_group(sent.message.conversation_id, sent.turn_id)
        async with claimed_reply_execution(self._messages, sent):
            if claim.player_message != sent.message or claim.token_ceiling != sent.token_ceiling:
                raise ChatReplyValidationError("chat_send_changed")
            if mentioned is None:
                assert first_selection is not None
                if progress is not None:
                    await progress(ChatProgress("selecting"))
                choice = await self._generate(first_selection, budget)
                speaker = self._selection_result(choice, claim, allow_stop=False)
                assert speaker is not None
                if budget.closed or budget.remaining < 1:
                    raise ChatReplyBudgetError("turn_token_limit_exceeded")
                first_request = None
            else:
                speaker = mentioned
                if speaker not in claim.character_ids:
                    raise ChatReplyValidationError("group_selection_invalid")
            for ordinal in range(_MAX_GROUP_REPLIES):
                chat_phase("context", ordinal=ordinal)
                try:
                    text = await self._reply(
                        claim,
                        speaker,
                        budget,
                        prepared=first_request if ordinal == 0 else None,
                        progress=progress,
                    )
                except ChatReplyBudgetError as error:
                    if ordinal:
                        chat_warning("chat_admission_denied", error=error)
                        return await self._finish_group(claim)
                    raise
                private_context = isinstance(text, AnnotatedDialogue) and text.private_context
                privacy = reply_privacy(text, speaker) if private_context else ()
                chat_phase("media")
                media = (
                    await self._media.resolve(claim, speaker, text.media)
                    if self._media is not None and isinstance(text, AnnotatedDialogue)
                    else None
                )
                only_media = media is not None and media.only_media
                chat_phase("persist_reply")
                message = (
                    await self._messages.complete_group_reply(
                        claim,
                        speaker,
                        ordinal,
                        text.text,
                        events=() if only_media else text.events,
                        memories=() if only_media else text.memories,
                        media=media,
                        **(
                            {
                                "privacy": privacy,
                                "private_context": True,
                                "privacy_fallback": text.privacy_fallback,
                            }
                            if private_context
                            else {}
                        ),
                    )
                    if isinstance(text, AnnotatedDialogue)
                    else await self._messages.complete_group_reply(claim, speaker, ordinal, text)
                )
                if (
                    isinstance(text, AnnotatedDialogue)
                    and not only_media
                    and text.character_updates
                ):
                    await self._save_completed_character_updates(
                        claim, speaker, text.character_updates
                    )
                if progress is not None:
                    chat_phase("deliver")
                    await progress(ChatProgress("message", message=message))
                if budget.closed or budget.remaining < 1 or ordinal + 1 == _MAX_GROUP_REPLIES:
                    chat_phase("finish")
                    return await self._finish_group(claim)
                try:
                    if progress is not None:
                        await progress(ChatProgress("selecting"))
                    next_speaker = await self._select(claim, budget)
                except ChatReplyBudgetError as error:
                    chat_warning("chat_admission_denied", error=error)
                    return await self._finish_group(claim)
                if next_speaker is None:
                    return await self._finish_group(claim)
                speaker = next_speaker
            raise AssertionError("group_reply_loop_unreachable")

    async def _finish_group(self, claim):
        chat_phase("finish")
        return await self._messages.finish_group(claim)
