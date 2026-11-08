"""Add a local creator directory without exposing every runtime location."""

import sqlalchemy as sa
from alembic import op

revision = "0026_local_location_catalog"
down_revision = "0025_director_runtime"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "local_location_catalog",
        sa.Column("world_id", sa.String(32), nullable=False, primary_key=True),
        sa.Column("location_id", sa.String(32), nullable=False, primary_key=True),
        sa.Column("name_key", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.world_id"]),
        sa.ForeignKeyConstraint(
            ["world_id", "location_id"], ["locations.world_id", "locations.location_id"]
        ),
        sa.UniqueConstraint("world_id", "name_key", name="uq_local_location_name"),
        sa.CheckConstraint(
            "length(CAST(name_key AS BLOB)) BETWEEN 1 AND 4096",
            name="ck_local_location_name",
        ),
    )


def downgrade():
    op.drop_table("local_location_catalog")
