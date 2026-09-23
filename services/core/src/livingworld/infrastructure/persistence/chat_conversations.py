"""Durable direct-chat identity bound to an existing local Player and Character."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from livingworld.application.chat_conversations import ChatConversation
from livingworld.application.errors import EntityNotFoundError
from livingworld.domain.identifiers import CharacterId, ConversationId, PlayerId, WorldId
from livingworld.infrastructure.persistence.models import (
    CharacterRecord,
    ChatConversationRecord,
    ChatParticipantRecord,
)


def _conversation(
    world_id: WorldId,
    row: ChatConversationRecord,
    participant: ChatParticipantRecord,
    name: str,
) -> ChatConversation:
    if row.kind != "direct" or row.direct_root_import_id != participant.root_import_id:
        raise EntityNotFoundError("chat_state_invalid")
    return ChatConversation(
        ConversationId(world_id, row.conversation_id),
        PlayerId(world_id, row.player_id),
        CharacterId(world_id, participant.character_id),
        participant.root_import_id,
        name,
    )


class SqlAlchemyChatConversationStore:
    def __init__(self, sessions) -> None:
        self._sessions = sessions

    async def _read(self, session, world_id: WorldId, conversation_id: UUID) -> ChatConversation:
        result = await session.execute(
            select(ChatConversationRecord, ChatParticipantRecord, CharacterRecord.name)
            .join(
                ChatParticipantRecord,
                (ChatParticipantRecord.world_id == ChatConversationRecord.world_id)
                & (ChatParticipantRecord.conversation_id == ChatConversationRecord.conversation_id),
            )
            .join(
                CharacterRecord,
                (CharacterRecord.world_id == ChatParticipantRecord.world_id)
                & (CharacterRecord.character_id == ChatParticipantRecord.character_id),
            )
            .where(
                ChatConversationRecord.world_id == world_id.value,
                ChatConversationRecord.conversation_id == conversation_id,
            )
        )
        rows = result.all()
        if len(rows) != 1:
            raise EntityNotFoundError("chat_state_invalid")
        row, participant, name = rows[0]
        return _conversation(world_id, row, participant, name)

    async def open_direct(
        self,
        conversation_id: ConversationId,
        player_id: PlayerId,
        character_id: CharacterId,
        root_import_id: UUID,
    ) -> ChatConversation:
        if not (conversation_id.world_id == player_id.world_id == character_id.world_id):
            raise EntityNotFoundError("chat_world_mismatch")
        world_id = conversation_id.world_id
        async with self._sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            existing = await session.get(
                ChatConversationRecord, (world_id.value, conversation_id.value)
            )
            if existing is None:
                session.add(
                    ChatConversationRecord(
                        world_id=world_id.value,
                        conversation_id=conversation_id.value,
                        player_id=player_id.value,
                        kind="direct",
                        direct_root_import_id=root_import_id,
                        created_at_utc=datetime.now(UTC),
                    )
                )
                session.add(
                    ChatParticipantRecord(
                        world_id=world_id.value,
                        conversation_id=conversation_id.value,
                        character_id=character_id.value,
                        root_import_id=root_import_id,
                    )
                )
                await session.flush()
            elif (
                existing.player_id != player_id.value
                or existing.kind != "direct"
                or existing.direct_root_import_id != root_import_id
            ):
                raise EntityNotFoundError("chat_identity_conflict")
            result = await self._read(session, world_id, conversation_id.value)
            if result.character_id != character_id or result.root_import_id != root_import_id:
                raise EntityNotFoundError("chat_identity_conflict")
            return result

    async def list_for_player(self, player_id: PlayerId) -> tuple[ChatConversation, ...]:
        async with self._sessions() as session:
            rows = (
                await session.scalars(
                    select(ChatConversationRecord)
                    .where(
                        ChatConversationRecord.world_id == player_id.world_id.value,
                        ChatConversationRecord.player_id == player_id.value,
                    )
                    .order_by(
                        ChatConversationRecord.created_at_utc,
                        ChatConversationRecord.conversation_id,
                    )
                )
            ).all()
            conversations = []
            for row in rows:
                if row.kind == "direct":
                    conversations.append(
                        await self._read(session, player_id.world_id, row.conversation_id)
                    )
            return tuple(conversations)
