"""Authored containment, per-character access and movement scopes."""

from uuid import UUID

from sqlalchemy import BigInteger, Boolean, CheckConstraint, ForeignKeyConstraint, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from livingworld.infrastructure.persistence.models import Base, UUIDStorage


class LocationPolicyRecord(Base):
    __tablename__ = "location_policies"
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    location_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    parent_id: Mapped[UUID | None] = mapped_column(UUIDStorage())
    hidden: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    is_region: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["world_id", "location_id"], ["locations.world_id", "locations.location_id"]
        ),
        ForeignKeyConstraint(
            ["world_id", "parent_id"], ["locations.world_id", "locations.location_id"]
        ),
        CheckConstraint(
            "parent_id IS NULL OR parent_id != location_id", name="ck_location_parent_self"
        ),
    )


class LocationAccessRecord(Base):
    __tablename__ = "location_character_access"
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    location_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    character_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    __table_args__ = (
        ForeignKeyConstraint(
            ["world_id", "location_id"], ["locations.world_id", "locations.location_id"]
        ),
        ForeignKeyConstraint(
            ["world_id", "character_id"], ["characters.world_id", "characters.character_id"]
        ),
    )


class CharacterLocationPolicyRecord(Base):
    __tablename__ = "character_location_policies"
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    character_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    initial_location_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    locked: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    revision: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    residency: Mapped[str] = mapped_column(String(16), nullable=False, default="strong")
    __table_args__ = (
        ForeignKeyConstraint(
            ["world_id", "character_id"], ["characters.world_id", "characters.character_id"]
        ),
        ForeignKeyConstraint(
            ["world_id", "initial_location_id"], ["locations.world_id", "locations.location_id"]
        ),
        CheckConstraint("revision >= 0", name="ck_character_location_policy_revision"),
    )


class CharacterMobilityRecord(Base):
    """Operational gates; actual positions remain canonical Kernel state."""

    __tablename__ = "character_mobility"
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    character_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    next_draw_at: Mapped[int] = mapped_column(BigInteger(), nullable=False, default=0)
    cooldown_until: Mapped[int] = mapped_column(BigInteger(), nullable=False, default=0)
    away_since: Mapped[int | None] = mapped_column(BigInteger())
    far_since: Mapped[int | None] = mapped_column(BigInteger())
    __table_args__ = (
        ForeignKeyConstraint(
            ["world_id", "character_id"], ["characters.world_id", "characters.character_id"]
        ),
        CheckConstraint(
            "next_draw_at >= 0 AND cooldown_until >= 0", name="ck_character_mobility_gate"
        ),
    )
