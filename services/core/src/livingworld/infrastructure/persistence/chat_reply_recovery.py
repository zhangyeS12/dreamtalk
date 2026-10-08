"""Explicit, idempotent generation attempts. Source text stays in its original message."""

import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select, update

from livingworld.application.errors import (
    ChatTurnUnavailableError,
    EntityNotFoundError,
    IdempotencyConflictError,
)
from livingworld.infrastructure.persistence.models import (
    ChatMessageRecord as Message,
)
from livingworld.infrastructure.persistence.models import (
    ChatReplyExecutionRecord as Execution,
)
from livingworld.infrastructure.persistence.models import (
    ChatReplyRecoveryRecord as Recovery,
)
from livingworld.infrastructure.persistence.models import (
    ChatTurnDispatchRecord as Dispatch,
)
from livingworld.infrastructure.persistence.models import (
    ChatTurnRecord as Turn,
)
from livingworld.infrastructure.persistence.models import (
    LocalPlayerBindingRecord,
)


class ChatReplyRecoveryMixin:
    async def _source_message(self, session, conversation, turn, player):
        recovery = await session.get(Recovery, (turn.world_id, turn.turn_id))
        if (turn.kind == "retry") != (recovery is not None):
            raise EntityNotFoundError("chat_state_invalid")
        source_id = recovery.source_turn_id if recovery else turn.turn_id
        if recovery:
            source = await session.get(Turn, (turn.world_id, source_id))
            if (
                source is None
                or source.kind != "player"
                or source.conversation_id != conversation.value
            ):
                raise EntityNotFoundError("chat_state_invalid")
        message = await session.scalar(
            select(Message).where(
                Message.world_id == turn.world_id,
                Message.turn_id == source_id,
                Message.conversation_id == conversation.value,
                Message.sender_player_id == player.value,
            )
        )
        if message is None:
            raise EntityNotFoundError("chat_state_invalid")
        return message

    async def _latest_attempt(self, session, world, source):
        return await session.scalar(
            select(Recovery)
            .where(
                Recovery.world_id == world,
                Recovery.source_turn_id == source,
            )
            .order_by(Recovery.ordinal.desc())
            .limit(1)
        )

    async def _active_attempt(self, session, conversation, turn, completing=False):
        recovery = await session.get(Recovery, (turn.world_id, turn.turn_id))
        source = recovery.source_turn_id if recovery else turn.turn_id
        latest = await self._latest_attempt(session, turn.world_id, source)
        if latest is not None and latest.turn_id != turn.turn_id:
            raise ChatTurnUnavailableError("chat_attempt_superseded")
        if completing:
            execution = await session.get(Execution, (turn.world_id, turn.turn_id))
            if execution is not None and execution.state not in {"running", "completed"}:
                raise ChatTurnUnavailableError("chat_turn_claim_invalid")
        elif recovery:
            last = await session.scalar(
                select(func.max(Message.position)).where(
                    Message.world_id == turn.world_id,
                    Message.conversation_id == conversation.value,
                )
            )
            source_message = await session.scalar(
                select(Message).where(
                    Message.world_id == turn.world_id,
                    Message.turn_id == source,
                    Message.sender_player_id.is_not(None),
                )
            )
            if source_message is None or last != source_message.position:
                raise ChatTurnUnavailableError("chat_recovery_not_latest")

    async def _recovery_view(self, session, conversation, source_id, player):
        await self._conversation(session, conversation, player)
        binding = await session.get(LocalPlayerBindingRecord, conversation.world_id.value)
        if binding is None or binding.player_id != player.value:
            raise EntityNotFoundError("selected_player_required")
        source = await session.get(Turn, (conversation.world_id.value, source_id.value))
        if (
            source is None
            or source.kind != "player"
            or source.conversation_id != conversation.value
        ):
            raise EntityNotFoundError("chat_turn_not_found")
        message = await self._source_message(session, conversation, source, player)
        latest = await self._latest_attempt(session, source.world_id, source.turn_id)
        current_id = latest.turn_id if latest else source.turn_id
        current = await session.get(Turn, (source.world_id, current_id))
        execution = await session.get(Execution, (source.world_id, current_id))
        dispatch = await session.get(Dispatch, (source.world_id, current_id))
        last_position = await session.scalar(
            select(func.max(Message.position)).where(
                Message.world_id == source.world_id,
                Message.conversation_id == conversation.value,
            )
        )
        has_reply = await session.scalar(
            select(Message.message_id)
            .where(
                Message.world_id == source.world_id,
                Message.conversation_id == conversation.value,
                Message.position > message.position,
                Message.sender_character_id.is_not(None),
            )
            .limit(1)
        )
        state = execution.state if execution else "unknown" if dispatch else "pending"
        if has_reply is not None:
            state = "completed" if execution and execution.state == "completed" else "has_replies"
        reason = "chat_recovery_not_latest" if last_position != message.position else ""
        if has_reply is not None:
            reason = "chat_recovery_has_replies"
        elif state in {"running", "unknown"}:
            reason = "chat_recovery_unknown" if state == "unknown" else "chat_recovery_running"
        elif state == "completed":
            reason = "chat_recovery_has_replies"
        return {
            "source_turn_id": str(source.turn_id),
            "attempt_turn_id": str(current_id),
            "state": state,
            "token_ceiling": current.token_ceiling,
            "can_generate": not reason and state == "pending",
            "can_create": not reason and state in {"failed", "interrupted"},
            "reason": reason or None,
        }

    async def reply_recovery(self, conversation, source, player):
        if conversation.world_id != source.world_id:
            raise EntityNotFoundError("chat_world_mismatch")
        async with self._sessions() as session:
            return await self._recovery_view(session, conversation, source, player)

    async def create_reply_recovery(self, request, conversation, source, player, expected, ceiling):
        if conversation.world_id != source.world_id:
            raise EntityNotFoundError("chat_world_mismatch")
        fingerprint = hashlib.sha256(
            json.dumps(
                [
                    "reply_recovery",
                    str(conversation.world_id.value),
                    str(conversation.value),
                    str(player.value),
                    str(source.value),
                    str(expected),
                    ceiling,
                ],
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        async with self._sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            await self._conversation(session, conversation, player)
            binding = await session.get(LocalPlayerBindingRecord, conversation.world_id.value)
            if binding is None or binding.player_id != player.value:
                raise EntityNotFoundError("selected_player_required")
            existing = await session.scalar(select(Turn).where(Turn.request_id == request.value))
            if existing is not None:
                if existing.fingerprint != fingerprint or existing.kind != "retry":
                    raise IdempotencyConflictError("chat_request_conflict")
                # Repeating a receipt never creates or dispatches another attempt.
                return {"turn_id": str(existing.turn_id), "token_ceiling": existing.token_ceiling}
            from livingworld.infrastructure.persistence.authored_lifecycle import (
                require_active_conversation,
            )

            await require_active_conversation(
                session, conversation.world_id.value, conversation.value
            )
            view = await self._recovery_view(session, conversation, source, player)
            if view["attempt_turn_id"] != str(expected):
                raise ChatTurnUnavailableError("chat_recovery_changed")
            if not view["can_create"]:
                raise ChatTurnUnavailableError(view["reason"] or "chat_recovery_unavailable")
            latest = await self._latest_attempt(session, conversation.world_id.value, source.value)
            identity = uuid4()
            session.add(
                Turn(
                    world_id=conversation.world_id.value,
                    turn_id=identity,
                    conversation_id=conversation.value,
                    request_id=request.value,
                    fingerprint=fingerprint,
                    token_ceiling=ceiling,
                    status="pending",
                    kind="retry",
                    created_at_utc=datetime.now(UTC),
                )
            )
            await session.flush()
            session.add(
                Recovery(
                    world_id=conversation.world_id.value,
                    turn_id=identity,
                    source_turn_id=source.value,
                    ordinal=latest.ordinal + 1 if latest else 1,
                )
            )
            await session.flush()
            return {"turn_id": str(identity), "token_ceiling": ceiling}

    async def fail_reply_execution(self, sent, known_failure):
        async with self._sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            row = await session.get(Execution, (sent.turn_id.world_id.value, sent.turn_id.value))
            if row is not None and row.state == "running":
                row.state = "failed" if known_failure else "unknown"

    async def recover_reply_executions(self):
        # Called only before this Core accepts HTTP requests. No provider work.
        async with self._sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            await session.execute(
                update(Execution).where(Execution.state == "running").values(state="interrupted")
            )
