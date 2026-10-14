"""Separate local model receipts from remote daily admission without changing old receipts."""

import sqlalchemy as sa
from alembic import op

revision = "0049_local_model_limits"
down_revision = "0048_chat_media"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("speech_call_receipts", sa.Column("is_local", sa.Boolean(), nullable=True))
    op.add_column("chat_media_caption_calls", sa.Column("is_local", sa.Boolean(), nullable=True))


def downgrade():
    op.drop_column("chat_media_caption_calls", "is_local")
    op.drop_column("speech_call_receipts", "is_local")
