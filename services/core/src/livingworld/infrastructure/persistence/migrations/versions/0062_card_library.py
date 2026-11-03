"""Global character-card templates and their independent world copies."""

import sqlalchemy as sa
from alembic import op

revision = "0062_card_library"
down_revision = "0061_chat_visuals"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "card_library",
        sa.Column("card_id", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("reviewed_hash", sa.String(64), nullable=False),
        sa.Column("draft_json", sa.Text(), nullable=False),
        sa.Column("design", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.CheckConstraint("revision > 0", name="ck_card_library_revision"),
    )
    op.create_table(
        "card_library_images",
        sa.Column("card_id", sa.String(32), primary_key=True),
        sa.Column("digest", sa.String(64), primary_key=True),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("media_type", sa.String(16), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["card_id"], ["card_library.card_id"], ondelete="CASCADE"),
        sa.CheckConstraint("size > 0 AND size <= 10485760", name="ck_card_library_image_size"),
        sa.CheckConstraint("width > 0 AND height > 0", name="ck_card_library_image_dimensions"),
        sa.CheckConstraint(
            "media_type IN ('image/jpeg','image/png','image/webp')",
            name="ck_card_library_image_media",
        ),
    )
    op.create_table(
        "card_library_worlds",
        sa.Column("card_id", sa.String(32), primary_key=True),
        sa.Column("world_id", sa.String(32), primary_key=True),
        sa.Column("import_id", sa.String(32), nullable=False),
        sa.Column("source_revision", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["card_id"], ["card_library.card_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.world_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["import_id"], ["world_content_imports.import_id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "uq_card_library_world_import", "card_library_worlds", ["import_id"], unique=True
    )


def downgrade():
    raise RuntimeError("card_library_downgrade_not_supported")
