"""Add world-scoped chat backgrounds and character expression bindings."""

import sqlalchemy as sa
from alembic import op

revision = "0061_chat_visuals"
down_revision = "0060_chat_preferences"
branch_labels = None
depends_on = None

EXPRESSIONS = (
    "'neutral','joy','content','sad','angry','surprised','scared',"
    "'disgusted','confused','love','embarrassed','thinking'"
)


def upgrade():
    op.create_table(
        "chat_visual_backgrounds",
        sa.Column("world_id", sa.String(32), primary_key=True),
        sa.Column("common_digest", sa.String(64), nullable=True),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.world_id"]),
        sa.ForeignKeyConstraint(
            ["world_id", "common_digest"],
            ["world_cover_images.world_id", "world_cover_images.digest"],
        ),
        sa.CheckConstraint(
            "common_digest IS NULL OR length(common_digest) = 64",
            name="ck_chat_visual_common_digest",
        ),
    )
    op.create_table(
        "chat_character_backgrounds",
        sa.Column("world_id", sa.String(32), primary_key=True),
        sa.Column("root_import_id", sa.String(32), primary_key=True),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.world_id"]),
        sa.ForeignKeyConstraint(["root_import_id"], ["world_content_imports.import_id"]),
        sa.ForeignKeyConstraint(
            ["world_id", "digest"],
            ["world_cover_images.world_id", "world_cover_images.digest"],
        ),
        sa.CheckConstraint("length(digest) = 64", name="ck_chat_visual_character_digest"),
    )
    op.create_table(
        "chat_character_expressions",
        sa.Column("world_id", sa.String(32), primary_key=True),
        sa.Column("root_import_id", sa.String(32), primary_key=True),
        sa.Column("expression", sa.String(16), primary_key=True),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.world_id"]),
        sa.ForeignKeyConstraint(["root_import_id"], ["world_content_imports.import_id"]),
        sa.ForeignKeyConstraint(
            ["world_id", "digest"],
            ["world_cover_images.world_id", "world_cover_images.digest"],
        ),
        sa.CheckConstraint(f"expression IN ({EXPRESSIONS})", name="ck_chat_visual_expression"),
        sa.CheckConstraint("length(digest) = 64", name="ck_chat_visual_expression_digest"),
    )
    op.create_index(
        "ix_chat_character_expressions_world_root",
        "chat_character_expressions",
        ["world_id", "root_import_id"],
    )


def downgrade():
    raise RuntimeError("chat_visuals_downgrade_not_supported")
