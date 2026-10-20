"""Chat-only paths reference immutable messages; they never fork WorldTruth or accounts."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, ForeignKeyConstraint, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from livingworld.infrastructure.persistence.models import Base
from livingworld.infrastructure.persistence.types import UTCTimestampStorage, UUIDStorage


class ChatPathRecord(Base):
    __tablename__ = "chat_paths"
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    path_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    conversation_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    parent_id: Mapped[UUID | None] = mapped_column(UUIDStorage())
    fork_message_id: Mapped[UUID | None] = mapped_column(UUIDStorage())
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCTimestampStorage(), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["world_id", "conversation_id"],
            ["chat_conversations.world_id", "chat_conversations.conversation_id"],
        ),
        ForeignKeyConstraint(
            ["world_id", "parent_id"], ["chat_paths.world_id", "chat_paths.path_id"]
        ),
        ForeignKeyConstraint(
            ["world_id", "fork_message_id"], ["chat_messages.world_id", "chat_messages.message_id"]
        ),
        CheckConstraint(
            "kind IN ('main','branch','checkpoint','candidate','edit')", name="ck_chat_path_kind"
        ),
        CheckConstraint("length(trim(name)) > 0 AND length(name) <= 80", name="ck_chat_path_name"),
        Index("ix_chat_path_conversation", "world_id", "conversation_id", "created_at", "path_id"),
    )


class ChatPathStateRecord(Base):
    __tablename__ = "chat_path_states"
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    conversation_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    active_path_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["world_id", "conversation_id"],
            ["chat_conversations.world_id", "chat_conversations.conversation_id"],
        ),
        ForeignKeyConstraint(
            ["world_id", "active_path_id"], ["chat_paths.world_id", "chat_paths.path_id"]
        ),
        CheckConstraint("revision >= 0", name="ck_chat_path_revision"),
    )


class ChatPathMessageRecord(Base):
    __tablename__ = "chat_path_messages"
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    path_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    message_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    __table_args__ = (
        ForeignKeyConstraint(
            ["world_id", "path_id"], ["chat_paths.world_id", "chat_paths.path_id"]
        ),
        ForeignKeyConstraint(
            ["world_id", "message_id"], ["chat_messages.world_id", "chat_messages.message_id"]
        ),
        Index("ix_chat_path_message_source", "world_id", "message_id", "path_id"),
    )


class ChatPathTurnRecord(Base):
    __tablename__ = "chat_path_turns"
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    turn_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    path_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["world_id", "turn_id"], ["chat_turns.world_id", "chat_turns.turn_id"]
        ),
        ForeignKeyConstraint(
            ["world_id", "path_id"], ["chat_paths.world_id", "chat_paths.path_id"]
        ),
    )


class ChatPathOperationRecord(Base):
    __tablename__ = "chat_path_operations"
    request_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    conversation_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    result_json: Mapped[str] = mapped_column(Text, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["world_id", "conversation_id"],
            ["chat_conversations.world_id", "chat_conversations.conversation_id"],
        ),
        CheckConstraint(
            "length(fingerprint) = 64 AND json_valid(result_json)", name="ck_chat_path_operation"
        ),
    )


class ChatMemoryOriginRecord(Base):
    __tablename__ = "chat_memory_origins"
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    entry_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    message_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["world_id", "entry_id"], ["long_chat_memories.world_id", "long_chat_memories.entry_id"]
        ),
        ForeignKeyConstraint(
            ["world_id", "message_id"], ["chat_messages.world_id", "chat_messages.message_id"]
        ),
    )


class ChatLoreActivationRecord(Base):
    """Idempotent activation starts anchored to immutable, visible chat messages."""

    __tablename__ = "chat_lore_activations"
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    conversation_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    anchor_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    entry_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    started: Mapped[bool] = mapped_column(Boolean, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["world_id", "conversation_id"],
            ["chat_conversations.world_id", "chat_conversations.conversation_id"],
        ),
        ForeignKeyConstraint(
            ["world_id", "anchor_id"], ["chat_messages.world_id", "chat_messages.message_id"]
        ),
        CheckConstraint("length(entry_key) = 64", name="ck_chat_lore_entry_key"),
    )
