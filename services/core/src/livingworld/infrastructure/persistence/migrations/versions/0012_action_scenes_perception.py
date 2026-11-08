"""Deterministic actions, persistent scenes, and event-perception indexes."""

import sqlalchemy as sa
from alembic import op

revision = "0012_action_scenes_perception"
down_revision = "0011_simulation_scheduler"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("observations", sa.Column("basis", sa.String(32), nullable=True))
    op.create_index(
        "ix_player_presence_active_location",
        "player_presences",
        ["world_id", "location_id", "player_id"],
        sqlite_where=sa.text("activity = 'active'"),
    )
    op.create_index(
        "ix_character_state_location",
        "character_states",
        ["world_id", "location_id", "character_id"],
    )
    op.create_table(
        "scenes",
        sa.Column("world_id", sa.String(32), nullable=False, primary_key=True),
        sa.Column("scene_id", sa.String(32), nullable=False, primary_key=True),
        sa.Column("location_id", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("started_at", sa.BigInteger(), nullable=False),
        sa.Column("ended_at", sa.BigInteger(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at_utc", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.world_id"]),
        sa.ForeignKeyConstraint(
            ["world_id", "location_id"], ["locations.world_id", "locations.location_id"]
        ),
        sa.CheckConstraint("status IN ('open', 'closed')", name="ck_scene_status"),
        sa.CheckConstraint(
            "(status = 'open' AND ended_at IS NULL) OR "
            "(status = 'closed' AND ended_at IS NOT NULL AND ended_at >= started_at)",
            name="ck_scene_lifecycle",
        ),
        sa.CheckConstraint("revision >= 0", name="ck_scene_revision"),
    )
    op.create_index("ix_scenes_world_status", "scenes", ["world_id", "status", "scene_id"])
    op.create_table(
        "scene_participants",
        sa.Column("world_id", sa.String(32), nullable=False, primary_key=True),
        sa.Column("participant_id", sa.String(32), nullable=False, primary_key=True),
        sa.Column("scene_id", sa.String(32), nullable=False),
        sa.Column("principal_kind", sa.String(16), nullable=False),
        sa.Column("principal_id", sa.String(32), nullable=False),
        sa.Column("principal_character_id", sa.String(32), nullable=True),
        sa.Column("principal_player_id", sa.String(32), nullable=True),
        sa.Column("joined_at", sa.BigInteger(), nullable=False),
        sa.Column("left_at", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.world_id"]),
        sa.ForeignKeyConstraint(["world_id", "scene_id"], ["scenes.world_id", "scenes.scene_id"]),
        sa.ForeignKeyConstraint(
            ["world_id", "principal_character_id"],
            ["characters.world_id", "characters.character_id"],
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "principal_player_id"], ["players.world_id", "players.player_id"]
        ),
        sa.CheckConstraint(
            "(principal_kind = 'character' AND principal_character_id IS NOT NULL "
            "AND principal_character_id = principal_id AND principal_player_id IS NULL) OR "
            "(principal_kind = 'player' AND principal_player_id IS NOT NULL "
            "AND principal_player_id = principal_id AND principal_character_id IS NULL)",
            name="ck_scene_participant_principal",
        ),
        sa.CheckConstraint(
            "left_at IS NULL OR left_at >= joined_at", name="ck_scene_participant_time"
        ),
    )
    op.create_index(
        "uq_scene_active_principal",
        "scene_participants",
        ["world_id", "principal_kind", "principal_id"],
        unique=True,
        sqlite_where=sa.text("left_at IS NULL"),
    )
    op.create_index(
        "ix_scene_active_participants",
        "scene_participants",
        ["world_id", "scene_id", "left_at", "principal_kind", "principal_id"],
    )
    op.create_index(
        "ix_scene_participant_history",
        "scene_participants",
        ["world_id", "principal_kind", "principal_id", "joined_at"],
    )
    op.create_index(
        "uq_observation_event_principal",
        "observations",
        ["world_id", "target_event_id", "principal_kind", "principal_id"],
        unique=True,
        sqlite_where=sa.text("target_kind = 'event' AND basis = 'event_occurrence'"),
    )
    op.create_index(
        "ix_observation_principal_history",
        "observations",
        ["world_id", "principal_kind", "principal_id", "target_kind", "observed_at"],
    )
    with op.batch_alter_table("command_receipts", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_command_receipt_command_result", type_="check")
        batch_op.create_check_constraint(
            "ck_command_receipt_command_result",
            "(command_fingerprint IS NULL AND result_payload IS NULL) OR "
            "(command_fingerprint IS NOT NULL AND length(command_fingerprint) = 64 "
            "AND result_payload IS NOT NULL AND status IN ('committed', 'rejected') "
            "AND completed_at IS NOT NULL)",
        )


def downgrade():
    raise RuntimeError("action_scenes_perception_downgrade_requires_review")
