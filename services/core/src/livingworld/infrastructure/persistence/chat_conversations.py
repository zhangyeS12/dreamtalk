"""Durable direct-chat identity bound to an existing local Player and Character."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from livingworld.application.chat_conversations import (
    ChatConversation,
    GroupChatConversation,
    GroupChatParticipant,
)
from livingworld.application.errors import EntityNotFoundError, IdempotencyConflictError
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

    async def _read_group(
        self, session, world_id: WorldId, row: ChatConversationRecord
    ) -> GroupChatConversation:
        if row.kind != "group" or row.direct_root_import_id is not None:
            raise EntityNotFoundError("chat_state_invalid")
        rows = (
            await session.execute(
                select(ChatParticipantRecord, CharacterRecord.name)
                .join(
                    CharacterRecord,
                    (CharacterRecord.world_id == ChatParticipantRecord.world_id)
                    & (CharacterRecord.character_id == ChatParticipantRecord.character_id),
                )
                .where(
                    ChatParticipantRecord.world_id == world_id.value,
                    ChatParticipantRecord.conversation_id == row.conversation_id,
                )
                .order_by(ChatParticipantRecord.root_import_id)
            )
        ).all()
        if len(rows) < 2:
            raise EntityNotFoundError("chat_state_invalid")
        return GroupChatConversation(
            ConversationId(world_id, row.conversation_id),
            PlayerId(world_id, row.player_id),
            tuple(
                GroupChatParticipant(
                    CharacterId(world_id, participant.character_id),
                    participant.root_import_id,
                    name,
                )
                for participant, name in rows
            ),
        )

    async def find_group(
        self, conversation_id: ConversationId, player_id: PlayerId
    ) -> GroupChatConversation | None:
        if conversation_id.world_id != player_id.world_id:
            raise EntityNotFoundError("chat_world_mismatch")
        async with self._sessions() as session:
            row = await session.get(
                ChatConversationRecord,
                (conversation_id.world_id.value, conversation_id.value),
            )
            if row is None:
                return None
            if row.player_id != player_id.value or row.kind != "group":
                raise IdempotencyConflictError("group_request_conflict")
            return await self._read_group(session, conversation_id.world_id, row)

    async def open_group(
        self,
        conversation_id: ConversationId,
        player_id: PlayerId,
        participants: tuple[GroupChatParticipant, ...],
    ) -> GroupChatConversation:
        if conversation_id.world_id != player_id.world_id or any(
            item.character_id.world_id != conversation_id.world_id for item in participants
        ):
            raise EntityNotFoundError("chat_world_mismatch")
        if len(participants) < 2 or len({item.root_import_id for item in participants}) != len(
            participants
        ):
            raise ValueError("group_members_invalid")
        world_id = conversation_id.world_id
        async with self._sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            row = await session.get(ChatConversationRecord, (world_id.value, conversation_id.value))
            if row is None:
                row = ChatConversationRecord(
                    world_id=world_id.value,
                    conversation_id=conversation_id.value,
                    player_id=player_id.value,
                    kind="group",
                    direct_root_import_id=None,
                    created_at_utc=datetime.now(UTC),
                )
                session.add(row)
                for item in participants:
                    session.add(
                        ChatParticipantRecord(
                            world_id=world_id.value,
                            conversation_id=conversation_id.value,
                            character_id=item.character_id.value,
                            root_import_id=item.root_import_id,
                        )
                    )
                await session.flush()
            if row.player_id != player_id.value or row.kind != "group":
                raise IdempotencyConflictError("group_request_conflict")
            group = await self._read_group(session, world_id, row)
            if tuple(item.root_import_id for item in group.participants) != tuple(
                item.root_import_id for item in participants
            ):
                raise IdempotencyConflictError("group_request_conflict")
            return group

    async def list_groups_for_player(
        self, player_id: PlayerId
    ) -> tuple[GroupChatConversation, ...]:
        async with self._sessions() as session:
            rows = (
                await session.scalars(
                    select(ChatConversationRecord)
                    .where(
                        ChatConversationRecord.world_id == player_id.world_id.value,
                        ChatConversationRecord.player_id == player_id.value,
                        ChatConversationRecord.kind == "group",
                    )
                    .order_by(
                        ChatConversationRecord.created_at_utc,
                        ChatConversationRecord.conversation_id,
                    )
                )
            ).all()
            return tuple([await self._read_group(session, player_id.world_id, row) for row in rows])

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
