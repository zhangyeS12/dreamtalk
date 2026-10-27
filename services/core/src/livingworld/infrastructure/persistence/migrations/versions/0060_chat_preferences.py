"""Persist conversation pins and bounded message feedback."""

import sqlalchemy as sa
from alembic import op

revision = "0060_chat_preferences"
down_revision = "0059_character_evolution_provenance"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "chat_conversations",
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "chat_messages",
        sa.Column("feedback", sa.String(4), nullable=True),
    )
    with op.batch_alter_table("chat_messages") as batch:
        batch.create_check_constraint(
            "ck_chat_message_feedback", "feedback IS NULL OR feedback IN ('up','down')"
        )


def downgrade():
    raise RuntimeError("chat_preferences_downgrade_not_supported")
