"""Track independent faction acquaintance bases without rewriting encounter history."""

import sqlalchemy as sa
from alembic import op

revision = "0043_acquaintance_sources"
down_revision = "0042_world_deletion"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "character_acquaintance_sources",
        sa.Column("world_id", sa.String(32), primary_key=True),
        sa.Column("first_root_import_id", sa.String(32), primary_key=True),
        sa.Column("second_root_import_id", sa.String(32), primary_key=True),
        sa.Column("source_faction_id", sa.String(32), primary_key=True),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.world_id"]),
        sa.ForeignKeyConstraint(["first_root_import_id"], ["world_content_imports.import_id"]),
        sa.ForeignKeyConstraint(["second_root_import_id"], ["world_content_imports.import_id"]),
        sa.CheckConstraint(
            "first_root_import_id < second_root_import_id", name="ck_acquaintance_source_order"
        ),
    )
    op.create_index(
        "ix_acquaintance_source_faction",
        "character_acquaintance_sources",
        ["world_id", "source_faction_id"],
    )
    # The original source survives even if its members/faction have since left.
    # Also recover each currently shared faction: older versions kept only one source.
    op.execute(
        "INSERT INTO character_acquaintance_sources "
        "(world_id, first_root_import_id, second_root_import_id, source_faction_id) "
        "SELECT world_id, first_root_import_id, second_root_import_id, source_faction_id "
        "FROM character_acquaintances UNION "
        "SELECT k.world_id, k.first_root_import_id, k.second_root_import_id, a.faction_id "
        "FROM character_acquaintances k "
        "JOIN character_faction_members a ON a.world_id = k.world_id "
        "AND a.root_import_id = k.first_root_import_id "
        "JOIN character_faction_members b ON b.world_id = k.world_id "
        "AND b.root_import_id = k.second_root_import_id AND b.faction_id = a.faction_id"
    )


def downgrade():
    op.drop_index("ix_acquaintance_source_faction", table_name="character_acquaintance_sources")
    op.drop_table("character_acquaintance_sources")
