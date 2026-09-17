"""Independent authored content library, without changes to runtime tables."""

import sqlalchemy as sa
from alembic import op

revision = "0006_canonical_content"
down_revision = "0005_canonical_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name in ("content_character_definitions", "content_worlds", "content_lore_entries"):
        checks = [
            sa.CheckConstraint(
                "typeof(content_version) = 'integer' AND content_version = 1",
                name=f"ck_{name}_version",
            ),
            sa.CheckConstraint(
                "typeof(revision) = 'integer' AND revision >= 0", name=f"ck_{name}_revision"
            ),
            sa.CheckConstraint("length(semantic_hash) = 64", name=f"ck_{name}_hash"),
            sa.CheckConstraint("json_valid(canonical_json)", name=f"ck_{name}_json"),
        ]
        if name != "content_lore_entries":
            checks.append(sa.CheckConstraint("length(trim(title)) > 0", name=f"ck_{name}_title"))
        op.create_table(
            name,
            sa.Column("content_id", sa.String(32), primary_key=True),
            sa.Column("title", sa.Text(), nullable=False),
            sa.Column("content_version", sa.Integer(), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False),
            sa.Column("semantic_hash", sa.String(64), nullable=False),
            sa.Column("canonical_json", sa.Text(), nullable=False),
            *checks,
        )
    op.create_table(
        "content_assets",
        sa.Column("asset_id", sa.String(32), primary_key=True),
        sa.Column("media_type", sa.Text(), nullable=False),
        sa.Column("resource_reference", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.CheckConstraint("length(trim(media_type)) > 0", name="ck_content_assets_media_type"),
        sa.CheckConstraint(
            "length(trim(resource_reference)) > 0", name="ck_content_assets_reference"
        ),
        sa.CheckConstraint("json_valid(metadata_json)", name="ck_content_assets_json"),
    )
    op.create_table(
        "content_raw_imports",
        sa.Column("import_id", sa.String(32), primary_key=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("provenance_json", sa.Text(), nullable=False),
        sa.Column("extensions_json", sa.Text(), nullable=False),
        sa.Column("original_payload", sa.LargeBinary(), nullable=False),
        sa.CheckConstraint("length(content_hash) = 64", name="ck_content_raw_imports_hash"),
        sa.CheckConstraint("json_valid(provenance_json)", name="ck_content_raw_imports_provenance"),
        sa.CheckConstraint("json_valid(extensions_json)", name="ck_content_raw_imports_extensions"),
    )


def downgrade() -> None:
    raise RuntimeError("canonical_content_downgrade_requires_review")
