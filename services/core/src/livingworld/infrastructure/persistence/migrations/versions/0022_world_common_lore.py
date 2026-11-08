"""Keep user-confirmed common lore separate from authored content and truth."""

import sqlalchemy as sa
from alembic import op

revision = "0022_world_common_lore"
down_revision = "0021_group_turn_completion"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "world_common_lore",
        sa.Column("world_id", sa.String(32), nullable=False),
        sa.Column("import_id", sa.String(32), nullable=False),
        sa.Column("entry_id", sa.String(32), nullable=False),
        sa.PrimaryKeyConstraint("world_id", "import_id", "entry_id"),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.world_id"]),
        sa.ForeignKeyConstraint(["import_id"], ["world_content_imports.import_id"]),
    )
    op.create_index("ix_world_common_lore_world", "world_common_lore", ["world_id"])


def downgrade():
    raise RuntimeError("world_common_lore_downgrade_requires_review")
