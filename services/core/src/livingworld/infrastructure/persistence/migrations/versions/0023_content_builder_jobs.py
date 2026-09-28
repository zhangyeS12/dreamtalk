"""World-owned authored research receipts; a request never dispatches twice."""

import sqlalchemy as sa
from alembic import op

revision = "0023_content_builder_jobs"
down_revision = "0022_world_common_lore"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "content_builder_jobs",
        sa.Column("request_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("world_id", sa.String(32), sa.ForeignKey("worlds.world_id"), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("result_json", sa.Text()),
        sa.Column("error", sa.String(80)),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "state IN ('searching','generating','ready','failed','interrupted')",
            name="ck_builder_job_state",
        ),
        sa.CheckConstraint("length(fingerprint) = 64", name="ck_builder_job_fingerprint"),
        sa.CheckConstraint(
            "result_json IS NULL OR json_valid(result_json)", name="ck_builder_job_result"
        ),
    )


def downgrade():
    op.drop_table("content_builder_jobs")
