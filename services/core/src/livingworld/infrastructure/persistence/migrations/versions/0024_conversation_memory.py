"""Add reviewed, owner-scoped conversation memory without changing episodic evidence."""

import sqlalchemy as sa
from alembic import op

revision = "0024_conversation_memory"
down_revision = "0023_content_builder_jobs"
branch_labels = None
depends_on = None


def _ownership():
    return (
        sa.ForeignKeyConstraint(
            ["world_id", "conversation_id"],
            ["chat_conversations.world_id", "chat_conversations.conversation_id"],
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "player_id"], ["players.world_id", "players.player_id"]
        ),
    )


def upgrade():
    op.create_table(
        "conversation_memory_revisions",
        sa.Column("world_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("conversation_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("revision", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("base_revision", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.String(32), nullable=False),
        sa.Column("through_position", sa.BigInteger(), nullable=False),
        sa.Column("source_ids", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("user_edited", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        *_ownership(),
        sa.CheckConstraint(
            "revision > 0 AND base_revision >= 0 AND base_revision < revision "
            "AND through_position > 0",
            name="ck_conversation_memory_revision",
        ),
        sa.CheckConstraint(
            "json_valid(source_ids) AND json_type(source_ids) = 'array' "
            "AND json_array_length(source_ids) <= 32",
            name="ck_conversation_memory_sources",
        ),
        sa.CheckConstraint(
            "length(trim(content)) > 0 AND length(CAST(content AS BLOB)) <= 8192",
            name="ck_conversation_memory_content",
        ),
    )
    op.create_table(
        "conversation_memory_drafts",
        sa.Column("draft_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("world_id", sa.String(32), nullable=False),
        sa.Column("conversation_id", sa.String(32), nullable=False),
        sa.Column("player_id", sa.String(32), nullable=False),
        sa.Column("base_revision", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("through_position", sa.BigInteger(), nullable=False),
        sa.Column("source_ids", sa.Text(), nullable=False),
        sa.Column("content", sa.Text()),
        sa.Column("user_edited", sa.Boolean(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("reviewed_hash", sa.String(64)),
        sa.Column("committed_revision", sa.Integer()),
        sa.Column("error", sa.String(80)),
        sa.Column("created_at", sa.String(32), nullable=False),
        *_ownership(),
        sa.CheckConstraint(
            "base_revision >= 0 AND through_position > 0",
            name="ck_conversation_memory_draft_position",
        ),
        sa.CheckConstraint(
            "mode IN ('summarize','correct')", name="ck_conversation_memory_draft_mode"
        ),
        sa.CheckConstraint(
            "state IN ('generating','ready','previewed','committed','failed','interrupted')",
            name="ck_conversation_memory_draft_state",
        ),
        sa.CheckConstraint(
            "json_valid(source_ids) AND json_type(source_ids) = 'array' "
            "AND json_array_length(source_ids) <= 32",
            name="ck_conversation_memory_draft_sources",
        ),
        sa.CheckConstraint(
            "content IS NULL OR (length(trim(content)) > 0 "
            "AND length(CAST(content AS BLOB)) <= 8192)",
            name="ck_conversation_memory_draft_content",
        ),
        sa.CheckConstraint(
            "reviewed_hash IS NULL OR length(reviewed_hash) = 64",
            name="ck_conversation_memory_draft_hash",
        ),
    )

    op.create_index(
        "ix_conversation_memory_draft_owner",
        "conversation_memory_drafts",
        ["world_id", "conversation_id", "player_id", "created_at", "draft_id"],
    )


def downgrade():
    op.drop_table("conversation_memory_drafts")
    op.drop_table("conversation_memory_revisions")
