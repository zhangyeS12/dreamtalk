"""Add sourced durable chat recollections without changing evidence memories."""

import sqlalchemy as sa
from alembic import op

revision = "0029_long_chat_memory"
down_revision = "0028_world_event_journal"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "long_chat_memories",
        sa.Column("world_id", sa.String(32), nullable=False, primary_key=True),
        sa.Column("entry_id", sa.String(32), nullable=False, primary_key=True),
        sa.Column("player_id", sa.String(32), nullable=False),
        sa.Column("character_id", sa.String(32), nullable=False),
        sa.Column("conversation_id", sa.String(32), nullable=False),
        sa.Column("message_id", sa.String(32), nullable=False),
        sa.Column("source_sender_id", sa.String(32), nullable=False),
        sa.Column("source_kind", sa.String(12), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("topic", sa.String(60), nullable=False),
        sa.Column("content", sa.String(300), nullable=False),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("world_time", sa.BigInteger(), nullable=True),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("pinned", sa.Boolean(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("replaces", sa.String(32), nullable=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(
            ["world_id", "player_id"], ["players.world_id", "players.player_id"]
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "conversation_id", "character_id"],
            [
                "chat_participants.world_id",
                "chat_participants.conversation_id",
                "chat_participants.character_id",
            ],
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "message_id"], ["chat_messages.world_id", "chat_messages.message_id"]
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "replaces"], ["long_chat_memories.world_id", "long_chat_memories.entry_id"]
        ),
        sa.CheckConstraint(
            "kind IN ('identity','preference','promise','experience')", name="ck_long_memory_kind"
        ),
        sa.CheckConstraint("source_kind IN ('player','character')", name="ck_long_memory_source"),
        sa.CheckConstraint(
            "state IN ('active','forgotten','superseded')", name="ck_long_memory_state"
        ),
        sa.CheckConstraint("revision >= 0", name="ck_long_memory_revision"),
        sa.UniqueConstraint(
            "world_id",
            "player_id",
            "character_id",
            "fingerprint",
            name="uq_long_memory_fingerprint",
        ),
    )
    op.create_index(
        "ix_long_memory_owner_time",
        "long_chat_memories",
        ["world_id", "player_id", "character_id", "created_at", "entry_id"],
    )
    op.create_table(
        "long_chat_memory_settings",
        sa.Column("world_id", sa.String(32), nullable=False, primary_key=True),
        sa.Column("player_id", sa.String(32), nullable=False, primary_key=True),
        sa.Column("character_id", sa.String(32), nullable=False, primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["world_id", "player_id"], ["players.world_id", "players.player_id"]
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "character_id"], ["characters.world_id", "characters.character_id"]
        ),
        sa.CheckConstraint("revision >= 0", name="ck_long_memory_settings_revision"),
    )


def downgrade():
    op.drop_table("long_chat_memory_settings")
    op.drop_table("long_chat_memories")
