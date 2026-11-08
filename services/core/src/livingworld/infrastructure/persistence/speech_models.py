"""Authored voices, stable bindings, and durable one-shot speech receipts."""

from uuid import UUID

from sqlalchemy import (
    Boolean,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from livingworld.infrastructure.persistence.models import Base
from livingworld.infrastructure.persistence.types import UUIDStorage


class VoiceCardRecord(Base):
    __tablename__ = "voice_cards"
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    card_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    manifest_json: Mapped[str] = mapped_column(Text, nullable=False)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    audio: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(["world_id"], ["worlds.world_id"]),
        Index("ix_voice_card_digest", "world_id", "digest"),
    )


class VoiceBindingRecord(Base):
    __tablename__ = "character_voices"
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    root_import_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    card_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(["world_id"], ["worlds.world_id"]),
        ForeignKeyConstraint(["root_import_id"], ["world_content_imports.import_id"]),
        ForeignKeyConstraint(
            ["world_id", "card_id"], ["voice_cards.world_id", "voice_cards.card_id"]
        ),
    )


class SpeechSettingsRecord(Base):
    __tablename__ = "speech_settings"
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    settings_json: Mapped[str] = mapped_column(Text, nullable=False)
    __table_args__ = (ForeignKeyConstraint(["world_id"], ["worlds.world_id"]),)


class SpeechJobRecord(Base):
    __tablename__ = "speech_jobs"
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    job_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    player_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    conversation_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    message_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    error: Mapped[str | None] = mapped_column(String(96))
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    remote_id: Mapped[str | None] = mapped_column(String(128))
    audio: Mapped[bytes | None] = mapped_column(LargeBinary)
    cache_key: Mapped[str | None] = mapped_column(String(64))
    audio_saved_at: Mapped[str | None] = mapped_column(String(32))
    review_state: Mapped[str | None] = mapped_column(String(16))
    base_job_id: Mapped[UUID | None] = mapped_column(UUIDStorage())
    previewed_at: Mapped[str | None] = mapped_column(String(32))
    __table_args__ = (
        ForeignKeyConstraint(["world_id"], ["worlds.world_id"]),
        UniqueConstraint("world_id", "fingerprint", name="uq_speech_job_fingerprint"),
        Index("ix_speech_cache_key", "world_id", "cache_key", "created_at"),
        Index("ix_speech_audio_saved", "audio_saved_at"),
        Index("ix_speech_review", "world_id", "conversation_id", "message_id", "review_state"),
    )


class SpeechCallRecord(Base):
    """No user content; retained across world erasure so daily admission is not reset."""

    __tablename__ = "speech_call_receipts"
    job_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    day: Mapped[str] = mapped_column(String(10), nullable=False)
    is_local: Mapped[bool | None] = mapped_column(Boolean(), nullable=True)
    __table_args__ = (Index("ix_speech_call_day", "day"),)


class RemoteVoiceRecord(Base):
    """Provider/account-specific IDs; never part of an exported voice card."""

    __tablename__ = "remote_voices"
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    voice_id: Mapped[str] = mapped_column(String(128), nullable=False)
    __table_args__ = (ForeignKeyConstraint(["world_id"], ["worlds.world_id"]),)
