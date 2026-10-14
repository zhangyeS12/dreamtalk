"""World sticker libraries, personal library, attachments and bounded media receipts."""

import sqlalchemy as sa
from alembic import op

from livingworld.infrastructure.persistence.types import UUIDStorage

revision = "0048_chat_media"
down_revision = "0047_speech_preview"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("chat_messages", sa.Column("media_json", sa.Text(), nullable=True))
    op.create_table(
        "chat_media_assets",
        sa.Column("asset_id", UUIDStorage(), primary_key=True),
        sa.Column("world_id", UUIDStorage(), sa.ForeignKey("worlds.world_id")),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("mime", sa.String(32), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text()),
        sa.Column("caption_state", sa.String(16), nullable=False),
    )
    op.create_index("ix_media_asset_world", "chat_media_assets", ["world_id"])
    op.create_table(
        "chat_sticker_entries",
        sa.Column("entry_id", UUIDStorage(), primary_key=True),
        sa.Column("world_id", UUIDStorage(), sa.ForeignKey("worlds.world_id")),
        sa.Column("library", sa.String(16), nullable=False),
        sa.Column("library_key", sa.String(128), nullable=False),
        sa.Column(
            "root_import_id", UUIDStorage(), sa.ForeignKey("world_content_imports.import_id")
        ),
        sa.Column(
            "asset_id", UUIDStorage(), sa.ForeignKey("chat_media_assets.asset_id"), nullable=False
        ),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("library_key", "asset_id", name="uq_sticker_library_asset"),
        sa.CheckConstraint(
            "library IN ('personal','public','character')", name="ck_sticker_library"
        ),
        sa.CheckConstraint(
            "(library = 'personal' AND world_id IS NULL AND root_import_id IS NULL) OR "
            "(library = 'public' AND world_id IS NOT NULL AND root_import_id IS NULL) OR "
            "(library = 'character' AND world_id IS NOT NULL AND root_import_id IS NOT NULL)",
            name="ck_sticker_scope",
        ),
    )
    op.create_index("ix_sticker_library", "chat_sticker_entries", ["library_key", "active"])
    op.create_table(
        "chat_media_settings",
        sa.Column("world_id", UUIDStorage(), sa.ForeignKey("worlds.world_id"), primary_key=True),
        sa.Column("settings_json", sa.Text(), nullable=False),
    )
    op.create_table(
        "chat_media_attempts",
        sa.Column("world_id", UUIDStorage(), sa.ForeignKey("worlds.world_id"), primary_key=True),
        sa.Column("turn_id", UUIDStorage(), primary_key=True),
        sa.Column("conversation_id", UUIDStorage(), nullable=False),
        sa.Column("source_position", sa.Integer(), nullable=False),
        sa.Column("searched", sa.Boolean(), nullable=False),
        sa.Column("sent", sa.Boolean(), nullable=False),
    )
    op.create_index(
        "ix_media_conversation",
        "chat_media_attempts",
        ["world_id", "conversation_id", "source_position"],
    )
    op.create_table(
        "chat_media_caption_calls",
        sa.Column("call_id", UUIDStorage(), primary_key=True),
        sa.Column("world_scope", UUIDStorage(), nullable=False),
        sa.Column("asset_id", UUIDStorage(), nullable=False),
        sa.Column("utc_day", sa.String(10), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("usage_json", sa.Text()),
    )
    op.create_index("ix_media_caption_day", "chat_media_caption_calls", ["utc_day"])


def downgrade():
    raise RuntimeError("chat_media_downgrade_requires_explicit_data_resolution")
