"""Accepted world-owned authored content snapshots; no runtime mutation."""

import sqlalchemy as sa
from alembic import op

revision = "0017_world_content_imports"
down_revision = "0016_local_profiles"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "world_content_imports",
        sa.Column("import_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("replaces_import_id", sa.String(32), nullable=True),
        sa.Column("world_id", sa.String(32), nullable=False),
        sa.Column("reviewed_hash", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("accepted_at", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.world_id"]),
        sa.ForeignKeyConstraint(["replaces_import_id"], ["world_content_imports.import_id"]),
        sa.CheckConstraint(
            "kind IN ('character', 'lorebook')", name="ck_world_content_import_kind"
        ),
        sa.CheckConstraint("length(reviewed_hash) = 64", name="ck_world_content_import_hash"),
    )
    op.create_index("ix_world_content_import_world", "world_content_imports", ["world_id"])
    op.create_index(
        "uq_world_content_replaces",
        "world_content_imports",
        ["replaces_import_id"],
        unique=True,
    )


def downgrade():
    raise RuntimeError("world_content_import_downgrade_requires_review")
