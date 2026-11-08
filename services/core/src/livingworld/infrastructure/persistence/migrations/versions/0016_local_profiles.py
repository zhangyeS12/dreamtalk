"""Persist local self-description and independent world-specific identity."""

import sqlalchemy as sa
from alembic import op

revision = "0016_local_profiles"
down_revision = "0015_local_player_binding"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "local_user_profile",
        sa.Column("singleton", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.CheckConstraint("singleton = 1", name="ck_local_user_profile_singleton"),
        sa.CheckConstraint("revision > 0", name="ck_local_user_profile_revision"),
    )
    op.create_table(
        "local_world_profiles",
        sa.Column("world_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.world_id"]),
        sa.CheckConstraint("revision > 0", name="ck_local_world_profile_revision"),
    )


def downgrade():
    raise RuntimeError("local_profile_downgrade_requires_review")
