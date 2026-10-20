"""Add per-world reviewed writing preferences without changing existing worlds."""

import sqlalchemy as sa
from alembic import op

revision = "0055_world_styles"
down_revision = "0054_player_personas"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "world_styles",
        sa.Column("world_id", sa.String(32), primary_key=True),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.world_id"]),
        sa.CheckConstraint("revision > 0", name="ck_world_style_revision"),
    )


def downgrade():
    raise RuntimeError("world_style_downgrade_not_supported")
