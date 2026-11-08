"""Persist bounded player-visible context selection diagnostics."""

import sqlalchemy as sa
from alembic import op

revision = "0032_chat_context_reports"
down_revision = "0031_chat_reply_recovery"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("chat_reply_executions", sa.Column("context_reports", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("chat_reply_executions", "context_reports")
