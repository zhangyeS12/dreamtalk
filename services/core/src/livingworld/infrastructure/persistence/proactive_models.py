"""Default-off online consent, one-way outreach claims and separate read watermarks."""

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


class ProactiveSettingsRecord(Base):
    __tablename__ = "proactive_contact_settings"
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True, nullable=False)
    player_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    next_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_plan_id: Mapped[UUID | None] = mapped_column(UUIDStorage(), nullable=True)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    error: Mapped[str | None] = mapped_column(String(80), nullable=True)
    consented_at: Mapped[datetime] = mapped_column(UTCTimestampStorage(), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(["world_id", "player_id"], ["players.world_id", "players.player_id"]),
        CheckConstraint(
            "revision >= 0 AND interval_minutes BETWEEN 15 AND 1440 AND next_at >= 0",
            name="ck_proactive_settings_bounds",
        ),
        CheckConstraint(
            "state IN ('off','idle','writing','attention')", name="ck_proactive_settings_state"
        ),
    )


class ProactiveEpisodeRecord(Base):
    __tablename__ = "proactive_contact_episodes"
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True, nullable=False)
    episode_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True, nullable=False)
    player_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    source_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    source_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    plan_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    input_json: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    error: Mapped[str | None] = mapped_column(String(80), nullable=True)
    conversation_id: Mapped[UUID | None] = mapped_column(UUIDStorage(), nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(UTCTimestampStorage(), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(["world_id", "player_id"], ["players.world_id", "players.player_id"]),
        ForeignKeyConstraint(
            ["world_id", "conversation_id"],
            ["chat_conversations.world_id", "chat_conversations.conversation_id"],
        ),
        ForeignKeyConstraint(
            ["world_id", "plan_id"], ["director_plans.world_id", "director_plans.plan_id"]
        ),
        UniqueConstraint(
            "world_id", "player_id", "source_kind", "source_id", name="uq_proactive_reason"
        ),
        CheckConstraint(
            "source_kind IN ('routine','shared') AND generation >= 0", name="ck_proactive_source"
        ),
        CheckConstraint(
            "state IN ('writing','delivered','cancelled','failed','interrupted')",
            name="ck_proactive_episode_state",
        ),
        CheckConstraint(
            "json_valid(input_json) AND length(CAST(input_json AS BLOB)) <= 65536",
            name="ck_proactive_input",
        ),
        Index("ix_proactive_episode_state", "world_id", "player_id", "state"),
    )


class ChatReadPositionRecord(Base):
    __tablename__ = "chat_read_positions"
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True, nullable=False)
    conversation_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True, nullable=False)
    player_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    position: Mapped[int] = mapped_column(BigInteger, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["world_id", "conversation_id"],
            ["chat_conversations.world_id", "chat_conversations.conversation_id"],
        ),
        ForeignKeyConstraint(["world_id", "player_id"], ["players.world_id", "players.player_id"]),
        CheckConstraint("position >= 0", name="ck_chat_read_position"),
    )
