"""Append authored location rules without rewriting positions or historical events."""

import sqlalchemy as sa
from alembic import op

revision = "0038_location_policies"
down_revision = "0037_persistent_chat_recall"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "location_policies",
        sa.Column("world_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("location_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("parent_id", sa.String(32)),
        sa.Column("hidden", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["world_id", "location_id"], ["locations.world_id", "locations.location_id"]
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "parent_id"], ["locations.world_id", "locations.location_id"]
        ),
        sa.CheckConstraint(
            "parent_id IS NULL OR parent_id != location_id", name="ck_location_parent_self"
        ),
    )
    op.create_table(
        "location_character_access",
        sa.Column("world_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("location_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("character_id", sa.String(32), primary_key=True, nullable=False),
        sa.ForeignKeyConstraint(
            ["world_id", "location_id"], ["locations.world_id", "locations.location_id"]
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "character_id"], ["characters.world_id", "characters.character_id"]
        ),
    )
    op.create_table(
        "character_location_policies",
        sa.Column("world_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("character_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("initial_location_id", sa.String(32), nullable=False),
        sa.Column("locked", sa.Boolean(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["world_id", "character_id"], ["characters.world_id", "characters.character_id"]
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "initial_location_id"], ["locations.world_id", "locations.location_id"]
        ),
        sa.CheckConstraint("revision >= 0", name="ck_character_location_policy_revision"),
    )


def downgrade():
    op.drop_table("character_location_policies")
    op.drop_table("location_character_access")
    op.drop_table("location_policies")
