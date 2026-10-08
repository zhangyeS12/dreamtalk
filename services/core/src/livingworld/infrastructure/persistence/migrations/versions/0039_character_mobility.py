"""Add residency and durable mobility gates without rewriting canonical positions."""

import sqlalchemy as sa
from alembic import op

revision = "0039_character_mobility"
down_revision = "0038_location_policies"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "location_policies",
        sa.Column("is_region", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "character_location_policies",
        sa.Column("residency", sa.String(16), nullable=False, server_default="strong"),
    )
    # SQLite validates new values via an additive guard, without rebuilding the
    # authored table referenced by live data or changing its historical rows.
    for operation in ("INSERT", "UPDATE"):
        op.execute(f"""CREATE TRIGGER character_residency_{operation.lower()}
            BEFORE {operation} ON character_location_policies
            WHEN NEW.residency NOT IN ('normal','strong','very_strong')
            BEGIN SELECT RAISE(ABORT, 'invalid_location_residency'); END""")
    op.create_table(
        "character_mobility",
        sa.Column("world_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("character_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("next_draw_at", sa.BigInteger(), nullable=False),
        sa.Column("cooldown_until", sa.BigInteger(), nullable=False),
        sa.Column("away_since", sa.BigInteger()),
        sa.Column("far_since", sa.BigInteger()),
        sa.ForeignKeyConstraint(
            ["world_id", "character_id"], ["characters.world_id", "characters.character_id"]
        ),
        sa.CheckConstraint(
            "next_draw_at >= 0 AND cooldown_until >= 0", name="ck_character_mobility_gate"
        ),
    )


def downgrade():
    op.drop_table("character_mobility")
    for operation in ("insert", "update"):
        op.execute(f"DROP TRIGGER character_residency_{operation}")
    op.drop_column("character_location_policies", "residency")
    op.drop_column("location_policies", "is_region")
