"""Authored containment, per-character access and movement scopes."""

from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, ForeignKeyConstraint, Integer
from sqlalchemy.orm import Mapped, mapped_column

from livingworld.infrastructure.persistence.models import Base, UUIDStorage


class LocationPolicyRecord(Base):
    __tablename__ = "location_policies"
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    location_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    parent_id: Mapped[UUID | None] = mapped_column(UUIDStorage())
    hidden: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
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
    __table_args__ = (
        ForeignKeyConstraint(
            ["world_id", "character_id"], ["characters.world_id", "characters.character_id"]
        ),
        ForeignKeyConstraint(
            ["world_id", "initial_location_id"], ["locations.world_id", "locations.location_id"]
        ),
        CheckConstraint("revision >= 0", name="ck_character_location_policy_revision"),
    )
