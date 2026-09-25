"""A durable one-time direct-reply claim without rewriting existing chat rows."""

import sqlalchemy as sa
from alembic import op

revision = "0020_chat_turn_dispatch"
down_revision = "0019_chat_messages"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "chat_turn_dispatches",
        sa.Column("world_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("turn_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("claimed_at_utc", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(
            ["world_id", "turn_id"], ["chat_turns.world_id", "chat_turns.turn_id"]
        ),
    )


def downgrade():
    raise RuntimeError("chat_turn_dispatch_downgrade_requires_review")
