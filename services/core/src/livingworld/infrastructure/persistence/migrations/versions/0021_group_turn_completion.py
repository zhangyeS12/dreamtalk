"""Record terminal group-turn completion without rewriting existing chat history."""

import sqlalchemy as sa
from alembic import op

revision = "0021_group_turn_completion"
down_revision = "0020_chat_turn_dispatch"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "chat_turn_dispatches",
        sa.Column("completed_at_utc", sa.String(32), nullable=True),
    )


def downgrade():
    raise RuntimeError("group_turn_completion_downgrade_requires_review")
