"""Add authored faction membership and local character avatars."""

import sqlalchemy as sa
from alembic import op

revision = "0036_character_factions"
down_revision = "0035_proactive_contact"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "character_factions",
        sa.Column("world_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("faction_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("parent_id", sa.String(32), nullable=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.world_id"]),
        sa.ForeignKeyConstraint(
            ["world_id", "parent_id"],
            ["character_factions.world_id", "character_factions.faction_id"],
        ),
        sa.CheckConstraint(
            "parent_id IS NULL OR parent_id != faction_id", name="ck_faction_not_self"
        ),
    )
    op.create_index("ix_faction_parent", "character_factions", ["world_id", "parent_id"])
    op.create_table(
        "character_faction_members",
        sa.Column("world_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("faction_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("root_import_id", sa.String(32), primary_key=True, nullable=False),
        sa.ForeignKeyConstraint(
            ["world_id", "faction_id"],
            ["character_factions.world_id", "character_factions.faction_id"],
        ),
        sa.ForeignKeyConstraint(["root_import_id"], ["world_content_imports.import_id"]),
    )
    op.create_index(
        "ix_faction_member_character", "character_faction_members", ["world_id", "root_import_id"]
    )
    op.create_table(
        "character_avatars",
        sa.Column("world_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("root_import_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(["root_import_id"], ["world_content_imports.import_id"]),
        sa.ForeignKeyConstraint(
            ["world_id", "digest"], ["world_cover_images.world_id", "world_cover_images.digest"]
        ),
        sa.CheckConstraint("length(digest) = 64", name="ck_character_avatar_digest"),
    )
    op.create_table(
        "character_acquaintances",
        sa.Column("world_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("first_root_import_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("second_root_import_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("source_faction_id", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.world_id"]),
        sa.ForeignKeyConstraint(["first_root_import_id"], ["world_content_imports.import_id"]),
        sa.ForeignKeyConstraint(["second_root_import_id"], ["world_content_imports.import_id"]),
        sa.CheckConstraint(
            "first_root_import_id < second_root_import_id", name="ck_acquaintance_order"
        ),
    )


def downgrade():
    op.drop_table("character_acquaintances")
    op.drop_table("character_avatars")
    op.drop_index("ix_faction_member_character", table_name="character_faction_members")
    op.drop_table("character_faction_members")
    op.drop_index("ix_faction_parent", table_name="character_factions")
    op.drop_table("character_factions")
