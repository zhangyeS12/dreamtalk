"""Authored foil packets and ordered references to the independent card library."""

import sqlalchemy as sa
from alembic import op

revision = "0063_card_packs"
down_revision = "0062_card_library"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "card_packs",
        sa.Column("pack_id", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("subtitle", sa.String(120), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("design", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.CheckConstraint("revision > 0", name="ck_card_pack_revision"),
    )
    op.create_table(
        "card_pack_members",
        sa.Column("pack_id", sa.String(32), primary_key=True),
        sa.Column("card_id", sa.String(32), primary_key=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["pack_id"], ["card_packs.pack_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["card_id"], ["card_library.card_id"], ondelete="CASCADE"),
        sa.CheckConstraint("position >= 0", name="ck_card_pack_member_position"),
    )
    op.create_index("ix_card_pack_member_order", "card_pack_members", ["pack_id", "position"])
    op.create_table(
        "card_pack_images",
        sa.Column("pack_id", sa.String(32), primary_key=True),
        sa.Column("digest", sa.String(64), primary_key=True),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("media_type", sa.String(16), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["pack_id"], ["card_packs.pack_id"], ondelete="CASCADE"),
        sa.CheckConstraint("size > 0 AND size <= 10485760", name="ck_card_pack_image_size"),
        sa.CheckConstraint("width > 0 AND height > 0", name="ck_card_pack_image_dimensions"),
        sa.CheckConstraint(
            "media_type IN ('image/jpeg','image/png','image/webp')", name="ck_card_pack_image_media"
        ),
    )


def downgrade():
    op.drop_table("card_pack_images")
    op.drop_index("ix_card_pack_member_order", table_name="card_pack_members")
    op.drop_table("card_pack_members")
    op.drop_table("card_packs")
