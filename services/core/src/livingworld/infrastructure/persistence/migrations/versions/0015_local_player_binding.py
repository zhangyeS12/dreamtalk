"""Bind the current local data-directory user to one Player in each World."""

import sqlalchemy as sa
from alembic import op

revision = "0015_local_player_binding"
down_revision = "0014_episodic_memory"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "local_player_bindings",
        sa.Column("world_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("player_id", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.world_id"]),
        sa.ForeignKeyConstraint(
            ["world_id", "player_id"], ["players.world_id", "players.player_id"]
        ),
    )


def downgrade():
    raise RuntimeError("local_player_binding_downgrade_requires_review")
