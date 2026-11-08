"""Record new sticker additions without inventing timestamps for existing libraries."""

import sqlalchemy as sa
from alembic import op

from livingworld.infrastructure.persistence.types import UTCTimestampStorage

revision = "0050_sticker_library_freshness"
down_revision = "0049_local_model_limits"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "chat_sticker_entries", sa.Column("added_at_utc", UTCTimestampStorage(), nullable=True)
    )


def downgrade():
    op.drop_column("chat_sticker_entries", "added_at_utc")
