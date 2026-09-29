"""Player-owned summaries and draft receipts; immutable revisions by application."""

import json
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    func,
    select,
)
from sqlalchemy.orm import Mapped, mapped_column

from livingworld.application.conversation_memory import ConversationMemoryError
from livingworld.application.errors import EntityNotFoundError
from livingworld.infrastructure.persistence.models import (
    Base,
    CharacterRecord,
    ChatConversationRecord,
    ChatMessageRecord,
    ChatParticipantRecord,
    LocalPlayerBindingRecord,
    PlayerRecord,
)
from livingworld.infrastructure.persistence.types import UTCTimestampStorage, UUIDStorage


class ConversationMemoryRevisionRecord(Base):
    __tablename__ = "conversation_memory_revisions"
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    conversation_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    base_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    player_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    through_position: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_ids: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    user_edited: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCTimestampStorage(), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["world_id", "conversation_id"],
            ["chat_conversations.world_id", "chat_conversations.conversation_id"],
        ),
        ForeignKeyConstraint(["world_id", "player_id"], ["players.world_id", "players.player_id"]),
        CheckConstraint(
            "revision > 0 AND base_revision >= 0 AND base_revision < revision "
            "AND through_position > 0",
            name="ck_conversation_memory_revision",
        ),
        CheckConstraint(
            "json_valid(source_ids) AND json_type(source_ids) = 'array' "
            "AND json_array_length(source_ids) <= 32",
            name="ck_conversation_memory_sources",
        ),
        CheckConstraint(
            "length(trim(content)) > 0 AND length(CAST(content AS BLOB)) <= 8192",
            name="ck_conversation_memory_content",
        ),
    )


class ConversationMemoryDraftRecord(Base):
    __tablename__ = "conversation_memory_drafts"
    draft_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    conversation_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    player_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    base_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    through_position: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_ids: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str | None] = mapped_column(Text)
    user_edited: Mapped[bool] = mapped_column(Boolean, nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    reviewed_hash: Mapped[str | None] = mapped_column(String(64))
    committed_revision: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(UTCTimestampStorage(), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["world_id", "conversation_id"],
            ["chat_conversations.world_id", "chat_conversations.conversation_id"],
        ),
        ForeignKeyConstraint(["world_id", "player_id"], ["players.world_id", "players.player_id"]),
        Index(
            "ix_conversation_memory_draft_owner",
            "world_id",
            "conversation_id",
            "player_id",
            "created_at",
            "draft_id",
        ),
        CheckConstraint(
            "base_revision >= 0 AND through_position > 0",
            name="ck_conversation_memory_draft_position",
        ),
        CheckConstraint(
            "mode IN ('summarize','correct')", name="ck_conversation_memory_draft_mode"
        ),
        CheckConstraint(
            "state IN ('generating','ready','previewed','committed','failed','interrupted')",
            name="ck_conversation_memory_draft_state",
        ),
        CheckConstraint(
            "json_valid(source_ids) AND json_type(source_ids) = 'array' "
            "AND json_array_length(source_ids) <= 32",
            name="ck_conversation_memory_draft_sources",
        ),
        CheckConstraint(
            "content IS NULL OR (length(trim(content)) > 0 "
            "AND length(CAST(content AS BLOB)) <= 8192)",
            name="ck_conversation_memory_draft_content",
        ),
        CheckConstraint(
            "reviewed_hash IS NULL OR length(reviewed_hash) = 64",
            name="ck_conversation_memory_draft_hash",
        ),
    )


def _scope(cls, conversation, player):
    return (
        cls.world_id == conversation.world_id.value,
        cls.conversation_id == conversation.value,
        cls.player_id == player.value,
    )


