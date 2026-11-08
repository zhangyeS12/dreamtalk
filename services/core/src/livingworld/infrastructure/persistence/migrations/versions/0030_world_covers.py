"""Add local book presentation and world-scoped immutable image bindings."""

import sqlalchemy as sa
from alembic import op

revision = "0030_world_covers"
down_revision = "0029_long_chat_memory"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "world_covers",
        sa.Column("world_id", sa.String(32), sa.ForeignKey("worlds.world_id"), primary_key=True),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.CheckConstraint("revision > 0", name="ck_world_cover_revision"),
    )
    op.create_table(
        "world_cover_images",
        sa.Column("world_id", sa.String(32), sa.ForeignKey("worlds.world_id"), primary_key=True),
        sa.Column("digest", sa.String(64), primary_key=True),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("media_type", sa.String(16), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.CheckConstraint("size > 0 AND size <= 10485760", name="ck_world_cover_image_size"),
        sa.CheckConstraint("width > 0 AND height > 0", name="ck_world_cover_image_dimensions"),
        sa.CheckConstraint(
            "media_type IN ('image/jpeg','image/png','image/webp')",
            name="ck_world_cover_image_media",
        ),
    )


def downgrade():
    op.drop_table("world_cover_images")
    op.drop_table("world_covers")
