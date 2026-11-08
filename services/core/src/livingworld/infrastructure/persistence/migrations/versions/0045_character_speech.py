"""Add authored speech without changing canonical world facts or existing transcripts."""

import sqlalchemy as sa
from alembic import op

revision = "0045_character_speech"
down_revision = "0044_location_name_scopes"
branch_labels = None
depends_on = None


def upgrade():
    def world():
        return sa.Column("world_id", sa.String(32), primary_key=True)

    def fk():
        return sa.ForeignKeyConstraint(["world_id"], ["worlds.world_id"])

    op.create_table(
        "voice_cards",
        world(),
        sa.Column("card_id", sa.String(32), primary_key=True),
        sa.Column("manifest_json", sa.Text(), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("audio", sa.LargeBinary(), nullable=False),
        fk(),
    )
    op.create_table(
        "character_voices",
        world(),
        sa.Column("root_import_id", sa.String(32), primary_key=True),
        sa.Column("card_id", sa.String(32), nullable=False),
        fk(),
        sa.ForeignKeyConstraint(["root_import_id"], ["world_content_imports.import_id"]),
        sa.ForeignKeyConstraint(
            ["world_id", "card_id"], ["voice_cards.world_id", "voice_cards.card_id"]
        ),
    )
    op.create_table(
        "speech_settings",
        world(),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("settings_json", sa.Text(), nullable=False),
        fk(),
    )
    op.create_table(
        "speech_jobs",
        world(),
        sa.Column("job_id", sa.String(32), primary_key=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("player_id", sa.String(32), nullable=False),
        sa.Column("conversation_id", sa.String(32), nullable=False),
        sa.Column("message_id", sa.String(32), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("error", sa.String(96)),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("remote_id", sa.String(128)),
        sa.Column("audio", sa.LargeBinary()),
        fk(),
        sa.UniqueConstraint("world_id", "fingerprint", name="uq_speech_job_fingerprint"),
    )
    op.create_table(
        "speech_call_receipts",
        sa.Column("job_id", sa.String(32), primary_key=True),
        sa.Column("day", sa.String(10), nullable=False),
    )
    op.create_index("ix_voice_card_digest", "voice_cards", ["world_id", "digest"])
    op.create_index("ix_speech_call_day", "speech_call_receipts", ["day"])
    op.create_table(
        "remote_voices",
        world(),
        sa.Column("cache_key", sa.String(64), primary_key=True),
        sa.Column("voice_id", sa.String(128), nullable=False),
        fk(),
    )


def downgrade():
    raise RuntimeError("speech_downgrade_requires_explicit_data_resolution")
