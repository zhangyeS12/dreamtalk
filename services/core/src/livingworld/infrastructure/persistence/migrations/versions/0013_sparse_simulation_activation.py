"""Generalize durable activations with typed targets, causes, and deterministic coalescing."""

import sqlalchemy as sa
from alembic import op

revision = "0013_sparse_simulation_activation"
down_revision = "0012_action_scenes_perception"
branch_labels = None
depends_on = None


def upgrade():
    # Both legacy tables reference the trigger table. SQLite's batch-table
    # recreation temporarily drops that parent, so defer FK validation until
    # the migration transaction has recreated every table and relationship.
    op.execute("PRAGMA defer_foreign_keys = ON")
    for column in (
        sa.Column("activation_target_kind", sa.String(16), nullable=True),
        sa.Column("activation_target_id", sa.String(32), nullable=True),
        sa.Column("activation_target_character_id", sa.String(32), nullable=True),
        sa.Column("activation_kind", sa.String(64), nullable=True),
        sa.Column("activation_version", sa.Integer(), nullable=True),
        sa.Column("activation_coalescing_key", sa.String(128), nullable=True),
        sa.Column("activation_attention", sa.String(16), nullable=True),
    ):
        op.add_column("simulation_scheduled_triggers", column)
    op.execute(
        "UPDATE simulation_scheduled_triggers SET "
        "activation_target_kind = 'world', activation_target_id = world_id, "
        "activation_kind = 'world_orchestration', activation_version = 1, "
        "activation_attention = 'none'"
    )
    with op.batch_alter_table("simulation_scheduled_triggers", recreate="always") as batch:
        for name in (
            "activation_target_kind",
            "activation_target_id",
            "activation_kind",
            "activation_version",
            "activation_attention",
        ):
            batch.alter_column(name, nullable=False)
        batch.create_foreign_key(
            "fk_simulation_trigger_activation_character",
            "characters",
            ["world_id", "activation_target_character_id"],
            ["world_id", "character_id"],
        )
        batch.create_check_constraint(
            "ck_simulation_trigger_activation_target",
            "(activation_target_kind = 'world' AND activation_target_id = world_id "
            "AND activation_target_character_id IS NULL) OR "
            "(activation_target_kind = 'character' "
            "AND activation_target_character_id = activation_target_id)",
        )
        batch.create_check_constraint(
            "ck_simulation_trigger_activation_version",
            "activation_version >= 1 AND activation_version <= 65535",
        )
        batch.create_check_constraint(
            "ck_simulation_trigger_activation_attention",
            "activation_attention IN ('none','active') "
            "AND NOT (activation_target_kind = 'world' AND activation_attention = 'active')",
        )

    for column in (
        sa.Column("target_kind", sa.String(16), nullable=True),
        sa.Column("target_id", sa.String(32), nullable=True),
        sa.Column("target_character_id", sa.String(32), nullable=True),
        sa.Column("activation_kind", sa.String(64), nullable=True),
        sa.Column("activation_version", sa.Integer(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=True),
        sa.Column("enqueue_position", sa.BigInteger(), nullable=True),
        sa.Column("coalescing_key", sa.String(128), nullable=True),
        sa.Column("attention", sa.String(16), nullable=True),
    ):
        op.add_column("simulation_activations", column)
    op.execute(
        "UPDATE simulation_activations SET "
        "target_kind = 'world', target_id = world_id, "
        "activation_kind = 'world_orchestration', activation_version = 1, "
        "priority = (SELECT priority FROM simulation_scheduled_triggers t "
        "WHERE t.world_id = simulation_activations.world_id "
        "AND t.trigger_id = simulation_activations.source_trigger_id), "
        "enqueue_position = (SELECT enqueue_position FROM simulation_scheduled_triggers t "
        "WHERE t.world_id = simulation_activations.world_id "
        "AND t.trigger_id = simulation_activations.source_trigger_id), "
        "attention = 'none'"
    )
    with op.batch_alter_table("simulation_activations", recreate="always") as batch:
        batch.alter_column("source_trigger_id", nullable=True)
        for name in (
            "target_kind",
            "target_id",
            "activation_kind",
            "activation_version",
            "priority",
            "enqueue_position",
            "attention",
        ):
            batch.alter_column(name, nullable=False)
        batch.create_foreign_key(
            "fk_simulation_activation_target_character",
            "characters",
            ["world_id", "target_character_id"],
            ["world_id", "character_id"],
        )
        batch.create_unique_constraint(
            "uq_simulation_activation_enqueue_position", ["world_id", "enqueue_position"]
        )
        batch.create_check_constraint(
            "ck_simulation_activation_target",
            "(target_kind = 'world' AND target_id = world_id "
            "AND target_character_id IS NULL) OR "
            "(target_kind = 'character' AND target_character_id = target_id)",
        )
        batch.create_check_constraint(
            "ck_simulation_activation_version",
            "activation_version >= 1 AND activation_version <= 65535",
        )
        batch.create_check_constraint("ck_simulation_activation_priority", "priority IN (-1,0,1)")
        batch.create_check_constraint(
            "ck_simulation_activation_enqueue_position", "enqueue_position > 0"
        )
        batch.create_check_constraint(
            "ck_simulation_activation_attention",
            "attention IN ('none','active') "
            "AND NOT (target_kind = 'world' AND attention = 'active')",
        )
    op.create_index(
        "ix_simulation_activation_due",
        "simulation_activations",
        ["world_id", "status", "due_at", "priority", "enqueue_position"],
    )
    op.create_index(
        "ix_simulation_activation_target",
        "simulation_activations",
        ["world_id", "target_kind", "target_id"],
    )
    op.create_index(
        "uq_simulation_activation_pending_coalescing",
        "simulation_activations",
        [
            "world_id",
            "target_kind",
            "target_id",
            "activation_kind",
            "activation_version",
            "coalescing_key",
        ],
        unique=True,
        sqlite_where=sa.text("status = 'pending' AND coalescing_key IS NOT NULL"),
    )

    op.create_table(
        "simulation_activation_causes",
        sa.Column("world_id", sa.String(32), nullable=False, primary_key=True),
        sa.Column("activation_id", sa.String(32), nullable=False, primary_key=True),
        sa.Column("cause_identity", sa.String(160), nullable=False, primary_key=True),
        sa.Column("position", sa.BigInteger(), nullable=False),
        sa.Column("cause_kind", sa.String(32), nullable=False),
        sa.Column("source_trigger_id", sa.String(32), nullable=True),
        sa.Column("source_event_id", sa.String(32), nullable=True),
        sa.Column("source_scene_id", sa.String(32), nullable=True),
        sa.Column("scene_activity", sa.String(32), nullable=True),
        sa.Column("source_request_id", sa.String(32), nullable=True),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("attached_at_utc", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.world_id"]),
        sa.ForeignKeyConstraint(
            ["world_id", "activation_id"],
            ["simulation_activations.world_id", "simulation_activations.activation_id"],
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "source_trigger_id"],
            ["simulation_scheduled_triggers.world_id", "simulation_scheduled_triggers.trigger_id"],
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "source_event_id"], ["world_events.world_id", "world_events.event_id"]
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "source_scene_id"], ["scenes.world_id", "scenes.scene_id"]
        ),
        sa.UniqueConstraint(
            "world_id",
            "activation_id",
            "position",
            name="uq_simulation_activation_cause_position",
        ),
        sa.CheckConstraint("position > 0", name="ck_simulation_activation_cause_position"),
        sa.CheckConstraint(
            "length(request_fingerprint) = 64",
            name="ck_simulation_activation_cause_fingerprint",
        ),
        sa.CheckConstraint(
            "(cause_kind = 'scheduled_trigger' AND source_trigger_id IS NOT NULL "
            "AND source_event_id IS NULL AND source_scene_id IS NULL "
            "AND scene_activity IS NULL AND source_request_id IS NULL) OR "
            "(cause_kind = 'world_event' AND source_trigger_id IS NULL "
            "AND source_event_id IS NOT NULL AND source_scene_id IS NULL "
            "AND scene_activity IS NULL AND source_request_id IS NULL) OR "
            "(cause_kind = 'scene_activity' AND source_trigger_id IS NULL "
            "AND source_event_id IS NULL AND source_scene_id IS NOT NULL "
            "AND scene_activity IS NOT NULL AND source_request_id IS NOT NULL) OR "
            "(cause_kind = 'explicit_system' AND source_trigger_id IS NULL "
            "AND source_event_id IS NULL AND source_scene_id IS NULL "
            "AND scene_activity IS NULL AND source_request_id IS NOT NULL)",
            name="ck_simulation_activation_cause_shape",
        ),
    )
    op.create_index(
        "ix_simulation_activation_cause_order",
        "simulation_activation_causes",
        ["world_id", "activation_id", "position", "cause_identity"],
    )
    op.create_index(
        "ix_simulation_activation_cause_identity",
        "simulation_activation_causes",
        ["world_id", "cause_identity"],
    )
    op.execute(
        "INSERT INTO simulation_activation_causes "
        "(world_id, cause_identity, activation_id, position, cause_kind, "
        "source_trigger_id, source_event_id, source_scene_id, scene_activity, "
        "source_request_id, request_fingerprint, attached_at_utc) "
        "SELECT world_id, 'scheduled_trigger:' || source_trigger_id, activation_id, 1, "
        "'scheduled_trigger', source_trigger_id, NULL, NULL, NULL, NULL, "
        "lower(hex(source_trigger_id)), materialized_at_utc FROM simulation_activations "
        "WHERE source_trigger_id IS NOT NULL"
    )
    violations = op.get_bind().execute(sa.text("PRAGMA foreign_key_check")).fetchall()
    if violations:
        raise RuntimeError("sparse activation migration produced foreign key violations")
    # The final graph is valid; clear SQLite's deferred record of the temporary
    # parent-table drop performed by batch recreation before transaction commit.
    op.execute("PRAGMA defer_foreign_keys = OFF")


def downgrade():
    raise RuntimeError("sparse_simulation_activation_downgrade_requires_review")
