"""Isolate editable library descriptions while retaining existing asset defaults."""

import sqlalchemy as sa
from alembic import op

revision = "0052_sticker_entry_description"
down_revision = "0051_media_frequency_kind"
branch_labels = None
depends_on = None


def upgrade():
    # Copy only existing asset descriptions; no chat bodies or image bytes are read.
    op.add_column("chat_sticker_entries", sa.Column("description", sa.Text(), nullable=True))
    op.execute(
        sa.text(
            "UPDATE chat_sticker_entries SET description = "
            "(SELECT description FROM chat_media_assets "
            "WHERE chat_media_assets.asset_id = chat_sticker_entries.asset_id)"
        )
    )


def downgrade():
    # Dropping independently edited descriptions would silently lose user data.
    raise RuntimeError("sticker_description_downgrade_not_supported")
