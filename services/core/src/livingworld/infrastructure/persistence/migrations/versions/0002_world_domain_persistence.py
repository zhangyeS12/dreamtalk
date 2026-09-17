# ruff: noqa: E501
"""world domain persistence

Revision ID: 0002_world_domain_persistence
Revises: 0001_legacy_runtime_foundation
Create Date: 2026-09-16 15:03:55.572876

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_world_domain_persistence"
down_revision: str | Sequence[str] | None = "0001_legacy_runtime_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Reviewed native SQLite schema: constraints, world-scoped keys, and indexes.
    op.create_table(
        "worlds",
        sa.Column("world_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.CheckConstraint("revision >= 0", name="ck_worlds_revision"),
        sa.PrimaryKeyConstraint("world_id"),
    )
    op.create_table(
        "characters",
        sa.Column("world_id", sa.String(length=32), nullable=False),
        sa.Column("character_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.CheckConstraint("revision >= 0", name="ck_characters_revision"),
        sa.ForeignKeyConstraint(
            ["world_id"],
            ["worlds.world_id"],
        ),
        sa.PrimaryKeyConstraint("world_id", "character_id"),
    )
    op.create_table(
        "locations",
        sa.Column("world_id", sa.String(length=32), nullable=False),
        sa.Column("location_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.CheckConstraint("revision >= 0", name="ck_locations_revision"),
        sa.ForeignKeyConstraint(
            ["world_id"],
            ["worlds.world_id"],
        ),
        sa.PrimaryKeyConstraint("world_id", "location_id"),
    )
    op.create_table(
        "players",
        sa.Column("world_id", sa.String(length=32), nullable=False),
        sa.Column("player_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.CheckConstraint("revision >= 0", name="ck_players_revision"),
        sa.ForeignKeyConstraint(
            ["world_id"],
            ["worlds.world_id"],
        ),
        sa.PrimaryKeyConstraint("world_id", "player_id"),
    )
    op.create_table(
        "world_clocks",
        sa.Column("world_id", sa.String(length=32), nullable=False),
        sa.Column("logical_time", sa.BigInteger(), nullable=False),
        sa.Column("observed_wall_time_utc", sa.String(length=32), nullable=False),
        sa.Column("time_scale", sa.Text(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.CheckConstraint("state IN ('running', 'paused')", name="ck_world_clocks_state"),
        sa.CheckConstraint(
            "typeof(logical_time) = 'integer'", name="ck_world_clock_logical_time_type"
        ),
        sa.CheckConstraint("revision >= 0", name="ck_world_clocks_revision"),
        sa.ForeignKeyConstraint(
            ["world_id"],
            ["worlds.world_id"],
        ),
        sa.PrimaryKeyConstraint("world_id"),
    )
    op.create_table(
        "world_events",
        sa.Column("world_id", sa.String(length=32), nullable=False),
        sa.Column("event_id", sa.String(length=32), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("occurred_at", sa.BigInteger(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("payload_version", sa.Integer(), nullable=False),
        sa.Column("causation_event_id", sa.String(length=32), nullable=True),
        sa.Column("causation_request_id", sa.String(length=32), nullable=True),
        sa.Column("correlation_id", sa.String(length=32), nullable=True),
        sa.Column("idempotency_key", sa.String(), nullable=True),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.CheckConstraint("typeof(occurred_at) = 'integer'", name="ck_world_event_occurred_type"),
        sa.CheckConstraint(
            "causation_event_id IS NULL OR causation_request_id IS NULL",
            name="ck_world_event_one_causation",
        ),
        sa.CheckConstraint("payload_version >= 1", name="ck_world_event_payload_version"),
        sa.ForeignKeyConstraint(
            ["world_id", "causation_event_id"],
            ["world_events.world_id", "world_events.event_id"],
        ),
        sa.ForeignKeyConstraint(
            ["world_id"],
            ["worlds.world_id"],
        ),
        sa.PrimaryKeyConstraint("world_id", "event_id"),
        sa.UniqueConstraint("world_id", "idempotency_key", name="uq_world_event_idempotency"),
    )
    op.create_index(
        "ix_world_events_occurred",
        "world_events",
        ["world_id", "occurred_at", "event_id"],
        unique=False,
    )
    # The event ledger is append-only even for direct SQL callers.
    op.execute(
        "CREATE TRIGGER world_events_no_update BEFORE UPDATE ON world_events "
        "BEGIN SELECT RAISE(ABORT, 'world_event_immutable'); END"
    )
    op.execute(
        "CREATE TRIGGER world_events_no_delete BEFORE DELETE ON world_events "
        "BEGIN SELECT RAISE(ABORT, 'world_event_immutable'); END"
    )
    op.create_table(
        "character_states",
        sa.Column("world_id", sa.String(length=32), nullable=False),
        sa.Column("character_id", sa.String(length=32), nullable=False),
        sa.Column("location_id", sa.String(length=32), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.CheckConstraint("revision >= 0", name="ck_character_states_revision"),
        sa.ForeignKeyConstraint(
            ["world_id", "character_id"],
            ["characters.world_id", "characters.character_id"],
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "location_id"],
            ["locations.world_id", "locations.location_id"],
        ),
        sa.ForeignKeyConstraint(
            ["world_id"],
            ["worlds.world_id"],
        ),
        sa.PrimaryKeyConstraint("world_id", "character_id"),
    )
    op.create_table(
        "knowledge_assertions",
        sa.Column("world_id", sa.String(length=32), nullable=False),
        sa.Column("assertion_id", sa.String(length=32), nullable=False),
        sa.Column("scope", sa.String(length=24), nullable=False),
        sa.Column("owner_character_id", sa.String(length=32), nullable=True),
        sa.Column("owner_player_id", sa.String(length=32), nullable=True),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("predicate", sa.String(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("epistemic_status", sa.String(), nullable=False),
        sa.Column("confidence", sa.Text(), nullable=True),
        sa.Column("valid_from", sa.BigInteger(), nullable=False),
        sa.Column("valid_to", sa.BigInteger(), nullable=True),
        sa.Column("provenance_event_id", sa.String(length=32), nullable=True),
        sa.Column("source_assertion_id", sa.String(length=32), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "(scope = 'truth' AND owner_character_id IS NULL AND owner_player_id IS NULL) OR (scope = 'character_belief' AND owner_character_id IS NOT NULL AND owner_player_id IS NULL) OR (scope = 'player_knowledge' AND owner_player_id IS NOT NULL AND owner_character_id IS NULL)",
            name="ck_knowledge_owner",
        ),
        sa.CheckConstraint(
            "typeof(valid_from) = 'integer' AND (valid_to IS NULL OR typeof(valid_to) = 'integer')",
            name="ck_knowledge_world_time_type",
        ),
        sa.CheckConstraint("revision >= 0", name="ck_knowledge_assertions_revision"),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from", name="ck_knowledge_validity"
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "owner_character_id"],
            ["characters.world_id", "characters.character_id"],
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "owner_player_id"],
            ["players.world_id", "players.player_id"],
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "provenance_event_id"],
            ["world_events.world_id", "world_events.event_id"],
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "source_assertion_id"],
            ["knowledge_assertions.world_id", "knowledge_assertions.assertion_id"],
        ),
        sa.ForeignKeyConstraint(
            ["world_id"],
            ["worlds.world_id"],
        ),
        sa.PrimaryKeyConstraint("world_id", "assertion_id"),
    )
    op.create_index(
        "ix_knowledge_character_owner",
        "knowledge_assertions",
        ["world_id", "scope", "owner_character_id"],
        unique=False,
    )
    op.create_index(
        "ix_knowledge_player_owner",
        "knowledge_assertions",
        ["world_id", "scope", "owner_player_id"],
        unique=False,
    )
    op.create_table(
        "location_connections",
        sa.Column("world_id", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.String(length=32), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.CheckConstraint("revision >= 0", name="ck_location_connections_revision"),
        sa.ForeignKeyConstraint(
            ["world_id", "source_id"],
            ["locations.world_id", "locations.location_id"],
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "target_id"],
            ["locations.world_id", "locations.location_id"],
        ),
        sa.ForeignKeyConstraint(
            ["world_id"],
            ["worlds.world_id"],
        ),
        sa.PrimaryKeyConstraint("world_id", "source_id", "target_id"),
    )
    op.create_table(
        "player_presences",
        sa.Column("world_id", sa.String(length=32), nullable=False),
        sa.Column("player_id", sa.String(length=32), nullable=False),
        sa.Column("location_id", sa.String(length=32), nullable=False),
        sa.Column("activity", sa.String(length=16), nullable=False),
        sa.Column("availability", sa.String(length=16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.CheckConstraint("activity IN ('active', 'inactive')", name="ck_presence_activity"),
        sa.CheckConstraint(
            "availability IN ('busy', 'available')", name="ck_presence_availability"
        ),
        sa.CheckConstraint("revision >= 0", name="ck_player_presences_revision"),
        sa.ForeignKeyConstraint(
            ["world_id", "location_id"],
            ["locations.world_id", "locations.location_id"],
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "player_id"],
            ["players.world_id", "players.player_id"],
        ),
        sa.ForeignKeyConstraint(
            ["world_id"],
            ["worlds.world_id"],
        ),
        sa.PrimaryKeyConstraint("world_id", "player_id"),
    )
    op.create_table(
        "relationships",
        sa.Column("world_id", sa.String(length=32), nullable=False),
        sa.Column("source_kind", sa.String(length=16), nullable=False),
        sa.Column("source_id", sa.String(length=32), nullable=False),
        sa.Column("target_kind", sa.String(length=16), nullable=False),
        sa.Column("target_id", sa.String(length=32), nullable=False),
        sa.Column("source_character_id", sa.String(length=32), nullable=True),
        sa.Column("source_player_id", sa.String(length=32), nullable=True),
        sa.Column("target_character_id", sa.String(length=32), nullable=True),
        sa.Column("target_player_id", sa.String(length=32), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "(source_kind = 'character' AND source_character_id IS NOT NULL AND source_character_id = source_id AND source_player_id IS NULL) OR (source_kind = 'player' AND source_player_id IS NOT NULL AND source_player_id = source_id AND source_character_id IS NULL)",
            name="ck_relationship_source",
        ),
        sa.CheckConstraint(
            "(target_kind = 'character' AND target_character_id IS NOT NULL AND target_character_id = target_id AND target_player_id IS NULL) OR (target_kind = 'player' AND target_player_id IS NOT NULL AND target_player_id = target_id AND target_character_id IS NULL)",
            name="ck_relationship_target",
        ),
        sa.CheckConstraint("revision >= 0", name="ck_relationships_revision"),
        sa.ForeignKeyConstraint(
            ["world_id", "source_character_id"],
            ["characters.world_id", "characters.character_id"],
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "source_player_id"],
            ["players.world_id", "players.player_id"],
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "target_character_id"],
            ["characters.world_id", "characters.character_id"],
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "target_player_id"],
            ["players.world_id", "players.player_id"],
        ),
        sa.ForeignKeyConstraint(
            ["world_id"],
            ["worlds.world_id"],
        ),
        sa.PrimaryKeyConstraint("world_id", "source_kind", "source_id", "target_kind", "target_id"),
    )
    op.create_table(
        "command_receipts",
        sa.Column("world_id", sa.String(length=32), nullable=False),
        sa.Column("request_id", sa.String(length=32), nullable=False),
        sa.Column("command_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("completed_at", sa.String(length=32), nullable=True),
        sa.Column("result_kind", sa.String(length=24), nullable=True),
        sa.Column("result_id", sa.String(length=32), nullable=True),
        sa.Column("result_event_id", sa.String(length=32), nullable=True),
        sa.Column("result_assertion_id", sa.String(length=32), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "(result_kind IS NULL AND result_id IS NULL AND result_event_id IS NULL AND result_assertion_id IS NULL) OR (result_kind IS NOT NULL AND result_kind = 'event' AND result_id IS NOT NULL AND result_event_id IS NOT NULL AND result_event_id = result_id AND result_assertion_id IS NULL) OR (result_kind IS NOT NULL AND result_kind = 'assertion' AND result_id IS NOT NULL AND result_assertion_id IS NOT NULL AND result_assertion_id = result_id AND result_event_id IS NULL)",
            name="ck_command_receipt_result",
        ),
        sa.CheckConstraint(
            "completed_at IS NULL OR completed_at >= created_at",
            name="ck_command_receipt_completion",
        ),
        sa.CheckConstraint("revision >= 0", name="ck_command_receipts_revision"),
        sa.ForeignKeyConstraint(
            ["world_id", "result_assertion_id"],
            ["knowledge_assertions.world_id", "knowledge_assertions.assertion_id"],
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "result_event_id"],
            ["world_events.world_id", "world_events.event_id"],
        ),
        sa.ForeignKeyConstraint(
            ["world_id"],
            ["worlds.world_id"],
        ),
        sa.PrimaryKeyConstraint("world_id", "request_id"),
    )
    op.create_table(
        "observations",
        sa.Column("world_id", sa.String(length=32), nullable=False),
        sa.Column("principal_kind", sa.String(length=16), nullable=False),
        sa.Column("principal_id", sa.String(length=32), nullable=False),
        sa.Column("target_kind", sa.String(length=24), nullable=False),
        sa.Column("target_id", sa.String(length=32), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("observed_at", sa.BigInteger(), nullable=False),
        sa.Column("principal_character_id", sa.String(length=32), nullable=True),
        sa.Column("principal_player_id", sa.String(length=32), nullable=True),
        sa.Column("target_event_id", sa.String(length=32), nullable=True),
        sa.Column("target_assertion_id", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.String(length=32), nullable=True),
        sa.CheckConstraint(
            "(principal_kind = 'character' AND principal_character_id IS NOT NULL AND principal_character_id = principal_id AND principal_player_id IS NULL) OR (principal_kind = 'player' AND principal_player_id IS NOT NULL AND principal_player_id = principal_id AND principal_character_id IS NULL)",
            name="ck_observation_principal",
        ),
        sa.CheckConstraint(
            "(target_kind = 'event' AND target_event_id IS NOT NULL AND target_event_id = target_id AND target_assertion_id IS NULL) OR (target_kind = 'assertion' AND target_assertion_id IS NOT NULL AND target_assertion_id = target_id AND target_event_id IS NULL)",
            name="ck_observation_target",
        ),
        sa.CheckConstraint(
            "channel IN ('witnessed', 'told', 'message', 'news', 'document', 'inferred')",
            name="ck_observation_channel",
        ),
        sa.CheckConstraint(
            "typeof(observed_at) = 'integer'", name="ck_observation_world_time_type"
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "principal_character_id"],
            ["characters.world_id", "characters.character_id"],
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "principal_player_id"],
            ["players.world_id", "players.player_id"],
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "target_assertion_id"],
            ["knowledge_assertions.world_id", "knowledge_assertions.assertion_id"],
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "target_event_id"],
            ["world_events.world_id", "world_events.event_id"],
        ),
        sa.ForeignKeyConstraint(
            ["world_id"],
            ["worlds.world_id"],
        ),
        sa.PrimaryKeyConstraint(
            "world_id",
            "principal_kind",
            "principal_id",
            "target_kind",
            "target_id",
            "channel",
            "observed_at",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TRIGGER IF EXISTS world_events_no_delete")
    op.execute("DROP TRIGGER IF EXISTS world_events_no_update")
    # Reviewed native SQLite schema: constraints, world-scoped keys, and indexes.
    op.drop_table("observations")
    op.drop_table("command_receipts")
    op.drop_table("relationships")
    op.drop_table("player_presences")
    op.drop_table("location_connections")
    op.drop_index("ix_knowledge_player_owner", table_name="knowledge_assertions")
    op.drop_index("ix_knowledge_character_owner", table_name="knowledge_assertions")
    op.drop_table("knowledge_assertions")
    op.drop_table("character_states")
    op.drop_index("ix_world_events_occurred", table_name="world_events")
    op.drop_table("world_events")
    op.drop_table("world_clocks")
    op.drop_table("players")
    op.drop_table("locations")
    op.drop_table("characters")
    op.drop_table("worlds")
