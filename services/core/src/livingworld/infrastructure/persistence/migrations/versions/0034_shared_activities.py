"""Add consent and shared leisure lifecycle; no rewrite or backfill of old facts."""

import sqlalchemy as sa
from alembic import op

revision = "0034_shared_activities"
down_revision = "0033_character_encounters"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "director_shared_settings",
        sa.Column("world_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("player_id", sa.String(32), primary_key=False, nullable=False),
        sa.Column("enabled", sa.Boolean(), primary_key=False, nullable=False),
        sa.Column("revision", sa.Integer(), primary_key=False, nullable=False),
        sa.Column("consented_at", sa.String(32), primary_key=False, nullable=False),
        sa.ForeignKeyConstraint(
            ["world_id", "player_id"], ["players.world_id", "players.player_id"]
        ),
        sa.CheckConstraint("revision >= 0", name="ck_shared_settings_revision"),
    )
    op.create_table(
        "director_shared_activities",
        sa.Column("world_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("candidate_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("plan_id", sa.String(32), primary_key=False, nullable=False),
        sa.Column("consent_revision", sa.Integer(), primary_key=False, nullable=False),
        sa.Column("encounter_revision", sa.Integer(), primary_key=False, nullable=False),
        sa.Column("first_character_id", sa.String(32), primary_key=False, nullable=False),
        sa.Column("second_character_id", sa.String(32), primary_key=False, nullable=False),
        sa.Column("location_id", sa.String(32), primary_key=False, nullable=False),
        sa.Column("first_routine_id", sa.String(32), primary_key=False, nullable=False),
        sa.Column("second_routine_id", sa.String(32), primary_key=False, nullable=False),
        sa.Column("due_at", sa.BigInteger(), primary_key=False, nullable=False),
        sa.Column("start_deadline", sa.BigInteger(), primary_key=False, nullable=False),
        sa.Column("duration_us", sa.BigInteger(), primary_key=False, nullable=False),
        sa.Column("activity", sa.String(24), primary_key=False, nullable=False),
        sa.Column("state", sa.String(16), primary_key=False, nullable=False),
        sa.Column("reason", sa.String(80), primary_key=False, nullable=True),
        sa.Column("started_at", sa.BigInteger(), primary_key=False, nullable=True),
        sa.Column("planned_end", sa.BigInteger(), primary_key=False, nullable=True),
        sa.Column("first_revision", sa.BigInteger(), primary_key=False, nullable=True),
        sa.Column("second_revision", sa.BigInteger(), primary_key=False, nullable=True),
        sa.Column("continuity_lost", sa.Boolean(), primary_key=False, nullable=False),
        sa.ForeignKeyConstraint(
            ["world_id", "plan_id"], ["director_plans.world_id", "director_plans.plan_id"]
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "first_character_id"], ["characters.world_id", "characters.character_id"]
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "second_character_id"], ["characters.world_id", "characters.character_id"]
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "location_id"], ["locations.world_id", "locations.location_id"]
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "first_routine_id"],
            ["director_candidates.world_id", "director_candidates.candidate_id"],
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "second_routine_id"],
            ["director_candidates.world_id", "director_candidates.candidate_id"],
        ),
        sa.CheckConstraint(
            "start_deadline > due_at AND start_deadline <= due_at + 300000000 AND "
            "duration_us BETWEEN 900000000 AND 1800000000 AND consent_revision >= 0 "
            "AND encounter_revision >= 0",
            name="ck_shared_bounds",
        ),
        sa.CheckConstraint("first_character_id < second_character_id", name="ck_shared_pair"),
        sa.CheckConstraint(
            "activity IN ('shared_rest','shared_leisure')", name="ck_shared_activity"
        ),
        sa.CheckConstraint(
            "state IN ('pending','active','ended','interrupted','cancelled','expired')",
            name="ck_shared_state",
        ),
        sa.CheckConstraint(
            "(state IN ('active','ended','interrupted') AND started_at IS NOT NULL AND "
            "planned_end IS NOT NULL AND planned_end = started_at + duration_us AND "
            "first_revision IS NOT NULL AND second_revision IS NOT NULL AND started_at >="
            " due_at AND started_at < start_deadline) OR (state IN "
            "('pending','cancelled','expired') AND started_at IS NULL AND planned_end IS "
            "NULL AND first_revision IS NULL AND second_revision IS NULL)",
            name="ck_shared_execution",
        ),
    )
    op.create_index(
        "ix_shared_due",
        "director_shared_activities",
        ["world_id", "state", "due_at", "candidate_id"],
    )
    op.create_index(
        "ix_shared_pair",
        "director_shared_activities",
        ["world_id", "first_character_id", "second_character_id", "started_at"],
    )


def downgrade():
    op.drop_table("director_shared_activities")
    op.drop_table("director_shared_settings")
