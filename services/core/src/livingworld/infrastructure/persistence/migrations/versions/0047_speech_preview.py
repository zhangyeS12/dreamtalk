"""Keep regenerated speech separate until an explicit post-preview decision."""

import sqlalchemy as sa
from alembic import op

from livingworld.infrastructure.persistence.types import UUIDStorage

revision = "0047_speech_preview"
down_revision = "0046_speech_cache_attempts"
branch_labels = None
depends_on = None


def upgrade():
    # Existing jobs retain their cache role, audio, save time and call receipts.
    op.add_column("speech_jobs", sa.Column("review_state", sa.String(16), nullable=True))
    op.add_column("speech_jobs", sa.Column("base_job_id", UUIDStorage(), nullable=True))
    op.add_column("speech_jobs", sa.Column("previewed_at", sa.String(32), nullable=True))
    op.create_index(
        "ix_speech_review",
        "speech_jobs",
        ["world_id", "conversation_id", "message_id", "review_state"],
    )


def downgrade():
    raise RuntimeError("speech_preview_downgrade_requires_explicit_data_resolution")
