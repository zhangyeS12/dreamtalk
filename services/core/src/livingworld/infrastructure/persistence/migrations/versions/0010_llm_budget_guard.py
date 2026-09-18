"""Persistent estimated-spend policies and pre-dispatch reservations."""

import sqlalchemy as sa
from alembic import op

revision = "0010_llm_budget_guard"
down_revision = "0009_llm_accounting"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "llm_budgets",
        sa.Column("budget_id", sa.String(32), nullable=False, primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, primary_key=False),
        sa.Column("mode", sa.String(8), nullable=False, primary_key=False),
        sa.Column("currency", sa.String(3), nullable=False, primary_key=False),
        sa.Column("limit_amount", sa.Text(), nullable=False, primary_key=False),
        sa.Column("start_utc", sa.String(32), nullable=False, primary_key=False),
        sa.Column("end_utc", sa.String(32), nullable=False, primary_key=False),
        sa.Column("purpose", sa.Text(), nullable=True, primary_key=False),
        sa.Column("provider_id", sa.Text(), nullable=True, primary_key=False),
        sa.Column("model_id", sa.Text(), nullable=True, primary_key=False),
        sa.Column("revision", sa.Integer(), nullable=False, primary_key=False),
        sa.Column("created_at_utc", sa.String(32), nullable=False, primary_key=False),
        sa.Column("updated_at_utc", sa.String(32), nullable=False, primary_key=False),
        sa.CheckConstraint("updated_at_utc >= created_at_utc", name="ck_llm_budget_audit_time"),
        sa.CheckConstraint("enabled IN (0,1)", name="ck_llm_budget_enabled"),
        sa.CheckConstraint("mode IN ('off','soft','hard')", name="ck_llm_budget_mode"),
        sa.CheckConstraint(
            "model_id IS NULL OR provider_id IS NOT NULL", name="ck_llm_budget_model_scope"
        ),
        sa.CheckConstraint("revision >= 0", name="ck_llm_budget_revision"),
        sa.CheckConstraint("start_utc < end_utc", name="ck_llm_budget_window"),
    )
    op.create_index(
        "ix_llm_budget_enabled", "llm_budgets", ["enabled", "mode", "start_utc", "end_utc"]
    )
    op.create_table(
        "llm_budget_reservations",
        sa.Column("budget_id", sa.String(32), nullable=False, primary_key=True),
        sa.Column("invocation_id", sa.String(32), nullable=False, primary_key=True),
        sa.Column("attempt_ordinal", sa.Integer(), nullable=False, primary_key=True),
        sa.Column("currency", sa.String(3), nullable=False, primary_key=False),
        sa.Column("reserved_amount", sa.Text(), nullable=False, primary_key=False),
        sa.Column("status", sa.String(24), nullable=False, primary_key=False),
        sa.Column("settled_amount", sa.Text(), nullable=True, primary_key=False),
        sa.Column("created_at_utc", sa.String(32), nullable=False, primary_key=False),
        sa.Column("updated_at_utc", sa.String(32), nullable=False, primary_key=False),
        sa.Column("policy_snapshot", sa.Text(), nullable=False, primary_key=False),
        sa.Column("bound_evidence", sa.Text(), nullable=False, primary_key=False),
        sa.ForeignKeyConstraint(["budget_id"], ["llm_budgets.budget_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["invocation_id", "attempt_ordinal"],
            ["llm_attempts.invocation_id", "llm_attempts.attempt_ordinal"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "updated_at_utc >= created_at_utc", name="ck_llm_reservation_audit_time"
        ),
        sa.CheckConstraint("attempt_ordinal >= 1", name="ck_llm_reservation_ordinal"),
        sa.CheckConstraint(
            "(status = 'settled' AND settled_amount IS NOT NULL) OR "
            "(status != 'settled' AND settled_amount IS NULL)",
            name="ck_llm_reservation_settlement",
        ),
        sa.CheckConstraint(
            "status IN ('held','held_uncertain','settled','released',"
            "'bound_violation','integrity_degraded')",
            name="ck_llm_reservation_status",
        ),
    )
    op.create_index(
        "ix_llm_reservation_attempt",
        "llm_budget_reservations",
        ["invocation_id", "attempt_ordinal"],
    )


def downgrade():
    raise RuntimeError("llm_budget_downgrade_requires_review")
