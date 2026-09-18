"""Local accepted baselines and immutable asset bindings; no ZIP/runtime tables."""

import sqlalchemy as sa
from alembic import op

revision = "0008_native_content_packages"
down_revision = "0007_lore_collections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "content_import_baselines",
        sa.Column("content_kind", sa.String(32), primary_key=True),
        sa.Column("content_id", sa.String(32), primary_key=True),
        sa.Column("accepted_semantic_hash", sa.String(64), nullable=False),
        sa.Column("accepted_at_utc", sa.String(32), nullable=False),
        sa.Column("source_package_id", sa.String(32), nullable=True),
        sa.Column("source_package_hash", sa.String(64), nullable=True),
        sa.CheckConstraint(
            "content_kind IN ('character_definition','world_content',"
            "'lore_entry','lore_collection')",
            name="ck_import_baseline_kind",
        ),
        sa.CheckConstraint(
            "length(accepted_semantic_hash) = 64 AND accepted_semantic_hash NOT GLOB '*[^0-9a-f]*'",
            name="ck_import_baseline_hash",
        ),
        sa.CheckConstraint(
            "source_package_hash IS NULL OR (length(source_package_hash) = 64 "
            "AND source_package_hash NOT GLOB '*[^0-9a-f]*')",
            name="ck_import_baseline_source_hash",
        ),
    )
    op.create_table(
        "content_asset_blob_bindings",
        sa.Column(
            "asset_id", sa.String(32), sa.ForeignKey("content_assets.asset_id"), primary_key=True
        ),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "length(digest) = 64 AND digest NOT GLOB '*[^0-9a-f]*'", name="ck_asset_blob_digest"
        ),
        sa.CheckConstraint("typeof(size) = 'integer' AND size >= 0", name="ck_asset_blob_size"),
    )


def downgrade() -> None:
    raise RuntimeError("native_content_packages_downgrade_requires_review")
