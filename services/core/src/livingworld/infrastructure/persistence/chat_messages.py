"""Atomic, idempotent transcript writes, independent of the WorldEvent ledger."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select

from livingworld.application.chat_messages import (
    ChatMessage,
    ClaimedDirectTurn,
    DirectTurnView,
    PlayerSend,
)
from livingworld.application.errors import (
    ChatTurnUnavailableError,
    EntityNotFoundError,
    IdempotencyConflictError,
)
from livingworld.domain.contracts import RequestId
from livingworld.domain.identifiers import (
    CharacterId,
    ChatTurnId,
    ConversationId,
    MessageId,
    PlayerId,
    WorldId,
)
from livingworld.infrastructure.persistence.models import (
    ChatConversationRecord,
    ChatMessageRecord,
    ChatParticipantRecord,
    ChatTurnDispatchRecord,
    ChatTurnRecord,
)


def _message(row: ChatMessageRecord) -> ChatMessage:
    world_id = WorldId(row.world_id)
    if (row.sender_player_id is None) == (row.sender_character_id is None):
        raise EntityNotFoundError("chat_state_invalid")
    sender = (
        PlayerId(world_id, row.sender_player_id)
        if row.sender_player_id is not None
        else CharacterId(world_id, row.sender_character_id)
    )
    return ChatMessage(
        MessageId(world_id, row.message_id),
        ConversationId(world_id, row.conversation_id),
        ChatTurnId(world_id, row.turn_id),
        row.position,
        sender,
        row.text,
        row.created_at_utc,
    )


class SqlAlchemyChatMessageStore:
    def __init__(self, sessions) -> None:
        self._sessions = sessions

    async def _conversation(self, session, conversation_id: ConversationId, player_id: PlayerId):
        if conversation_id.world_id != player_id.world_id:
            raise EntityNotFoundError("chat_world_mismatch")
        conversation = await session.get(
            ChatConversationRecord, (conversation_id.world_id.value, conversation_id.value)
        )
        if conversation is None or conversation.player_id != player_id.value:
            raise EntityNotFoundError("conversation_not_found")
        return conversation

    async def send_player(
        self,
        request_id: RequestId,
        conversation_id: ConversationId,
        player_id: PlayerId,
        text: str,
        token_ceiling: int,
        fingerprint: str,
    ) -> PlayerSend:
        async with self._sessions() as session, session.begin():
            # SQLite obtains a write reservation before any receipt/position read.
            await session.connection(execution_options={"livingworld_write_intent": True})
            existing = await session.scalar(
                select(ChatTurnRecord).where(ChatTurnRecord.request_id == request_id.value)
            )
            if existing is not None:
                if (
                    existing.world_id != conversation_id.world_id.value
                    or existing.conversation_id != conversation_id.value
                    or existing.fingerprint != fingerprint
                    or existing.token_ceiling != token_ceiling
                ):
                    raise IdempotencyConflictError("chat_request_conflict")
                message = await session.scalar(
                    select(ChatMessageRecord).where(
                        ChatMessageRecord.world_id == existing.world_id,
                        ChatMessageRecord.turn_id == existing.turn_id,
                        ChatMessageRecord.sender_player_id == player_id.value,
                    )
                )
                if message is None:
                    raise EntityNotFoundError("chat_state_invalid")
                return PlayerSend(
                    ChatTurnId(conversation_id.world_id, existing.turn_id),
                    _message(message),
                    existing.token_ceiling,
                    existing.status,
                )
            conversation = await self._conversation(session, conversation_id, player_id)
            if conversation.kind != "direct":
                raise ChatTurnUnavailableError("group_turn_unavailable")
            position = (
                await session.scalar(
                    select(func.max(ChatMessageRecord.position)).where(
                        ChatMessageRecord.world_id == conversation_id.world_id.value,
                        ChatMessageRecord.conversation_id == conversation_id.value,
                    )
                )
                or 0
            ) + 1
            turn_id = uuid4()
            message_id = uuid4()
            created_at = datetime.now(UTC)
            session.add(
                ChatTurnRecord(
                    world_id=conversation_id.world_id.value,
                    turn_id=turn_id,
                    conversation_id=conversation_id.value,
                    request_id=request_id.value,
                    fingerprint=fingerprint,
                    token_ceiling=token_ceiling,
                    status="pending",
                    created_at_utc=created_at,
                )
            )
            await session.flush()
            row = ChatMessageRecord(
                world_id=conversation_id.world_id.value,
                message_id=message_id,
                conversation_id=conversation_id.value,
                turn_id=turn_id,
                position=position,
                sender_player_id=player_id.value,
                sender_character_id=None,
                text=text,
                created_at_utc=created_at,
            )
            session.add(row)
            await session.flush()
            return PlayerSend(
                ChatTurnId(conversation_id.world_id, turn_id),
                _message(row),
                token_ceiling,
                "pending",
            )

    async def list_for_player(
        self, conversation_id: ConversationId, player_id: PlayerId
    ) -> tuple[ChatMessage, ...]:
        async with self._sessions() as session:
            await self._conversation(session, conversation_id, player_id)
            rows = (
                await session.scalars(
                    select(ChatMessageRecord)
                    .where(
                        ChatMessageRecord.world_id == conversation_id.world_id.value,
                        ChatMessageRecord.conversation_id == conversation_id.value,
                    )
                    .order_by(ChatMessageRecord.position)
                )
            ).all()
            return tuple(_message(row) for row in rows)

    async def direct_turn(
        self, conversation_id: ConversationId, turn_id: ChatTurnId, player_id: PlayerId
    ) -> DirectTurnView:
        if turn_id.world_id != conversation_id.world_id:
            raise EntityNotFoundError("chat_world_mismatch")
        async with self._sessions() as session:
            conversation = await self._conversation(session, conversation_id, player_id)
            if conversation.kind != "direct":
                raise ChatTurnUnavailableError("direct_turn_required")
            turn = await session.get(
                ChatTurnRecord, (conversation_id.world_id.value, turn_id.value)
            )
            if turn is None or turn.conversation_id != conversation_id.value:
                raise EntityNotFoundError("chat_turn_not_found")
            rows = (
                await session.scalars(
                    select(ChatMessageRecord).where(
                        ChatMessageRecord.world_id == conversation_id.world_id.value,
                        ChatMessageRecord.conversation_id == conversation_id.value,
                        ChatMessageRecord.turn_id == turn_id.value,
                    )
                )
            ).all()
            player_rows = [row for row in rows if row.sender_player_id == player_id.value]
            replies = [row for row in rows if row.sender_character_id is not None]
            if len(player_rows) != 1 or len(replies) > 1 or len(rows) != 1 + len(replies):
                raise EntityNotFoundError("chat_state_invalid")
            sent = PlayerSend(turn_id, _message(player_rows[0]), turn.token_ceiling, turn.status)
            dispatch = await session.get(
                ChatTurnDispatchRecord, (conversation_id.world_id.value, turn_id.value)
            )
            if replies and dispatch is None:
                raise EntityNotFoundError("chat_state_invalid")
            state = "completed" if replies else "claimed" if dispatch else "pending"
            return DirectTurnView(sent, state, _message(replies[0]) if replies else None)

    async def claim_direct(
        self, conversation_id: ConversationId, turn_id: ChatTurnId, player_id: PlayerId
    ) -> ClaimedDirectTurn:
        if turn_id.world_id != conversation_id.world_id:
            raise EntityNotFoundError("chat_world_mismatch")
        async with self._sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            conversation = await self._conversation(session, conversation_id, player_id)
            if conversation.kind != "direct":
                raise ChatTurnUnavailableError("direct_turn_required")
            turn = await session.get(
                ChatTurnRecord, (conversation_id.world_id.value, turn_id.value)
            )
            if turn is None or turn.conversation_id != conversation_id.value:
                raise EntityNotFoundError("chat_turn_not_found")
            if turn.status != "pending":
                raise ChatTurnUnavailableError("chat_turn_state_invalid")
            if (
                await session.get(
                    ChatTurnDispatchRecord, (conversation_id.world_id.value, turn_id.value)
                )
                is not None
            ):
                raise ChatTurnUnavailableError("chat_turn_already_claimed")
            participants = (
                await session.scalars(
                    select(ChatParticipantRecord).where(
                        ChatParticipantRecord.world_id == conversation_id.world_id.value,
                        ChatParticipantRecord.conversation_id == conversation_id.value,
                    )
                )
            ).all()
            if len(participants) != 1:
                raise ChatTurnUnavailableError("direct_participant_invalid")
            player_message = await session.scalar(
                select(ChatMessageRecord).where(
                    ChatMessageRecord.world_id == conversation_id.world_id.value,
                    ChatMessageRecord.turn_id == turn_id.value,
                    ChatMessageRecord.sender_player_id == player_id.value,
                )
            )
            if player_message is None or player_message.conversation_id != conversation_id.value:
                raise EntityNotFoundError("chat_state_invalid")
            session.add(
                ChatTurnDispatchRecord(
                    world_id=conversation_id.world_id.value,
                    turn_id=turn_id.value,
                    claimed_at_utc=datetime.now(UTC),
                )
            )
            await session.flush()
            return ClaimedDirectTurn(
                turn_id,
                conversation_id,
                player_id,
                CharacterId(conversation_id.world_id, participants[0].character_id),
                _message(player_message),
                turn.token_ceiling,
            )

    async def complete_direct(self, claim: ClaimedDirectTurn, text: str) -> ChatMessage:
        if not (
            claim.turn_id.world_id
            == claim.conversation_id.world_id
            == claim.player_id.world_id
            == claim.character_id.world_id
        ):
            raise EntityNotFoundError("chat_world_mismatch")
        world_id = claim.conversation_id.world_id.value
        async with self._sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            conversation = await self._conversation(session, claim.conversation_id, claim.player_id)
            turn = await session.get(ChatTurnRecord, (world_id, claim.turn_id.value))
            dispatch = await session.get(ChatTurnDispatchRecord, (world_id, claim.turn_id.value))
            participant = await session.get(
                ChatParticipantRecord,
                (world_id, claim.conversation_id.value, claim.character_id.value),
            )
            player_message = await session.scalar(
                select(ChatMessageRecord).where(
                    ChatMessageRecord.world_id == world_id,
                    ChatMessageRecord.turn_id == claim.turn_id.value,
                    ChatMessageRecord.sender_player_id == claim.player_id.value,
                )
            )
            if (
                conversation.kind != "direct"
                or turn is None
                or turn.conversation_id != claim.conversation_id.value
                or turn.token_ceiling != claim.token_ceiling
                or dispatch is None
                or participant is None
                or player_message is None
                or _message(player_message) != claim.player_message
            ):
                raise ChatTurnUnavailableError("chat_turn_claim_invalid")
            existing = await session.scalar(
                select(ChatMessageRecord).where(
                    ChatMessageRecord.world_id == world_id,
                    ChatMessageRecord.turn_id == claim.turn_id.value,
                    ChatMessageRecord.sender_character_id.is_not(None),
                )
            )
            if existing is not None:
                if (
                    existing.sender_character_id != claim.character_id.value
                    or existing.text != text
                ):
                    raise IdempotencyConflictError("chat_reply_conflict")
                return _message(existing)
            position = (
                await session.scalar(
                    select(func.max(ChatMessageRecord.position)).where(
                        ChatMessageRecord.world_id == world_id,
                        ChatMessageRecord.conversation_id == claim.conversation_id.value,
                    )
                )
                or 0
            ) + 1
            row = ChatMessageRecord(
                world_id=world_id,
                message_id=uuid4(),
                conversation_id=claim.conversation_id.value,
                turn_id=claim.turn_id.value,
                position=position,
                sender_player_id=None,
                sender_character_id=claim.character_id.value,
                text=text,
                created_at_utc=datetime.now(UTC),
            )
            session.add(row)
            await session.flush()
            return _message(row)
