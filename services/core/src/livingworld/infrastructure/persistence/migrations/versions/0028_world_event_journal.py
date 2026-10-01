"""Add a player journal and finite public announcement pool; preserve existing data."""

import sqlalchemy as sa
from alembic import op

revision = "0028_world_event_journal"
down_revision = "0027_offline_contact"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "chat_story_entries",
        sa.Column("world_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("entry_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("player_id", sa.String(32), nullable=False),
        sa.Column("character_id", sa.String(32), nullable=False),
        sa.Column("conversation_id", sa.String(32), nullable=False),
        sa.Column("message_id", sa.String(32), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("title", sa.String(80), nullable=False),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("time_text", sa.String(100), nullable=True),
        sa.Column("source_event_id", sa.String(32), nullable=True),
        sa.Column("updates_entry_id", sa.String(32), nullable=True),
        sa.Column("learned_world_time", sa.BigInteger(), nullable=True),
        sa.Column("learned_at", sa.String(32), nullable=False),
        sa.Column("hidden", sa.Boolean(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("correction", sa.String(500), nullable=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(
            ["world_id", "player_id"], ["players.world_id", "players.player_id"]
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "character_id"], ["characters.world_id", "characters.character_id"]
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "conversation_id"],
            ["chat_conversations.world_id", "chat_conversations.conversation_id"],
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "message_id"], ["chat_messages.world_id", "chat_messages.message_id"]
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "source_event_id"], ["world_events.world_id", "world_events.event_id"]
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "updates_entry_id"],
            ["chat_story_entries.world_id", "chat_story_entries.entry_id"],
        ),
        sa.CheckConstraint(
            "kind IN ('activity','plan','rumor','invitation','change')", name="ck_chat_story_kind"
        ),
        sa.UniqueConstraint(
            "world_id", "player_id", "fingerprint", name="uq_chat_story_fingerprint"
        ),
    )
    op.create_index(
        "ix_chat_story_owner_time",
        "chat_story_entries",
        ["world_id", "player_id", "learned_at", "entry_id"],
    )
    op.create_table(
        "world_news_settings",
        sa.Column(
            "world_id",
            sa.String(32),
            sa.ForeignKey("worlds.world_id"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("player_id", sa.String(32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("consented_at", sa.String(32), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("error", sa.String(80), nullable=True),
        sa.Column("next_publish_at", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(
            ["world_id", "player_id"], ["players.world_id", "players.player_id"]
        ),
        sa.CheckConstraint("revision >= 0", name="ck_world_news_revision"),
        sa.CheckConstraint(
            "state IN ('off','idle','generating','ready','attention')", name="ck_world_news_state"
        ),
    )
    op.create_table(
        "world_news_batches",
        sa.Column("world_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("batch_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("player_id", sa.String(32), nullable=False),
        sa.Column("invocation_id", sa.String(32), nullable=False, unique=True),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("input_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("replenished", sa.Boolean(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["world_id", "player_id"], ["players.world_id", "players.player_id"]
        ),
        sa.CheckConstraint(
            "state IN ('queued','dispatched','ready','failed','interrupted','cancelled')",
            name="ck_world_news_batch_state",
        ),
        sa.CheckConstraint("total >= 0 AND total <= 20", name="ck_world_news_batch_total"),
    )
    op.create_index(
        "ix_world_news_batch_world_time",
        "world_news_batches",
        ["world_id", "created_at", "batch_id"],
    )
    op.create_table(
        "world_news_candidates",
        sa.Column("world_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("entry_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("batch_id", sa.String(32), nullable=False),
        sa.Column("title", sa.String(80), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("time_text", sa.String(100), nullable=True),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("available_from", sa.BigInteger(), nullable=False),
        sa.Column("expires_at", sa.BigInteger(), nullable=False),
        sa.Column("shuffle_key", sa.String(64), nullable=False),
        sa.Column("event_id", sa.String(32), nullable=True),
        sa.Column("published_at", sa.String(32), nullable=True),
        sa.Column("occurred_at", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(
            ["world_id", "batch_id"], ["world_news_batches.world_id", "world_news_batches.batch_id"]
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "event_id"], ["world_events.world_id", "world_events.event_id"]
        ),
        sa.CheckConstraint("expires_at > available_from", name="ck_world_news_candidate_time"),
        sa.CheckConstraint(
            "state IN ('pending','published','cancelled')", name="ck_world_news_candidate_state"
        ),
    )
    op.create_index(
        "ix_world_news_candidate_queue",
        "world_news_candidates",
        ["world_id", "state", "shuffle_key"],
    )
    op.create_table(
        "world_news_marks",
        sa.Column("world_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("player_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("entry_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["world_id", "player_id"], ["players.world_id", "players.player_id"]
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "entry_id"],
            ["world_news_candidates.world_id", "world_news_candidates.entry_id"],
        ),
        sa.CheckConstraint(
            "state IN ('pending','experienced','skipped')", name="ck_world_news_mark_state"
        ),
        sa.CheckConstraint("revision >= 0", name="ck_world_news_mark_revision"),
    )


def downgrade():
    op.drop_table("world_news_marks")
    op.drop_table("world_news_candidates")
    op.drop_table("world_news_batches")
    op.drop_table("world_news_settings")
    op.drop_table("chat_story_entries")
