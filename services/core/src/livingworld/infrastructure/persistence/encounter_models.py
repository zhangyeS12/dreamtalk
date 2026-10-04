"""Default-off encounter consent and bounded proposals; no inferred shared facts."""

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
)
from sqlalchemy.orm import Mapped, mapped_column

from livingworld.infrastructure.persistence.models import Base
from livingworld.infrastructure.persistence.types import UTCTimestampStorage, UUIDStorage


class EncounterSettingsRecord(Base):
    __tablename__ = "director_encounter_settings"
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    player_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    consented_at: Mapped[datetime] = mapped_column(UTCTimestampStorage(), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(["world_id", "player_id"], ["players.world_id", "players.player_id"]),
        CheckConstraint("revision >= 0", name="ck_encounter_settings_revision"),
    )


class EncounterCandidateRecord(Base):
    __tablename__ = "director_encounters"
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    candidate_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    plan_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    consent_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    first_character_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    second_character_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    location_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    first_routine_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    second_routine_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    due_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    end_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(80))
    executed_at: Mapped[int | None] = mapped_column(BigInteger)
    __table_args__ = (
        ForeignKeyConstraint(
            ["world_id", "plan_id"], ["director_plans.world_id", "director_plans.plan_id"]
        ),
        ForeignKeyConstraint(
            ["world_id", "first_character_id"], ["characters.world_id", "characters.character_id"]
        ),
        ForeignKeyConstraint(
            ["world_id", "second_character_id"], ["characters.world_id", "characters.character_id"]
        ),
        ForeignKeyConstraint(
            ["world_id", "location_id"], ["locations.world_id", "locations.location_id"]
        ),
        ForeignKeyConstraint(
            ["world_id", "first_routine_id"],
            ["director_candidates.world_id", "director_candidates.candidate_id"],
        ),
        ForeignKeyConstraint(
            ["world_id", "second_routine_id"],
            ["director_candidates.world_id", "director_candidates.candidate_id"],
        ),
        CheckConstraint(
            "end_at > due_at AND end_at <= due_at + 300000000 AND consent_revision >= 0",
            name="ck_encounter_bounds",
        ),
        CheckConstraint("first_character_id < second_character_id", name="ck_encounter_pair"),
        CheckConstraint(
            "state IN ('pending','finished','invalid','cancelled','expired')",
            name="ck_encounter_state",
        ),
        CheckConstraint(
            "(state = 'finished' AND executed_at IS NOT NULL AND executed_at >= due_at "
            "AND executed_at < end_at) OR (state != 'finished' AND executed_at IS NULL)",
            name="ck_encounter_execution",
        ),
        Index("ix_encounter_due", "world_id", "state", "due_at", "candidate_id"),
        Index(
            "ix_encounter_pair",
            "world_id",
            "first_character_id",
            "second_character_id",
            "state",
            "executed_at",
        ),
    )
