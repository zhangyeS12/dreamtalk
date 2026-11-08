"""Preserve classification fallback provenance; old messages remain unknown."""

import sqlalchemy as sa
from alembic import op

revision = "0066_chat_privacy_fallback"
down_revision = "0065_chat_privacy"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("chat_messages", sa.Column("privacy_fallback", sa.Boolean(), nullable=True))


def downgrade():
    raise RuntimeError("chat_privacy_fallback_downgrade_not_supported")
