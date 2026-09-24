"""Durable player-send receipt and ordered transcript; no generation dispatch."""

import sqlalchemy as sa
from alembic import op

revision = "0019_chat_messages"
down_revision = "0018_chat_conversations"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "chat_turns",
        sa.Column("world_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("turn_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("conversation_id", sa.String(32), nullable=False),
        sa.Column("request_id", sa.String(32), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("token_ceiling", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at_utc", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(
            ["world_id", "conversation_id"],
            ["chat_conversations.world_id", "chat_conversations.conversation_id"],
        ),
        sa.CheckConstraint("length(fingerprint) = 64", name="ck_chat_turn_fingerprint"),
        sa.CheckConstraint("token_ceiling > 0", name="ck_chat_turn_token_ceiling"),
        sa.CheckConstraint("status = 'pending'", name="ck_chat_turn_status"),
    )
    op.create_index("uq_chat_turn_request", "chat_turns", ["request_id"], unique=True)
    op.create_table(
        "chat_messages",
        sa.Column("world_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("message_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("conversation_id", sa.String(32), nullable=False),
        sa.Column("turn_id", sa.String(32), nullable=False),
        sa.Column("position", sa.BigInteger(), nullable=False),
        sa.Column("sender_player_id", sa.String(32), nullable=True),
        sa.Column("sender_character_id", sa.String(32), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at_utc", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(
            ["world_id", "conversation_id"],
            ["chat_conversations.world_id", "chat_conversations.conversation_id"],
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "turn_id"], ["chat_turns.world_id", "chat_turns.turn_id"]
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "sender_player_id"], ["players.world_id", "players.player_id"]
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "sender_character_id"],
            ["characters.world_id", "characters.character_id"],
        ),
        sa.UniqueConstraint(
            "world_id", "conversation_id", "position", name="uq_chat_message_position"
        ),
        sa.CheckConstraint("position > 0", name="ck_chat_message_position"),
        sa.CheckConstraint("length(trim(text)) > 0", name="ck_chat_message_text"),
        sa.CheckConstraint(
            "(sender_player_id IS NOT NULL AND sender_character_id IS NULL) OR "
            "(sender_player_id IS NULL AND sender_character_id IS NOT NULL)",
            name="ck_chat_message_sender",
        ),
    )
    op.create_index(
        "uq_chat_turn_player_message",
        "chat_messages",
        ["world_id", "turn_id"],
        unique=True,
        sqlite_where=sa.text("sender_player_id IS NOT NULL"),
    )


def downgrade():
    raise RuntimeError("chat_message_downgrade_requires_review")
