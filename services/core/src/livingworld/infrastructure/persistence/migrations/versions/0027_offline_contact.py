"""Add real recovery receipts and additive story timestamps; preserve old transcripts."""

import sqlalchemy as sa
from alembic import op

revision = "0027_offline_contact"
down_revision = "0026_local_location_catalog"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "local_session_visibility",
        sa.Column("singleton", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("world_id", sa.String(32)),
        sa.Column("visible_until", sa.String(32), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.world_id"]),
        sa.CheckConstraint(
            "singleton = 1 AND sequence >= 0", name="ck_local_session_visibility_bounds"
        ),
    )
    op.add_column(
        "chat_turns", sa.Column("kind", sa.String(16), nullable=False, server_default="player")
    )
    op.add_column("chat_messages", sa.Column("story_sent_at_utc", sa.String(32)))
    op.create_table(
        "offline_contact_settings",
        sa.Column("singleton", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("world_id", sa.String(32), nullable=False),
        sa.Column("player_id", sa.String(32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("hours", sa.Integer(), nullable=False),
        sa.Column("consented_at", sa.String(32), nullable=False),
        sa.Column("last_online_at", sa.String(32)),
        sa.Column("input_json", sa.Text()),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("error", sa.String(80)),
        sa.Column("episode_id", sa.String(32)),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.world_id"]),
        sa.ForeignKeyConstraint(
            ["world_id", "player_id"], ["players.world_id", "players.player_id"]
        ),
        sa.CheckConstraint(
            "singleton = 1 AND revision > 0 AND hours BETWEEN 1 AND 168",
            name="ck_offline_contact_settings_bounds",
        ),
        sa.CheckConstraint(
            "input_json IS NULL OR (json_valid(input_json) "
            "AND length(CAST(input_json AS BLOB)) <= 65536)",
            name="ck_offline_contact_settings_input",
        ),
        sa.CheckConstraint(
            "state IN ('off','idle','waiting','planning','writing',"
            "'delivered','skipped','attention')",
            name="ck_offline_contact_settings_state",
        ),
    )
    op.create_table(
        "offline_contact_episodes",
        sa.Column("episode_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("world_id", sa.String(32), nullable=False),
        sa.Column("player_id", sa.String(32), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("reason_key", sa.String(64), nullable=False),
        sa.Column("offline_from", sa.String(32), nullable=False),
        sa.Column("offline_to", sa.String(32), nullable=False),
        sa.Column("input_json", sa.Text(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("error", sa.String(80)),
        sa.Column("conversation_id", sa.String(32)),
        sa.Column("character_id", sa.String(32)),
        sa.Column("purpose", sa.String(40)),
        sa.Column("story_sent_at_utc", sa.String(32)),
        sa.Column("created_at_utc", sa.String(32), nullable=False),
        sa.Column("message_id", sa.String(32)),
        sa.Column("read_at_utc", sa.String(32)),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.world_id"]),
        sa.ForeignKeyConstraint(
            ["world_id", "player_id"], ["players.world_id", "players.player_id"]
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "conversation_id"],
            ["chat_conversations.world_id", "chat_conversations.conversation_id"],
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "character_id"], ["characters.world_id", "characters.character_id"]
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "message_id"], ["chat_messages.world_id", "chat_messages.message_id"]
        ),
        sa.UniqueConstraint(
            "world_id", "player_id", "reason_key", name="uq_offline_contact_reason"
        ),
        sa.CheckConstraint(
            "generation > 0 AND length(reason_key) = 64 AND offline_to > offline_from",
            name="ck_offline_contact_episode_bounds",
        ),
        sa.CheckConstraint(
            "json_valid(input_json) AND length(CAST(input_json AS BLOB)) <= 65536",
            name="ck_offline_contact_episode_input",
        ),
        sa.CheckConstraint(
            "state IN ('queued','planning','writing','delivered','skipped','failed','interrupted')",
            name="ck_offline_contact_episode_state",
        ),
    )


def downgrade():
    op.drop_table("local_session_visibility")
    op.drop_table("offline_contact_episodes")
    op.drop_table("offline_contact_settings")
    op.drop_column("chat_messages", "story_sent_at_utc")
    op.drop_column("chat_turns", "kind")
