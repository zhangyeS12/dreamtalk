"""Add reviewed player identity and per-character opening knowledge metadata."""

import sqlalchemy as sa
from alembic import op

revision = "0054_player_personas"
down_revision = "0053_example_world_setup"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "world_player_personas",
        sa.Column("world_id", sa.String(32), primary_key=True),
        sa.Column("player_id", sa.String(32), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("draft_json", sa.Text(), nullable=False),
        sa.Column("confirmation_id", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(
            ["world_id", "player_id"], ["players.world_id", "players.player_id"]
        ),
        sa.CheckConstraint("revision > 0", name="ck_player_persona_revision"),
        sa.CheckConstraint("json_valid(draft_json)", name="ck_player_persona_json"),
    )


def downgrade():
    raise RuntimeError("player_persona_downgrade_not_supported")
