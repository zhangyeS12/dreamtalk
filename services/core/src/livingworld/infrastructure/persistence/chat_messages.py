"""Atomic, idempotent transcript writes, independent of the WorldEvent ledger."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select

from livingworld.application.chat_messages import ChatMessage, PlayerSend
from livingworld.application.errors import EntityNotFoundError, IdempotencyConflictError
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
            await self._conversation(session, conversation_id, player_id)
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
