"""Local visual metadata, outside canonical and authored lore state."""

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from livingworld.infrastructure.persistence.models import Base
from livingworld.infrastructure.persistence.types import JSONTextStorage, UUIDStorage


class WorldCoverRecord(Base):
    __tablename__ = "world_covers"
    world_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), ForeignKey("worlds.world_id"), primary_key=True
    )
    payload: Mapped[dict] = mapped_column(JSONTextStorage(), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (CheckConstraint("revision > 0", name="ck_world_cover_revision"),)


class WorldCoverImageRecord(Base):
    __tablename__ = "world_cover_images"
    world_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), ForeignKey("worlds.world_id"), primary_key=True
    )
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    media_type: Mapped[str] = mapped_column(String(16), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (
        CheckConstraint("size > 0 AND size <= 10485760", name="ck_world_cover_image_size"),
        CheckConstraint("width > 0 AND height > 0", name="ck_world_cover_image_dimensions"),
        CheckConstraint(
            "media_type IN ('image/jpeg','image/png','image/webp')",
            name="ck_world_cover_image_media",
        ),
    )
