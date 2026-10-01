"""Player-reported journal and consented public news reservoir, separate from Truth."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
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


class ChatStoryRecord(Base):
    __tablename__ = "chat_story_entries"
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    entry_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    player_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    character_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    conversation_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    message_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(80), nullable=False)
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    time_text: Mapped[str | None] = mapped_column(String(100))
    source_event_id: Mapped[UUID | None] = mapped_column(UUIDStorage())
    updates_entry_id: Mapped[UUID | None] = mapped_column(UUIDStorage())
    learned_world_time: Mapped[int | None] = mapped_column(BigInteger)
    learned_at: Mapped[datetime] = mapped_column(UTCTimestampStorage(), nullable=False)
    hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    correction: Mapped[str | None] = mapped_column(String(500))
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(["world_id", "player_id"], ["players.world_id", "players.player_id"]),
        ForeignKeyConstraint(
            ["world_id", "character_id"], ["characters.world_id", "characters.character_id"]
        ),
        ForeignKeyConstraint(
            ["world_id", "conversation_id"],
            ["chat_conversations.world_id", "chat_conversations.conversation_id"],
        ),
        ForeignKeyConstraint(
            ["world_id", "message_id"], ["chat_messages.world_id", "chat_messages.message_id"]
        ),
        ForeignKeyConstraint(
            ["world_id", "source_event_id"], ["world_events.world_id", "world_events.event_id"]
        ),
        ForeignKeyConstraint(
            ["world_id", "updates_entry_id"],
            ["chat_story_entries.world_id", "chat_story_entries.entry_id"],
        ),
        CheckConstraint(
            "kind IN ('activity','plan','rumor','invitation','change')", name="ck_chat_story_kind"
        ),
        UniqueConstraint("world_id", "player_id", "fingerprint", name="uq_chat_story_fingerprint"),
        Index("ix_chat_story_owner_time", "world_id", "player_id", "learned_at", "entry_id"),
    )


class WorldNewsSettingsRecord(Base):
    __tablename__ = "world_news_settings"
    world_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), ForeignKey("worlds.world_id"), primary_key=True
    )
    player_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    consented_at: Mapped[datetime] = mapped_column(UTCTimestampStorage(), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    error: Mapped[str | None] = mapped_column(String(80))
    next_publish_at: Mapped[int | None] = mapped_column(BigInteger)
    __table_args__ = (
        ForeignKeyConstraint(["world_id", "player_id"], ["players.world_id", "players.player_id"]),
        CheckConstraint("revision >= 0", name="ck_world_news_revision"),
        CheckConstraint(
            "state IN ('off','idle','generating','ready','attention')", name="ck_world_news_state"
        ),
    )


class WorldNewsBatchRecord(Base):
    __tablename__ = "world_news_batches"
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    batch_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    player_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    invocation_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False, unique=True)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    input_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCTimestampStorage(), nullable=False)
    replenished: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    __table_args__ = (
        ForeignKeyConstraint(["world_id", "player_id"], ["players.world_id", "players.player_id"]),
        CheckConstraint(
            "state IN ('queued','dispatched','ready','failed','interrupted','cancelled')",
            name="ck_world_news_batch_state",
        ),
        CheckConstraint("total >= 0 AND total <= 20", name="ck_world_news_batch_total"),
        Index("ix_world_news_batch_world_time", "world_id", "created_at", "batch_id"),
    )


class WorldNewsCandidateRecord(Base):
    __tablename__ = "world_news_candidates"
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    entry_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    batch_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    title: Mapped[str] = mapped_column(String(80), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    time_text: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    available_from: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expires_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    shuffle_key: Mapped[str] = mapped_column(String(64), nullable=False)
    event_id: Mapped[UUID | None] = mapped_column(UUIDStorage())
    published_at: Mapped[datetime | None] = mapped_column(UTCTimestampStorage())
    occurred_at: Mapped[int | None] = mapped_column(BigInteger)
    __table_args__ = (
        ForeignKeyConstraint(
            ["world_id", "batch_id"], ["world_news_batches.world_id", "world_news_batches.batch_id"]
        ),
        ForeignKeyConstraint(
            ["world_id", "event_id"], ["world_events.world_id", "world_events.event_id"]
        ),
        CheckConstraint("expires_at > available_from", name="ck_world_news_candidate_time"),
        CheckConstraint(
            "state IN ('pending','published','cancelled')", name="ck_world_news_candidate_state"
        ),
        Index("ix_world_news_candidate_queue", "world_id", "state", "shuffle_key"),
    )


class WorldNewsMarkRecord(Base):
    __tablename__ = "world_news_marks"
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    player_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    entry_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(["world_id", "player_id"], ["players.world_id", "players.player_id"]),
        ForeignKeyConstraint(
            ["world_id", "entry_id"],
            ["world_news_candidates.world_id", "world_news_candidates.entry_id"],
        ),
        CheckConstraint(
            "state IN ('pending','experienced','skipped')", name="ck_world_news_mark_state"
        ),
        CheckConstraint("revision >= 0", name="ck_world_news_mark_revision"),
    )
