"""Durable tickless simulation trigger and activation substrate."""

import sqlalchemy as sa
from alembic import op

revision = "0011_simulation_scheduler"
down_revision = "0010_llm_budget_guard"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "simulation_queue_cursors",
        sa.Column("world_id", sa.String(32), nullable=False, primary_key=True),
        sa.Column("last_position", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.world_id"]),
        sa.CheckConstraint("last_position >= 0", name="ck_simulation_queue_cursor_position"),
    )
    op.create_table(
        "simulation_scheduled_triggers",
        sa.Column("world_id", sa.String(32), nullable=False, primary_key=True),
        sa.Column("trigger_id", sa.String(32), nullable=False, primary_key=True),
        sa.Column("due_at", sa.BigInteger(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("enqueue_position", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(128), nullable=False),
        sa.Column("payload_version", sa.Integer(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at_utc", sa.String(32), nullable=False),
        sa.Column("fired_at_utc", sa.String(32), nullable=True),
        sa.Column("cancelled_at_utc", sa.String(32), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("causation_request_id", sa.String(32), nullable=True),
        sa.Column("correlation_id", sa.String(32), nullable=True),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.world_id"]),
        sa.UniqueConstraint(
            "world_id", "enqueue_position", name="uq_simulation_trigger_enqueue_position"
        ),
        sa.CheckConstraint("typeof(due_at) = 'integer'", name="ck_simulation_trigger_due_at_type"),
        sa.CheckConstraint("priority IN (-1,0,1)", name="ck_simulation_trigger_priority"),
        sa.CheckConstraint("enqueue_position > 0", name="ck_simulation_trigger_enqueue_position"),
        sa.CheckConstraint(
            "payload_version >= 1 AND payload_version <= 65535",
            name="ck_simulation_trigger_payload_version",
        ),
        sa.CheckConstraint(
            "length(kind) >= 1 AND length(kind) <= 128",
            name="ck_simulation_trigger_kind",
        ),
        sa.CheckConstraint(
            "(status = 'pending' AND fired_at_utc IS NULL AND cancelled_at_utc IS NULL) OR "
            "(status = 'fired' AND fired_at_utc IS NOT NULL AND cancelled_at_utc IS NULL) OR "
            "(status = 'cancelled' AND fired_at_utc IS NULL AND cancelled_at_utc IS NOT NULL)",
            name="ck_simulation_trigger_status",
        ),
        sa.CheckConstraint("revision >= 0", name="ck_simulation_scheduled_triggers_revision"),
    )
    op.create_index(
        "ix_simulation_trigger_due",
        "simulation_scheduled_triggers",
        ["world_id", "status", "due_at", "priority", "enqueue_position"],
    )
    op.create_table(
        "simulation_activations",
        sa.Column("world_id", sa.String(32), nullable=False, primary_key=True),
        sa.Column("activation_id", sa.String(32), nullable=False, primary_key=True),
        sa.Column("source_trigger_id", sa.String(32), nullable=False),
        sa.Column("kind", sa.String(128), nullable=False),
        sa.Column("payload_version", sa.Integer(), nullable=False),
        sa.Column("due_at", sa.BigInteger(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("materialized_at_utc", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(
            ["world_id", "source_trigger_id"],
            ["simulation_scheduled_triggers.world_id", "simulation_scheduled_triggers.trigger_id"],
        ),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.world_id"]),
        sa.UniqueConstraint(
            "world_id", "source_trigger_id", name="uq_simulation_activation_source"
        ),
        sa.CheckConstraint(
            "typeof(due_at) = 'integer'", name="ck_simulation_activation_due_at_type"
        ),
        sa.CheckConstraint(
            "payload_version >= 1 AND payload_version <= 65535",
            name="ck_simulation_activation_payload_version",
        ),
        sa.CheckConstraint(
            "length(kind) >= 1 AND length(kind) <= 128",
            name="ck_simulation_activation_kind",
        ),
        sa.CheckConstraint("status = 'pending'", name="ck_simulation_activation_status"),
    )
    op.create_table(
        "simulation_schedule_receipts",
        sa.Column("world_id", sa.String(32), nullable=False, primary_key=True),
        sa.Column("request_id", sa.String(32), nullable=False, primary_key=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("trigger_id", sa.String(32), nullable=False),
        sa.Column("created_at_utc", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(
            ["world_id", "trigger_id"],
            ["simulation_scheduled_triggers.world_id", "simulation_scheduled_triggers.trigger_id"],
        ),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.world_id"]),
        sa.CheckConstraint(
            "length(fingerprint) = 64", name="ck_simulation_schedule_receipt_fingerprint"
        ),
    )
    op.create_index(
        "uq_simulation_schedule_request",
        "simulation_schedule_receipts",
        ["request_id"],
        unique=True,
    )


def downgrade():
    raise RuntimeError("simulation_scheduler_downgrade_requires_review")
