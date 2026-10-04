"""Independent default-off shared leisure consent and durable lifecycle candidates."""

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


class SharedActivitySettingsRecord(Base):
    __tablename__ = "director_shared_settings"
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True, nullable=False)
    player_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=False, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, primary_key=False, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, primary_key=False, nullable=False)
    consented_at: Mapped[datetime] = mapped_column(
        UTCTimestampStorage(), primary_key=False, nullable=False
    )
    __table_args__ = (
        ForeignKeyConstraint(["world_id", "player_id"], ["players.world_id", "players.player_id"]),
        CheckConstraint("revision >= 0", name="ck_shared_settings_revision"),
    )


class SharedActivityRecord(Base):
    __tablename__ = "director_shared_activities"
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True, nullable=False)
    candidate_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True, nullable=False)
    plan_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=False, nullable=False)
    consent_revision: Mapped[int] = mapped_column(Integer, primary_key=False, nullable=False)
    encounter_revision: Mapped[int] = mapped_column(Integer, primary_key=False, nullable=False)
    first_character_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), primary_key=False, nullable=False
    )
    second_character_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), primary_key=False, nullable=False
    )
    location_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=False, nullable=False)
    first_routine_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=False, nullable=False)
    second_routine_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), primary_key=False, nullable=False
    )
    due_at: Mapped[int] = mapped_column(BigInteger, primary_key=False, nullable=False)
    start_deadline: Mapped[int] = mapped_column(BigInteger, primary_key=False, nullable=False)
    duration_us: Mapped[int] = mapped_column(BigInteger, primary_key=False, nullable=False)
    activity: Mapped[str] = mapped_column(String(24), primary_key=False, nullable=False)
    state: Mapped[str] = mapped_column(String(16), primary_key=False, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(80), primary_key=False, nullable=True)
    started_at: Mapped[int | None] = mapped_column(BigInteger, primary_key=False, nullable=True)
    planned_end: Mapped[int | None] = mapped_column(BigInteger, primary_key=False, nullable=True)
    first_revision: Mapped[int | None] = mapped_column(BigInteger, primary_key=False, nullable=True)
    second_revision: Mapped[int | None] = mapped_column(
        BigInteger, primary_key=False, nullable=True
    )
    continuity_lost: Mapped[bool] = mapped_column(Boolean, primary_key=False, nullable=False)
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
            "start_deadline > due_at AND start_deadline <= due_at + 300000000 AND "
            "duration_us BETWEEN 900000000 AND 1800000000 AND consent_revision >= 0 "
            "AND encounter_revision >= 0",
            name="ck_shared_bounds",
        ),
        CheckConstraint("first_character_id < second_character_id", name="ck_shared_pair"),
        CheckConstraint("activity IN ('shared_rest','shared_leisure')", name="ck_shared_activity"),
        CheckConstraint(
            "state IN ('pending','active','ended','interrupted','cancelled','expired')",
            name="ck_shared_state",
        ),
        CheckConstraint(
            "(state IN ('active','ended','interrupted') AND started_at IS NOT NULL AND "
            "planned_end IS NOT NULL AND planned_end = started_at + duration_us AND "
            "first_revision IS NOT NULL AND second_revision IS NOT NULL AND started_at >="
            " due_at AND started_at < start_deadline) OR (state IN "
            "('pending','cancelled','expired') AND started_at IS NULL AND planned_end IS "
            "NULL AND first_revision IS NULL AND second_revision IS NULL)",
            name="ck_shared_execution",
        ),
        Index("ix_shared_due", "world_id", "state", "due_at", "candidate_id"),
        Index(
            "ix_shared_pair", "world_id", "first_character_id", "second_character_id", "started_at"
        ),
    )
