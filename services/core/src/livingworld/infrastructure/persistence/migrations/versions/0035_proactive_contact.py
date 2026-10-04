"""Add grounded outreach and read positions; preserve old offline unread flags."""

import sqlalchemy as sa
from alembic import op

revision = "0035_proactive_contact"
down_revision = "0034_shared_activities"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "proactive_contact_settings",
        sa.Column("world_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("player_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("enabled", sa.Boolean(), primary_key=False, nullable=False),
        sa.Column("revision", sa.Integer(), primary_key=False, nullable=False),
        sa.Column("interval_minutes", sa.Integer(), primary_key=False, nullable=False),
        sa.Column("next_at", sa.BigInteger(), primary_key=False, nullable=False),
        sa.Column("last_plan_id", sa.String(32), primary_key=False, nullable=True),
        sa.Column("state", sa.String(20), primary_key=False, nullable=False),
        sa.Column("error", sa.String(80), primary_key=False, nullable=True),
        sa.Column("consented_at", sa.String(32), primary_key=False, nullable=False),
        sa.ForeignKeyConstraint(
            ["world_id", "player_id"], ["players.world_id", "players.player_id"]
        ),
        sa.CheckConstraint(
            "revision >= 0 AND interval_minutes BETWEEN 15 AND 1440 AND next_at >= 0",
            name="ck_proactive_settings_bounds",
        ),
        sa.CheckConstraint(
            "state IN ('off','idle','writing','attention')", name="ck_proactive_settings_state"
        ),
    )
    op.create_table(
        "proactive_contact_episodes",
        sa.Column("world_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("episode_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("player_id", sa.String(32), primary_key=False, nullable=False),
        sa.Column("generation", sa.Integer(), primary_key=False, nullable=False),
        sa.Column("source_kind", sa.String(16), primary_key=False, nullable=False),
        sa.Column("source_id", sa.String(32), primary_key=False, nullable=False),
        sa.Column("plan_id", sa.String(32), primary_key=False, nullable=False),
        sa.Column("input_json", sa.Text(), primary_key=False, nullable=False),
        sa.Column("state", sa.String(20), primary_key=False, nullable=False),
        sa.Column("error", sa.String(80), primary_key=False, nullable=True),
        sa.Column("conversation_id", sa.String(32), primary_key=False, nullable=True),
        sa.Column("created_at_utc", sa.String(32), primary_key=False, nullable=False),
        sa.ForeignKeyConstraint(
            ["world_id", "player_id"], ["players.world_id", "players.player_id"]
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "conversation_id"],
            ["chat_conversations.world_id", "chat_conversations.conversation_id"],
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "plan_id"], ["director_plans.world_id", "director_plans.plan_id"]
        ),
        sa.UniqueConstraint(
            "world_id", "player_id", "source_kind", "source_id", name="uq_proactive_reason"
        ),
        sa.CheckConstraint(
            "source_kind IN ('routine','shared') AND generation >= 0", name="ck_proactive_source"
        ),
        sa.CheckConstraint(
            "state IN ('writing','delivered','cancelled','failed','interrupted')",
            name="ck_proactive_episode_state",
        ),
        sa.CheckConstraint(
            "json_valid(input_json) AND length(CAST(input_json AS BLOB)) <= 65536",
            name="ck_proactive_input",
        ),
    )
    op.create_index(
        "ix_proactive_episode_state",
        "proactive_contact_episodes",
        ["world_id", "player_id", "state"],
    )
    op.create_table(
        "chat_read_positions",
        sa.Column("world_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("conversation_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("player_id", sa.String(32), primary_key=False, nullable=False),
        sa.Column("position", sa.BigInteger(), primary_key=False, nullable=False),
        sa.ForeignKeyConstraint(
            ["world_id", "conversation_id"],
            ["chat_conversations.world_id", "chat_conversations.conversation_id"],
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "player_id"], ["players.world_id", "players.player_id"]
        ),
        sa.CheckConstraint("position >= 0", name="ck_chat_read_position"),
    )
    op.execute(
        sa.text("""
        INSERT INTO chat_read_positions (world_id, conversation_id, player_id, position)
        SELECT c.world_id, c.conversation_id, c.player_id,
          COALESCE((SELECT MIN(m.position) - 1 FROM offline_contact_episodes e
            JOIN chat_messages m ON m.world_id=e.world_id AND m.message_id=e.message_id
            WHERE e.world_id=c.world_id AND e.player_id=c.player_id
              AND e.conversation_id=c.conversation_id AND e.state='delivered'
              AND e.read_at_utc IS NULL),
            (SELECT COALESCE(MAX(m.position),0) FROM chat_messages m
              WHERE m.world_id=c.world_id AND m.conversation_id=c.conversation_id))
        FROM chat_conversations c
    """)
    )


def downgrade():
    op.drop_table("chat_read_positions")
    op.drop_table("proactive_contact_episodes")
    op.drop_table("proactive_contact_settings")
