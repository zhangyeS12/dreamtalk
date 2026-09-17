"""Authored collections and nullable legacy-only ownership; no runtime changes."""

import sqlalchemy as sa
from alembic import op

revision = "0007_lore_collections"
down_revision = "0006_canonical_content"
branch_labels = None
depends_on = None


def upgrade() -> None:
    name = "content_lore_collections"
    op.create_table(
        name,
        sa.Column("content_id", sa.String(32), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("content_version", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("semantic_hash", sa.String(64), nullable=False),
        sa.Column("canonical_json", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "typeof(content_version) = 'integer' AND content_version = 1",
            name=f"ck_{name}_version",
        ),
        sa.CheckConstraint(
            "typeof(revision) = 'integer' AND revision >= 0", name=f"ck_{name}_revision"
        ),
        sa.CheckConstraint("length(semantic_hash) = 64", name=f"ck_{name}_hash"),
        sa.CheckConstraint("json_valid(canonical_json)", name=f"ck_{name}_json"),
    )
    # SQLite supports an additive nullable REFERENCES column. No table rebuild,
    # backfill, canonical JSON/hash rewrite or inference from legacy references.
    op.execute(
        "ALTER TABLE content_lore_entries ADD COLUMN collection_id VARCHAR(32) "
        "REFERENCES content_lore_collections(content_id)"
    )


def downgrade() -> None:
    raise RuntimeError("lore_collections_downgrade_requires_review")
