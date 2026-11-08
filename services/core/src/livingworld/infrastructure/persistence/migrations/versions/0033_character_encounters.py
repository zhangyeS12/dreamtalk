"""Add opt-in encounter proposals without altering or backfilling old world events."""

import sqlalchemy as sa
from alembic import op

revision = "0033_character_encounters"
down_revision = "0032_chat_context_reports"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "director_encounter_settings",
        sa.Column("world_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("player_id", sa.String(32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("consented_at", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(
            ["world_id", "player_id"], ["players.world_id", "players.player_id"]
        ),
        sa.CheckConstraint("revision >= 0", name="ck_encounter_settings_revision"),
    )
    op.create_table(
        "director_encounters",
        sa.Column("world_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("candidate_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("plan_id", sa.String(32), nullable=False),
        sa.Column("consent_revision", sa.Integer(), nullable=False),
        sa.Column("first_character_id", sa.String(32), nullable=False),
        sa.Column("second_character_id", sa.String(32), nullable=False),
        sa.Column("location_id", sa.String(32), nullable=False),
        sa.Column("first_routine_id", sa.String(32), nullable=False),
        sa.Column("second_routine_id", sa.String(32), nullable=False),
        sa.Column("due_at", sa.BigInteger(), nullable=False),
        sa.Column("end_at", sa.BigInteger(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(80)),
        sa.Column("executed_at", sa.BigInteger()),
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
            "end_at > due_at AND end_at <= due_at + 300000000 AND consent_revision >= 0",
            name="ck_encounter_bounds",
        ),
        sa.CheckConstraint("first_character_id < second_character_id", name="ck_encounter_pair"),
        sa.CheckConstraint(
            "state IN ('pending','finished','invalid','cancelled','expired')",
            name="ck_encounter_state",
        ),
        sa.CheckConstraint(
            "(state = 'finished' AND executed_at IS NOT NULL AND executed_at >= due_at "
            "AND executed_at < end_at) OR (state != 'finished' AND executed_at IS NULL)",
            name="ck_encounter_execution",
        ),
    )
    op.create_index(
        "ix_encounter_due", "director_encounters", ["world_id", "state", "due_at", "candidate_id"]
    )
    op.create_index(
        "ix_encounter_pair",
        "director_encounters",
        ["world_id", "first_character_id", "second_character_id", "state", "executed_at"],
    )


def downgrade():
    op.drop_table("director_encounters")
    op.drop_table("director_encounter_settings")
