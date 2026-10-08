"""Persist small random cohorts; preserve all existing locations and history."""

import sqlalchemy as sa
from alembic import op

revision = "0041_director_rotation"
down_revision = "0040_authored_removal"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "director_rotation",
        sa.Column("world_id", sa.String(32), primary_key=True),
        sa.Column("batch_size", sa.Integer(), nullable=False),
        sa.Column("settings_revision", sa.Integer(), nullable=False),
        sa.Column("cycle", sa.BigInteger(), nullable=False),
        sa.Column("window_end", sa.BigInteger(), nullable=False),
        sa.Column("accepted", sa.Boolean(), nullable=False),
        sa.Column("cohort_json", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.world_id"]),
        sa.CheckConstraint("cycle >= 0 AND window_end >= 0", name="ck_director_rotation_bounds"),
        sa.CheckConstraint(
            "batch_size BETWEEN 1 AND 16 AND settings_revision >= 0",
            name="ck_director_rotation_settings",
        ),
        sa.CheckConstraint(
            "json_valid(cohort_json) AND length(cohort_json) <= 1024",
            name="ck_director_rotation_cohort",
        ),
    )
    op.create_table(
        "director_rotation_members",
        sa.Column("world_id", sa.String(32), primary_key=True),
        sa.Column("character_id", sa.String(32), primary_key=True),
        sa.Column("last_cycle", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["world_id", "character_id"], ["characters.world_id", "characters.character_id"]
        ),
        sa.CheckConstraint("last_cycle >= 0", name="ck_director_rotation_member_cycle"),
    )
    op.create_table(
        "character_card_bindings",
        sa.Column("world_id", sa.String(32), primary_key=True),
        sa.Column("character_id", sa.String(32), primary_key=True),
        sa.Column("root_import_id", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(
            ["world_id", "character_id"], ["characters.world_id", "characters.character_id"]
        ),
        sa.ForeignKeyConstraint(["root_import_id"], ["world_content_imports.import_id"]),
        sa.UniqueConstraint("world_id", "root_import_id", name="uq_character_card_binding_root"),
    )
    op.execute(
        "INSERT INTO character_card_bindings (world_id, character_id, root_import_id) "
        "SELECT DISTINCT world_id, character_id, root_import_id FROM chat_participants"
    )


def downgrade():
    op.drop_table("character_card_bindings")
    op.drop_table("director_rotation_members")
    op.drop_table("director_rotation")
