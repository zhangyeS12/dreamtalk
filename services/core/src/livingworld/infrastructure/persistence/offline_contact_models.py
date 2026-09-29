"""Local recovery receipts; no historical WorldTruth or player-send fabrication."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from livingworld.infrastructure.persistence.models import Base
from livingworld.infrastructure.persistence.types import UTCTimestampStorage, UUIDStorage


class OfflineContactSettingsRecord(Base):
    __tablename__ = "offline_contact_settings"
    singleton: Mapped[int] = mapped_column(Integer, primary_key=True)
    world_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), ForeignKey("worlds.world_id"), nullable=False
    )
    player_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    hours: Mapped[int] = mapped_column(Integer, nullable=False)
    consented_at: Mapped[datetime] = mapped_column(UTCTimestampStorage(), nullable=False)
    last_online_at: Mapped[datetime | None] = mapped_column(UTCTimestampStorage())
    input_json: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    error: Mapped[str | None] = mapped_column(String(80))
    episode_id: Mapped[UUID | None] = mapped_column(UUIDStorage())
    __table_args__ = (
        ForeignKeyConstraint(["world_id", "player_id"], ["players.world_id", "players.player_id"]),
        CheckConstraint(
            "singleton = 1 AND revision > 0 AND hours BETWEEN 1 AND 168",
            name="ck_offline_contact_settings_bounds",
        ),
        CheckConstraint(
            "input_json IS NULL OR (json_valid(input_json) "
            "AND length(CAST(input_json AS BLOB)) <= 65536)",
            name="ck_offline_contact_settings_input",
        ),
        CheckConstraint(
            "state IN ('off','idle','waiting','planning','writing',"
            "'delivered','skipped','attention')",
            name="ck_offline_contact_settings_state",
        ),
    )


class OfflineContactEpisodeRecord(Base):
    __tablename__ = "offline_contact_episodes"
    episode_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    world_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), ForeignKey("worlds.world_id"), nullable=False
    )
    player_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    reason_key: Mapped[str] = mapped_column(String(64), nullable=False)
    offline_from: Mapped[datetime] = mapped_column(UTCTimestampStorage(), nullable=False)
    offline_to: Mapped[datetime] = mapped_column(UTCTimestampStorage(), nullable=False)
    input_json: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    error: Mapped[str | None] = mapped_column(String(80))
    conversation_id: Mapped[UUID | None] = mapped_column(UUIDStorage())
    character_id: Mapped[UUID | None] = mapped_column(UUIDStorage())
    purpose: Mapped[str | None] = mapped_column(String(40))
    story_sent_at_utc: Mapped[datetime | None] = mapped_column(UTCTimestampStorage())
    created_at_utc: Mapped[datetime] = mapped_column(UTCTimestampStorage(), nullable=False)
    message_id: Mapped[UUID | None] = mapped_column(UUIDStorage())
    read_at_utc: Mapped[datetime | None] = mapped_column(UTCTimestampStorage())
    __table_args__ = (
        ForeignKeyConstraint(["world_id", "player_id"], ["players.world_id", "players.player_id"]),
        ForeignKeyConstraint(
            ["world_id", "conversation_id"],
            ["chat_conversations.world_id", "chat_conversations.conversation_id"],
        ),
        ForeignKeyConstraint(
            ["world_id", "character_id"], ["characters.world_id", "characters.character_id"]
        ),
        ForeignKeyConstraint(
            ["world_id", "message_id"], ["chat_messages.world_id", "chat_messages.message_id"]
        ),
        UniqueConstraint("world_id", "player_id", "reason_key", name="uq_offline_contact_reason"),
        CheckConstraint(
            "generation > 0 AND length(reason_key) = 64 AND offline_to > offline_from",
            name="ck_offline_contact_episode_bounds",
        ),
        CheckConstraint(
            "json_valid(input_json) AND length(CAST(input_json AS BLOB)) <= 65536",
            name="ck_offline_contact_episode_input",
        ),
        CheckConstraint(
            "state IN ('queued','planning','writing','delivered','skipped','failed','interrupted')",
            name="ck_offline_contact_episode_state",
        ),
    )


class LocalSessionVisibilityRecord(Base):
    """Operational UI lease; being hidden does not make a player a scene witness."""

    __tablename__ = "local_session_visibility"
    singleton: Mapped[int] = mapped_column(Integer, primary_key=True)
    world_id: Mapped[UUID | None] = mapped_column(UUIDStorage(), ForeignKey("worlds.world_id"))
    visible_until: Mapped[datetime] = mapped_column(UTCTimestampStorage(), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (
        CheckConstraint(
            "singleton = 1 AND sequence >= 0", name="ck_local_session_visibility_bounds"
        ),
    )
