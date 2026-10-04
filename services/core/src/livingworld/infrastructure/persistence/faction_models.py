"""World-scoped authored factions and local character presentation."""

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from livingworld.infrastructure.persistence.models import Base
from livingworld.infrastructure.persistence.types import UUIDStorage


class FactionRecord(Base):
    __tablename__ = "character_factions"
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    faction_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    parent_id: Mapped[UUID | None] = mapped_column(UUIDStorage())
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(["world_id"], ["worlds.world_id"]),
        ForeignKeyConstraint(
            ["world_id", "parent_id"],
            ["character_factions.world_id", "character_factions.faction_id"],
        ),
        CheckConstraint("parent_id IS NULL OR parent_id != faction_id", name="ck_faction_not_self"),
        Index("ix_faction_parent", "world_id", "parent_id"),
    )


class FactionMemberRecord(Base):
    __tablename__ = "character_faction_members"
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    faction_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    root_import_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    __table_args__ = (
        ForeignKeyConstraint(
            ["world_id", "faction_id"],
            ["character_factions.world_id", "character_factions.faction_id"],
        ),
        ForeignKeyConstraint(["root_import_id"], ["world_content_imports.import_id"]),
        Index("ix_faction_member_character", "world_id", "root_import_id"),
    )


class CharacterAvatarRecord(Base):
    __tablename__ = "character_avatars"
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    root_import_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(["root_import_id"], ["world_content_imports.import_id"]),
        ForeignKeyConstraint(
            ["world_id", "digest"], ["world_cover_images.world_id", "world_cover_images.digest"]
        ),
        CheckConstraint("length(digest) = 64", name="ck_character_avatar_digest"),
    )


class AcquaintanceRecord(Base):
    """Joining a faction establishes acquaintance; leaving cannot erase a real past."""

    __tablename__ = "character_acquaintances"
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    first_root_import_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    second_root_import_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    source_faction_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(["world_id"], ["worlds.world_id"]),
        ForeignKeyConstraint(["first_root_import_id"], ["world_content_imports.import_id"]),
        ForeignKeyConstraint(["second_root_import_id"], ["world_content_imports.import_id"]),
        CheckConstraint(
            "first_root_import_id < second_root_import_id", name="ck_acquaintance_order"
        ),
    )