def _view(row):
    if row is None:
        return None
    data = {
        "base_revision": row.base_revision,
        "through_position": row.through_position,
        "source_ids": json.loads(row.source_ids),
        "content": row.content,
        "user_edited": row.user_edited,
        "created_at_utc": row.created_at.isoformat(),
    }
    if isinstance(row, ConversationMemoryDraftRecord):
        data.update(
            draft_id=str(row.draft_id),
            mode=row.mode,
            state=row.state,
            reviewed_hash=row.reviewed_hash,
            committed_revision=row.committed_revision,
            error=row.error,
        )
    else:
        data["revision"] = row.revision
    return data


class SqlAlchemyConversationMemoryStore:
    def __init__(self, sessions):
        self._sessions = sessions

    async def _owner(self, session, conversation, player):
        if conversation.world_id != player.world_id:
            raise EntityNotFoundError("conversation_not_found")
        binding = await session.get(LocalPlayerBindingRecord, conversation.world_id.value)
        row = await session.scalar(
            select(ChatConversationRecord).where(
                *_scope(ChatConversationRecord, conversation, player)
            )
        )
        if binding is None or binding.player_id != player.value or row is None:
            raise EntityNotFoundError("conversation_not_found")

    async def _head(self, session, conversation, player, before_position=None):
        query = select(ConversationMemoryRevisionRecord).where(
            *_scope(ConversationMemoryRevisionRecord, conversation, player)
        )
        if before_position is not None:
            query = query.where(ConversationMemoryRevisionRecord.through_position < before_position)
        return await session.scalar(
            query.order_by(ConversationMemoryRevisionRecord.revision.desc()).limit(1)
        )

    async def _draft(self, session, conversation, player, draft_id):
        row = await session.scalar(
            select(ConversationMemoryDraftRecord).where(
                *_scope(ConversationMemoryDraftRecord, conversation, player),
                ConversationMemoryDraftRecord.draft_id == draft_id,
            )
        )
        if row is None:
            raise ConversationMemoryError("memory_draft_not_found")
        return row

    async def _revision(self, session, conversation, player, revision):
        row = await session.scalar(
            select(ConversationMemoryRevisionRecord).where(
                *_scope(ConversationMemoryRevisionRecord, conversation, player),
                ConversationMemoryRevisionRecord.revision == revision,
            )
        )
        if row is None:
            raise ConversationMemoryError("memory_revision_not_found")
        return row

    async def _source_messages(self, session, conversation, player, ids):
        if not ids:
            return []
        if len(ids) > 32 or len(set(ids)) != len(ids):
            raise ConversationMemoryError("memory_source_invalid")
        rows = list(
            (
                await session.scalars(
                    select(ChatMessageRecord)
                    .where(
                        ChatMessageRecord.world_id == conversation.world_id.value,
                        ChatMessageRecord.conversation_id == conversation.value,
                        ChatMessageRecord.message_id.in_([UUID(value) for value in ids]),
                    )
                    .order_by(ChatMessageRecord.position)
                )
            ).all()
        )
        if [str(row.message_id) for row in rows] != ids:
            raise ConversationMemoryError("memory_source_invalid")
        participants = set(
            (
                await session.scalars(
                    select(ChatParticipantRecord.character_id).where(
                        ChatParticipantRecord.world_id == conversation.world_id.value,
                        ChatParticipantRecord.conversation_id == conversation.value,
                    )
                )
            ).all()
        )
        if any(
            (
                row.sender_player_id != player.value
                if row.sender_player_id
                else row.sender_character_id not in participants
            )
            for row in rows
        ):
            raise ConversationMemoryError("memory_source_invalid")
        names = dict(
            (
                await session.execute(
                    select(CharacterRecord.character_id, CharacterRecord.name).where(
                        CharacterRecord.world_id == conversation.world_id.value,
                        CharacterRecord.character_id.in_(participants),
                    )
                )
            ).all()
        )
        names[player.value] = (
            await session.scalar(
                select(PlayerRecord.name).where(
                    PlayerRecord.world_id == conversation.world_id.value,
                    PlayerRecord.player_id == player.value,
                )
            )
            or "玩家"
        )
        return [
            {
                "message_id": str(row.message_id),
                "turn_id": str(row.turn_id),
                "conversation_id": str(conversation.value),
                "position": row.position,
                "sender_kind": "player" if row.sender_player_id else "character",
                "sender_id": str(row.sender_player_id or row.sender_character_id),
                "sender_name": names.get(row.sender_player_id or row.sender_character_id, "角色")[
                    :160
                ],
                "text": row.text,
                "created_at_utc": row.created_at_utc.isoformat(),
            }
            for row in rows
        ]

    async def snapshot(self, conversation, player):
        async with self._sessions() as session:
            await self._owner(session, conversation, player)
            head = await self._head(session, conversation, player)
            draft = await session.scalar(
                select(ConversationMemoryDraftRecord)
                .where(*_scope(ConversationMemoryDraftRecord, conversation, player))
                .order_by(
                    ConversationMemoryDraftRecord.created_at.desc(),
                    ConversationMemoryDraftRecord.draft_id.desc(),
                )
                .limit(1)
            )
            latest = await session.scalar(
                select(func.max(ChatMessageRecord.position)).where(
                    ChatMessageRecord.world_id == conversation.world_id.value,
                    ChatMessageRecord.conversation_id == conversation.value,
                )
            )
            return {"current": _view(head), "draft": _view(draft), "latest_position": latest or 0}

    async def claim(self, conversation, player, draft_id, base_revision, mode):
        async with self._sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            await self._owner(session, conversation, player)
            existing = await session.get(ConversationMemoryDraftRecord, draft_id)
            if existing is not None:
                if (
                    existing.world_id,
                    existing.conversation_id,
                    existing.player_id,
                    existing.base_revision,
                    existing.mode,
                ) != (
                    conversation.world_id.value,
                    conversation.value,
                    player.value,
                    base_revision,
                    mode,
                ):
                    raise ConversationMemoryError("memory_request_conflict")
                return False, _view(existing)
            head = await self._head(session, conversation, player)
            if (head.revision if head else 0) != base_revision:
                raise ConversationMemoryError("memory_revision_changed")
            through = head.through_position if head else 0
            selected = []
            if mode == "summarize":
                rows = list(
                    (
                        await session.scalars(
                            select(ChatMessageRecord)
                            .where(
                                ChatMessageRecord.world_id == conversation.world_id.value,
                                ChatMessageRecord.conversation_id == conversation.value,
                                ChatMessageRecord.position > through,
                            )
                            .order_by(ChatMessageRecord.position)
                            .limit(32)
                        )
                    ).all()
                )
                used = 0
                for row in rows:
                    size = len(row.text.encode("utf-8"))
                    if used + size > 96 * 1024:
                        break
                    selected.append(str(row.message_id))
                    through = row.position
                    used += size
                if not selected:
                    raise ConversationMemoryError("memory_no_new_messages")
                await self._source_messages(session, conversation, player, selected)
            elif mode != "correct" or head is None:
                raise ConversationMemoryError("memory_correction_unavailable")
            row = ConversationMemoryDraftRecord(
                draft_id=draft_id,
                world_id=conversation.world_id.value,
                conversation_id=conversation.value,
                player_id=player.value,
                base_revision=base_revision,
                mode=mode,
                through_position=through,
                source_ids=json.dumps(selected),
                content=head.content if mode == "correct" else None,
                user_edited=mode == "correct",
                state="ready" if mode == "correct" else "generating",
                created_at=datetime.now(UTC),
            )
            session.add(row)
            return True, _view(row)

    async def generation_input(self, conversation, player, draft_id):
        async with self._sessions() as session:
            await self._owner(session, conversation, player)
            row = await self._draft(session, conversation, player, draft_id)
            previous = (
                await self._revision(session, conversation, player, row.base_revision)
                if row.base_revision
                else None
            )
            return _view(previous), await self._source_messages(
                session, conversation, player, json.loads(row.source_ids)
            )

    async def draft(self, conversation, player, draft_id):
        async with self._sessions() as session:
            await self._owner(session, conversation, player)
            return _view(await self._draft(session, conversation, player, draft_id))

    async def finish(self, conversation, player, draft_id, state, *, content=None, error=None):
        async with self._sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            await self._owner(session, conversation, player)
            row = await self._draft(session, conversation, player, draft_id)
            if row.state != "generating":
                raise ConversationMemoryError("memory_state_invalid")
            row.state, row.content, row.error = state, content, error

    async def preview(self, conversation, player, draft_id, content):
        async with self._sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            await self._owner(session, conversation, player)
            row = await self._draft(session, conversation, player, draft_id)
            if row.state not in ("ready", "previewed"):
                raise ConversationMemoryError("memory_state_invalid")
            head = await self._head(session, conversation, player)
            if (head.revision if head else 0) != row.base_revision:
                raise ConversationMemoryError("memory_revision_changed")
            await self._source_messages(session, conversation, player, json.loads(row.source_ids))
            row.user_edited = row.user_edited or row.content != content
            row.content = content
            row.reviewed_hash = sha256(
                json.dumps(
                    [
                        "conversation_summary_v1",
                        str(row.world_id),
                        str(row.player_id),
                        str(row.conversation_id),
                        str(row.draft_id),
                        row.base_revision,
                        row.mode,
                        row.through_position,
                        json.loads(row.source_ids),
                        row.content,
                        row.user_edited,
                    ],
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            row.state = "previewed"
            return _view(row)

    async def commit(self, conversation, player, draft_id, reviewed_hash):
        async with self._sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            await self._owner(session, conversation, player)
            row = await self._draft(session, conversation, player, draft_id)
            if row.reviewed_hash != reviewed_hash:
                raise ConversationMemoryError("memory_preview_changed")
            if row.state == "committed":
                return _view(
                    await self._revision(session, conversation, player, row.committed_revision)
                )
            if row.state != "previewed":
                raise ConversationMemoryError("memory_state_invalid")
            head = await self._head(session, conversation, player)
            if (head.revision if head else 0) != row.base_revision:
                raise ConversationMemoryError("memory_revision_changed")
            await self._source_messages(session, conversation, player, json.loads(row.source_ids))
            revision = ConversationMemoryRevisionRecord(
                world_id=row.world_id,
                conversation_id=row.conversation_id,
                player_id=row.player_id,
                revision=row.base_revision + 1,
                base_revision=row.base_revision,
                through_position=row.through_position,
                source_ids=row.source_ids,
                content=row.content,
                user_edited=row.user_edited,
                created_at=datetime.now(UTC),
            )
            session.add(revision)
            row.state, row.committed_revision = "committed", revision.revision
            return _view(revision)

    async def revision(self, conversation, player, revision):
        async with self._sessions() as session:
            await self._owner(session, conversation, player)
            row = await self._revision(session, conversation, player, revision)
            return {
                "memory": _view(row),
                "sources": await self._source_messages(
                    session, conversation, player, json.loads(row.source_ids)
                ),
            }

    async def sources(self, conversation, player, draft_id):
        async with self._sessions() as session:
            await self._owner(session, conversation, player)
            row = await self._draft(session, conversation, player, draft_id)
            return {
                "items": await self._source_messages(
                    session, conversation, player, json.loads(row.source_ids)
                )
            }

    async def for_character(self, conversation, player, character, before_position):
        async with self._sessions() as session:
            await self._owner(session, conversation, player)
            if (
                character.world_id != conversation.world_id
                or await session.scalar(
                    select(ChatParticipantRecord.character_id).where(
                        ChatParticipantRecord.world_id == conversation.world_id.value,
                        ChatParticipantRecord.conversation_id == conversation.value,
                        ChatParticipantRecord.character_id == character.value,
                    )
                )
                is None
            ):
                raise EntityNotFoundError("conversation_not_found")
            row = await self._head(session, conversation, player, before_position)
            return _view(row)
