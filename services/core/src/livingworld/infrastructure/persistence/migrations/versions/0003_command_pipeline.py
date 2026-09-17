"""Internal relationship metrics and persistent command identity/results."""

import sqlalchemy as sa
from alembic import op

revision = "0003_command_pipeline"
down_revision = "0002_world_domain_persistence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Native ADD COLUMN avoids rebuilding any FK target or touching event triggers.
    for name, minimum in (("affinity", -100), ("trust", -100), ("familiarity", 0)):
        op.add_column(
            "relationships",
            sa.Column(
                name,
                sa.Integer(),
                sa.CheckConstraint(
                    f"typeof({name}) = 'integer' AND {name} BETWEEN {minimum} AND 100",
                    name=f"ck_relationship_{name}",
                ),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )
    op.add_column("command_receipts", sa.Column("result_payload", sa.Text(), nullable=True))
    op.add_column(
        "command_receipts",
        sa.Column(
            "command_fingerprint",
            sa.String(64),
            sa.CheckConstraint(
                "(command_fingerprint IS NULL AND result_payload IS NULL) OR "
                "(command_fingerprint IS NOT NULL AND length(command_fingerprint) = 64 "
                "AND result_payload IS NOT NULL AND status = 'committed' "
                "AND completed_at IS NOT NULL AND result_event_id IS NOT NULL)",
                name="ck_command_receipt_command_result",
            ),
            nullable=True,
        ),
    )
    op.create_index(
        "uq_command_request_identity",
        "command_receipts",
        ["request_id"],
        unique=True,
        sqlite_where=sa.text("command_fingerprint IS NOT NULL"),
    )


def downgrade() -> None:
    # Removing durable command identity would make committed retries unsafe.
    raise RuntimeError("command_pipeline_downgrade_requires_review")
