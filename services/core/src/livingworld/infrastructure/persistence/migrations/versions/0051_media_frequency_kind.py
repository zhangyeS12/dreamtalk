"""Separate image intervals from unlimited stickers without rewriting old receipts."""

import sqlalchemy as sa
from alembic import op

revision = "0051_media_frequency_kind"
down_revision = "0050_sticker_library_freshness"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("chat_media_attempts", sa.Column("sent_kind", sa.String(16), nullable=True))


def downgrade():
    op.drop_column("chat_media_attempts", "sent_kind")
