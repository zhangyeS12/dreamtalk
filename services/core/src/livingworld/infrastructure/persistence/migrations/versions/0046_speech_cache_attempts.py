"""Separate explicit speech attempts from six-hour derived audio caches."""

import sqlalchemy as sa
from alembic import op

revision = "0046_speech_cache_attempts"
down_revision = "0045_character_speech"
branch_labels = None
depends_on = None


def upgrade():
    # Legacy receipts and audio stay intact. A missing save time uses creation
    # time conservatively until normal cache cleanup; no guessed fresh lifetime.
    op.add_column("speech_jobs", sa.Column("cache_key", sa.String(64), nullable=True))
    op.add_column("speech_jobs", sa.Column("audio_saved_at", sa.String(32), nullable=True))
    op.create_index("ix_speech_cache_key", "speech_jobs", ["world_id", "cache_key", "created_at"])
    op.create_index("ix_speech_audio_saved", "speech_jobs", ["audio_saved_at"])


def downgrade():
    raise RuntimeError("speech_cache_downgrade_requires_explicit_data_resolution")
