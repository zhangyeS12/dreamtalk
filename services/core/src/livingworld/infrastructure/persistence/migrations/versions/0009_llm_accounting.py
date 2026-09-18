"""Physical-attempt usage ledger, isolated from canonical world/content state."""

import sqlalchemy as sa
from alembic import op

revision = "0009_llm_accounting"
down_revision = "0008_native_content_packages"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "llm_attempts",
        sa.Column("invocation_id", sa.String(32), primary_key=True),
        sa.Column("attempt_ordinal", sa.Integer, primary_key=True),
        sa.Column("purpose", sa.Text, nullable=False),
        sa.Column("provider_id", sa.Text, nullable=False),
        sa.Column("requested_model", sa.Text, nullable=False),
        sa.Column("reported_model", sa.Text, nullable=True),
        sa.Column("started_at_utc", sa.String(32), nullable=False),
        sa.Column("finished_at_utc", sa.String(32), nullable=True),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("invocation_outcome", sa.String(16), nullable=True),
        sa.Column("facts", sa.Text, nullable=True),
        sa.Column("cost_status", sa.String(32), nullable=False),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("estimated_cost", sa.Text, nullable=True),
        sa.Column("price_snapshot", sa.Text, nullable=True),
        sa.CheckConstraint("attempt_ordinal >= 1", name="ck_llm_attempt_ordinal"),
        sa.CheckConstraint(
            "invocation_outcome IS NULL OR (facts IS NOT NULL AND "
            "invocation_outcome IN ('success','failed','cancelled','local_error'))",
            name="ck_llm_invocation_terminal",
        ),
        sa.CheckConstraint(
            "outcome IN ('incomplete','success','failed','cancelled','local_error')",
            name="ck_llm_attempt_outcome",
        ),
        sa.CheckConstraint(
            "cost_status IN "
            "('priced','price_unknown','usage_unknown','usage_partial','pricing_context_incomplete"
            "','possibly_billed_unknown','not_dispatched')",
            name="ck_llm_attempt_cost_status",
        ),
        sa.CheckConstraint(
            "(outcome = 'incomplete' AND finished_at_utc IS NULL AND facts IS NULL AND "
            "cost_status = 'possibly_billed_unknown') OR (outcome != 'incomplete' AND "
            "finished_at_utc IS NOT NULL AND facts IS NOT NULL)",
            name="ck_llm_attempt_lifecycle",
        ),
        sa.CheckConstraint(
            "(cost_status = 'priced' AND currency IS NOT NULL AND estimated_cost IS NOT NULL AND "
            "price_snapshot IS NOT NULL) OR (cost_status != 'priced' AND currency IS NULL AND "
            "estimated_cost IS NULL AND price_snapshot IS NULL)",
            name="ck_llm_attempt_estimate",
        ),
    )
    op.create_index("ix_llm_attempt_time", "llm_attempts", ["started_at_utc"])
    op.create_index("ix_llm_attempt_purpose", "llm_attempts", ["purpose", "started_at_utc"])
    op.create_index(
        "ix_llm_attempt_model", "llm_attempts", ["provider_id", "requested_model", "started_at_utc"]
    )


def downgrade():
    raise RuntimeError("llm_accounting_downgrade_requires_review")
