"""User-authored card templates and local presentation, separate from world instances."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from livingworld.infrastructure.persistence.models import Base
from livingworld.infrastructure.persistence.types import (
    JSONTextStorage,
    UTCTimestampStorage,
    UUIDStorage,
)


class CardLibraryRecord(Base):
    __tablename__ = "card_library"
    card_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    reviewed_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    draft_json: Mapped[dict] = mapped_column(JSONTextStorage(), nullable=False)
    design: Mapped[dict | None] = mapped_column(JSONTextStorage(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCTimestampStorage(), nullable=False)
    __table_args__ = (CheckConstraint("revision > 0", name="ck_card_library_revision"),)


class CardLibraryImageRecord(Base):
    __tablename__ = "card_library_images"
    card_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), ForeignKey("card_library.card_id", ondelete="CASCADE"), primary_key=True
    )
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    media_type: Mapped[str] = mapped_column(String(16), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (
        CheckConstraint("size > 0 AND size <= 10485760", name="ck_card_library_image_size"),
        CheckConstraint("width > 0 AND height > 0", name="ck_card_library_image_dimensions"),
        CheckConstraint(
            "media_type IN ('image/jpeg','image/png','image/webp')",
            name="ck_card_library_image_media",
        ),
    )


class CardLibraryWorldRecord(Base):
    __tablename__ = "card_library_worlds"
    card_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), ForeignKey("card_library.card_id", ondelete="CASCADE"), primary_key=True
    )
    world_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), ForeignKey("worlds.world_id", ondelete="CASCADE"), primary_key=True
    )
    import_id: Mapped[UUID] = mapped_column(
        UUIDStorage(),
        ForeignKey("world_content_imports.import_id", ondelete="CASCADE"),
        nullable=False,
    )
    source_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (Index("uq_card_library_world_import", "import_id", unique=True),)


class CardPackRecord(Base):
    __tablename__ = "card_packs"
    pack_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    subtitle: Mapped[str] = mapped_column(String(120), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    design: Mapped[dict] = mapped_column(JSONTextStorage(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCTimestampStorage(), nullable=False)
    __table_args__ = (CheckConstraint("revision > 0", name="ck_card_pack_revision"),)


class CardPackMemberRecord(Base):
    __tablename__ = "card_pack_members"
    pack_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), ForeignKey("card_packs.pack_id", ondelete="CASCADE"), primary_key=True
    )
    card_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), ForeignKey("card_library.card_id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (
        CheckConstraint("position >= 0", name="ck_card_pack_member_position"),
        Index("ix_card_pack_member_order", "pack_id", "position"),
    )


class CardPackImageRecord(Base):
    __tablename__ = "card_pack_images"
    pack_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), ForeignKey("card_packs.pack_id", ondelete="CASCADE"), primary_key=True
    )
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    media_type: Mapped[str] = mapped_column(String(16), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (
        CheckConstraint("size > 0 AND size <= 10485760", name="ck_card_pack_image_size"),
        CheckConstraint("width > 0 AND height > 0", name="ck_card_pack_image_dimensions"),
        CheckConstraint(
            "media_type IN ('image/jpeg','image/png','image/webp')", name="ck_card_pack_image_media"
        ),
    )
