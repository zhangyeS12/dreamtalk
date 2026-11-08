"""Add default-off Director consent, finite plans and routine candidate state."""

import sqlalchemy as sa
from alembic import op

revision = "0025_director_runtime"
down_revision = "0024_conversation_memory"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "director_settings",
        sa.Column("world_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("player_id", sa.String(32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("plan_id", sa.String(32)),
        sa.Column("error", sa.String(80)),
        sa.Column("consented_at", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.world_id"]),
        sa.ForeignKeyConstraint(
            ["world_id", "player_id"], ["players.world_id", "players.player_id"]
        ),
        sa.CheckConstraint("revision >= 0", name="ck_director_settings_revision"),
        sa.CheckConstraint(
            "state IN ('idle','planning','ready','attention','off')",
            name="ck_director_settings_state",
        ),
    )
    op.create_table(
        "director_plans",
        sa.Column("world_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("plan_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("window_start", sa.BigInteger(), nullable=False),
        sa.Column("window_end", sa.BigInteger(), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False),
        sa.Column("input_json", sa.Text(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("error", sa.String(80)),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.world_id"]),
        sa.CheckConstraint(
            "window_end > window_start AND candidate_count BETWEEN 0 AND 64 AND generation >= 0",
            name="ck_director_plan_bounds",
        ),
        sa.CheckConstraint(
            "json_valid(input_json) AND length(CAST(input_json AS BLOB)) <= 65536",
            name="ck_director_plan_input",
        ),
        sa.CheckConstraint(
            "state IN ('planning','ready','failed','interrupted','superseded')",
            name="ck_director_plan_state",
        ),
    )
    op.create_table(
        "director_candidates",
        sa.Column("world_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("candidate_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("plan_id", sa.String(32), nullable=False),
        sa.Column("character_id", sa.String(32), nullable=False),
        sa.Column("location_id", sa.String(32), nullable=False),
        sa.Column("activity", sa.String(16), nullable=False),
        sa.Column("due_at", sa.BigInteger(), nullable=False),
        sa.Column("end_at", sa.BigInteger(), nullable=False),
        sa.Column("expected_revision", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(80)),
        sa.ForeignKeyConstraint(
            ["world_id", "plan_id"], ["director_plans.world_id", "director_plans.plan_id"]
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "character_id"], ["characters.world_id", "characters.character_id"]
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "location_id"], ["locations.world_id", "locations.location_id"]
        ),
        sa.CheckConstraint(
            "end_at > due_at AND expected_revision >= 0", name="ck_director_candidate_bounds"
        ),
        sa.CheckConstraint(
            "activity IN ('rest','work','leisure')", name="ck_director_candidate_activity"
        ),
        sa.CheckConstraint(
            "state IN ('pending','active','finished','invalid','cancelled','expired')",
            name="ck_director_candidate_state",
        ),
    )
    op.create_index(
        "ix_director_candidate_due",
        "director_candidates",
        ["world_id", "state", "due_at", "candidate_id"],
    )
    op.create_index(
        "ix_director_candidate_character",
        "director_candidates",
        ["world_id", "character_id", "state", "end_at"],
    )


def downgrade():
    op.drop_table("director_candidates")
    op.drop_table("director_plans")
    op.drop_table("director_settings")
