"""Application chat-memory records; do not extend EpisodicMemory provenance."""

from datetime import datetime
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
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from livingworld.infrastructure.persistence.models import Base
from livingworld.infrastructure.persistence.types import UTCTimestampStorage, UUIDStorage


class LongChatMemoryRecord(Base):
    __tablename__ = "long_chat_memories"
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    entry_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    player_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    character_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    conversation_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    message_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    source_sender_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(12), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    topic: Mapped[str] = mapped_column(String(60), nullable=False)
    content: Mapped[str] = mapped_column(String(300), nullable=False)
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCTimestampStorage(), nullable=False)
    world_time: Mapped[int | None] = mapped_column(BigInteger)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    replaces: Mapped[UUID | None] = mapped_column(UUIDStorage())
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(["world_id", "player_id"], ["players.world_id", "players.player_id"]),
        ForeignKeyConstraint(
            ["world_id", "conversation_id", "character_id"],
            [
                "chat_participants.world_id",
                "chat_participants.conversation_id",
                "chat_participants.character_id",
            ],
        ),
        ForeignKeyConstraint(
            ["world_id", "message_id"], ["chat_messages.world_id", "chat_messages.message_id"]
        ),
        ForeignKeyConstraint(
            ["world_id", "replaces"], ["long_chat_memories.world_id", "long_chat_memories.entry_id"]
        ),
        CheckConstraint(
            "kind IN ('identity','preference','promise','experience')", name="ck_long_memory_kind"
        ),
        CheckConstraint("source_kind IN ('player','character')", name="ck_long_memory_source"),
        CheckConstraint(
            "state IN ('active','forgotten','superseded')", name="ck_long_memory_state"
        ),
        CheckConstraint("revision >= 0", name="ck_long_memory_revision"),
        UniqueConstraint(
            "world_id",
            "player_id",
            "character_id",
            "fingerprint",
            name="uq_long_memory_fingerprint",
        ),
        Index(
            "ix_long_memory_owner_time",
            "world_id",
            "player_id",
            "character_id",
            "created_at",
            "entry_id",
        ),
    )


class LongChatMemorySettingsRecord(Base):
    __tablename__ = "long_chat_memory_settings"
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    player_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    character_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(["world_id", "player_id"], ["players.world_id", "players.player_id"]),
        ForeignKeyConstraint(
            ["world_id", "character_id"], ["characters.world_id", "characters.character_id"]
        ),
        CheckConstraint("revision >= 0", name="ck_long_memory_settings_revision"),
    )
