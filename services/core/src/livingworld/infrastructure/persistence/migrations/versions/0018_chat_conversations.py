"""Durable world-scoped chat identities; messages and generation follow later."""

import sqlalchemy as sa
from alembic import op

revision = "0018_chat_conversations"
down_revision = "0017_world_content_imports"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "chat_conversations",
        sa.Column("world_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("conversation_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("player_id", sa.String(32), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("direct_root_import_id", sa.String(32), nullable=True),
        sa.Column("created_at_utc", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(
            ["world_id", "player_id"], ["players.world_id", "players.player_id"]
        ),
        sa.ForeignKeyConstraint(["direct_root_import_id"], ["world_content_imports.import_id"]),
        sa.CheckConstraint(
            "(kind = 'direct' AND direct_root_import_id IS NOT NULL) OR "
            "(kind = 'group' AND direct_root_import_id IS NULL)",
            name="ck_chat_conversation_kind",
        ),
    )
    op.create_index(
        "ix_chat_conversation_player",
        "chat_conversations",
        ["world_id", "player_id", "created_at_utc"],
    )
    op.create_index(
        "uq_chat_direct_player_contact",
        "chat_conversations",
        ["world_id", "player_id", "direct_root_import_id"],
        unique=True,
        sqlite_where=sa.text("kind = 'direct'"),
    )
    op.create_table(
        "chat_participants",
        sa.Column("world_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("conversation_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("character_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("root_import_id", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(
            ["world_id", "conversation_id"],
            ["chat_conversations.world_id", "chat_conversations.conversation_id"],
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "character_id"], ["characters.world_id", "characters.character_id"]
        ),
        sa.ForeignKeyConstraint(["root_import_id"], ["world_content_imports.import_id"]),
        sa.UniqueConstraint(
            "world_id", "conversation_id", "root_import_id", name="uq_chat_participant_contact"
        ),
    )


def downgrade():
    raise RuntimeError("chat_conversation_downgrade_requires_review")
