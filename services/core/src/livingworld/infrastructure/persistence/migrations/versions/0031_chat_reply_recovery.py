"""Add explicit reply attempts and terminal local generation states."""

import sqlalchemy as sa
from alembic import op

revision = "0031_chat_reply_recovery"
down_revision = "0030_world_covers"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "chat_reply_executions",
        sa.Column("world_id", sa.String(32), primary_key=True),
        sa.Column("turn_id", sa.String(32), primary_key=True),
        sa.Column("state", sa.String(16), nullable=False),
        sa.ForeignKeyConstraint(
            ["world_id", "turn_id"], ["chat_turns.world_id", "chat_turns.turn_id"]
        ),
        sa.CheckConstraint(
            "state IN ('running','completed','failed','unknown','interrupted')",
            name="ck_chat_reply_execution_state",
        ),
    )
    op.create_table(
        "chat_reply_recoveries",
        sa.Column("world_id", sa.String(32), primary_key=True),
        sa.Column("turn_id", sa.String(32), primary_key=True),
        sa.Column("source_turn_id", sa.String(32), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["world_id", "turn_id"], ["chat_turns.world_id", "chat_turns.turn_id"]
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "source_turn_id"], ["chat_turns.world_id", "chat_turns.turn_id"]
        ),
        sa.UniqueConstraint(
            "world_id", "source_turn_id", "ordinal", name="uq_chat_reply_recovery_order"
        ),
        sa.CheckConstraint("ordinal > 0", name="ck_chat_reply_recovery_order"),
        sa.CheckConstraint("turn_id != source_turn_id", name="ck_chat_reply_recovery_source"),
    )


def downgrade():
    op.drop_table("chat_reply_recoveries")
    op.drop_table("chat_reply_executions")
