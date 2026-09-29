"""Operational plans and consent; Kernel still owns every actual world event."""

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
)
from sqlalchemy.orm import Mapped, mapped_column

from livingworld.infrastructure.persistence.models import Base
from livingworld.infrastructure.persistence.types import UTCTimestampStorage, UUIDStorage


class DirectorSettingsRecord(Base):
    __tablename__ = "director_settings"
    world_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), ForeignKey("worlds.world_id"), primary_key=True
    )
    player_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    plan_id: Mapped[UUID | None] = mapped_column(UUIDStorage())
    error: Mapped[str | None] = mapped_column(String(80))
    consented_at: Mapped[datetime] = mapped_column(UTCTimestampStorage(), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(["world_id", "player_id"], ["players.world_id", "players.player_id"]),
        CheckConstraint("revision >= 0", name="ck_director_settings_revision"),
        CheckConstraint(
            "state IN ('idle','planning','ready','attention','off')",
            name="ck_director_settings_state",
        ),
    )


class DirectorPlanRecord(Base):
    __tablename__ = "director_plans"
    world_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), ForeignKey("worlds.world_id"), primary_key=True
    )
    plan_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    window_start: Mapped[int] = mapped_column(BigInteger, nullable=False)
    window_end: Mapped[int] = mapped_column(BigInteger, nullable=False)
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False)
    input_json: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    error: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(UTCTimestampStorage(), nullable=False)
    __table_args__ = (
        CheckConstraint(
            "window_end > window_start AND candidate_count BETWEEN 0 AND 64 AND generation >= 0",
            name="ck_director_plan_bounds",
        ),
        CheckConstraint(
            "json_valid(input_json) AND length(CAST(input_json AS BLOB)) <= 65536",
            name="ck_director_plan_input",
        ),
        CheckConstraint(
            "state IN ('planning','ready','failed','interrupted','superseded')",
            name="ck_director_plan_state",
        ),
    )


class DirectorCandidateRecord(Base):
    __tablename__ = "director_candidates"
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    candidate_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    plan_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    character_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    location_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    activity: Mapped[str] = mapped_column(String(16), nullable=False)
    due_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    end_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expected_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(80))
    __table_args__ = (
        ForeignKeyConstraint(
            ["world_id", "plan_id"], ["director_plans.world_id", "director_plans.plan_id"]
        ),
        ForeignKeyConstraint(
            ["world_id", "character_id"], ["characters.world_id", "characters.character_id"]
        ),
        ForeignKeyConstraint(
            ["world_id", "location_id"], ["locations.world_id", "locations.location_id"]
        ),
        CheckConstraint(
            "end_at > due_at AND expected_revision >= 0", name="ck_director_candidate_bounds"
        ),
        CheckConstraint(
            "activity IN ('rest','work','leisure')", name="ck_director_candidate_activity"
        ),
        CheckConstraint(
            "state IN ('pending','active','finished','invalid','cancelled','expired')",
            name="ck_director_candidate_state",
        ),
        Index("ix_director_candidate_due", "world_id", "state", "due_at", "candidate_id"),
        Index("ix_director_candidate_character", "world_id", "character_id", "state", "end_at"),
    )
