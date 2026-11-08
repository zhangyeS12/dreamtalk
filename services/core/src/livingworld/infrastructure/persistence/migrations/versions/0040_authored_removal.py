"""Retire authored cards and locations, retaining all immutable snapshots and facts."""

import sqlalchemy as sa
from alembic import op

revision = "0040_authored_removal"
down_revision = "0039_character_mobility"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("world_content_imports", sa.Column("removed_at", sa.String(32), nullable=True))
    op.add_column("local_location_catalog", sa.Column("removed_at", sa.String(32), nullable=True))
    # Keep the existing SQLite table, foreign keys and records intact. Its old
    # UNIQUE constraint remains; removed rows receive an internal unique key.


def downgrade():
    op.drop_column("local_location_catalog", "removed_at")
    op.drop_column("world_content_imports", "removed_at")
