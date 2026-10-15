"""Chat attachments and reusable stickers are separate from canonical world facts."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from livingworld.infrastructure.persistence.models import Base
from livingworld.infrastructure.persistence.types import UTCTimestampStorage, UUIDStorage


class MediaAssetRecord(Base):
    __tablename__ = "chat_media_assets"
    asset_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    world_id: Mapped[UUID | None] = mapped_column(UUIDStorage(), ForeignKey("worlds.world_id"))
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    mime: Mapped[str] = mapped_column(String(32), nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary(), nullable=False)
    description: Mapped[str] = mapped_column(Text(), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text())
    caption_state: Mapped[str] = mapped_column(String(16), nullable=False)
    __table_args__ = (Index("ix_media_asset_world", "world_id"),)


class StickerEntryRecord(Base):
    __tablename__ = "chat_sticker_entries"
    entry_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    world_id: Mapped[UUID | None] = mapped_column(UUIDStorage(), ForeignKey("worlds.world_id"))
    library: Mapped[str] = mapped_column(String(16), nullable=False)
    library_key: Mapped[str] = mapped_column(String(128), nullable=False)
    root_import_id: Mapped[UUID | None] = mapped_column(
        UUIDStorage(), ForeignKey("world_content_imports.import_id")
    )
    asset_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), ForeignKey("chat_media_assets.asset_id"), nullable=False
    )
    active: Mapped[bool] = mapped_column(Boolean(), nullable=False)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    added_at_utc: Mapped[datetime | None] = mapped_column(UTCTimestampStorage(), nullable=True)
    __table_args__ = (
        UniqueConstraint("library_key", "asset_id", name="uq_sticker_library_asset"),
        Index("ix_sticker_library", "library_key", "active"),
        CheckConstraint("library IN ('personal','public','character')", name="ck_sticker_library"),
        CheckConstraint(
            "(library = 'personal' AND world_id IS NULL AND root_import_id IS NULL) OR "
            "(library = 'public' AND world_id IS NOT NULL AND root_import_id IS NULL) OR "
            "(library = 'character' AND world_id IS NOT NULL AND root_import_id IS NOT NULL)",
            name="ck_sticker_scope",
        ),
    )


class MediaSettingsRecord(Base):
    __tablename__ = "chat_media_settings"
    world_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), ForeignKey("worlds.world_id"), primary_key=True
    )
    settings_json: Mapped[str] = mapped_column(Text(), nullable=False)


class MediaAttemptRecord(Base):
    __tablename__ = "chat_media_attempts"
    world_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), ForeignKey("worlds.world_id"), primary_key=True
    )
    turn_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    conversation_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    source_position: Mapped[int] = mapped_column(Integer(), nullable=False)
    searched: Mapped[bool] = mapped_column(Boolean(), nullable=False)
    sent: Mapped[bool] = mapped_column(Boolean(), nullable=False)
    sent_kind: Mapped[str | None] = mapped_column(String(16), nullable=True)
    __table_args__ = (
        Index("ix_media_conversation", "world_id", "conversation_id", "source_position"),
    )


class MediaCaptionCallRecord(Base):
    __tablename__ = "chat_media_caption_calls"
    call_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    world_scope: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    asset_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    utc_day: Mapped[str] = mapped_column(String(10), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    usage_json: Mapped[str | None] = mapped_column(Text())
    is_local: Mapped[bool | None] = mapped_column(Boolean(), nullable=True)
    __table_args__ = (Index("ix_media_caption_day", "utc_day"),)
