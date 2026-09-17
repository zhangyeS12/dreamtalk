"""Explicit observation occurrence identity, preserving all legacy coordinates."""

import json
from uuid import UUID, uuid5

import sqlalchemy as sa
from alembic import op

revision = "0004_observation_identity"
down_revision = "0003_command_pipeline"
branch_labels = None
depends_on = None

# Frozen migration-only namespace; runtime uses independently generated UUIDs.
LEGACY_NAMESPACE = UUID("35cc16fa-c0b7-4ca3-a834-57cbbf226b1f")
LEGACY_COORDINATES = (
    "world_id",
    "principal_kind",
    "principal_id",
    "target_kind",
    "target_id",
    "channel",
    "observed_at",
)


def legacy_observation_uuid(row) -> UUID:
    canonical = json.dumps(
        {name: row[name] for name in LEGACY_COORDINATES},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return uuid5(LEGACY_NAMESPACE, canonical)


def upgrade() -> None:
    op.add_column("observations", sa.Column("observation_id", sa.String(32), nullable=True))
    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT * FROM observations")).mappings()
    for row in rows:
        predicates = " AND ".join(f"{name} = :{name}" for name in LEGACY_COORDINATES)
        connection.execute(
            sa.text(f"UPDATE observations SET observation_id = :identity WHERE {predicates}"),
            {
                **{name: row[name] for name in LEGACY_COORDINATES},
                "identity": legacy_observation_uuid(row).hex,
            },
        )
    with op.batch_alter_table(
        "observations", recreate="always", naming_convention={"pk": "pk_%(table_name)s"}
    ) as batch:
        batch.drop_constraint("pk_observations", type_="primary")
        batch.alter_column("observation_id", existing_type=sa.String(32), nullable=False)
        batch.create_primary_key("pk_observations", ["world_id", "observation_id"])


def downgrade() -> None:
    raise RuntimeError("observation_identity_downgrade_requires_review")
