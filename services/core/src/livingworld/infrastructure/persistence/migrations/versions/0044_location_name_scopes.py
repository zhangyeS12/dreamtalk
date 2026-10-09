"""Allow names to repeat in different authored location branches."""

import sqlalchemy as sa
from alembic import op

revision = "0044_location_name_scopes"
down_revision = "0043_acquaintance_sources"
branch_labels = None
depends_on = None


def _catalog():
    # Explicit reviewed shape also permits offline SQL generation without a DB.
    return sa.Table(
        "local_location_catalog",
        sa.MetaData(),
        sa.Column("world_id", sa.String(32), primary_key=True),
        sa.Column("location_id", sa.String(32), primary_key=True),
        sa.Column("name_key", sa.Text(), nullable=False),
        sa.Column("removed_at", sa.String(32), nullable=True),
        sa.Column("name_scope", sa.String(32), nullable=False, server_default=""),
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


def upgrade():
    op.add_column(
        "local_location_catalog",
        sa.Column("name_scope", sa.String(32), nullable=False, server_default=""),
    )
    op.execute(
        "UPDATE local_location_catalog SET name_scope = COALESCE("
        "(SELECT parent_id FROM location_policies "
        "WHERE location_policies.world_id = local_location_catalog.world_id "
        "AND location_policies.location_id = local_location_catalog.location_id), '')"
    )
    # No table references this creator directory. Canonical locations, IDs,
    # policies, observations and retained removal markers are left untouched.
    with op.batch_alter_table(
        "local_location_catalog", copy_from=_catalog(), recreate="always"
    ) as batch:
        batch.drop_constraint("uq_local_location_name", type_="unique")
        batch.create_unique_constraint(
            "uq_local_location_name", ["world_id", "name_scope", "name_key"]
        )
        batch.create_check_constraint(
            "ck_local_location_name_scope", "length(name_scope) IN (0, 32)"
        )


def downgrade():
    # Restoring world-wide uniqueness could discard valid same-name places.
    raise RuntimeError("location_name_scopes_downgrade_requires_explicit_data_resolution")
