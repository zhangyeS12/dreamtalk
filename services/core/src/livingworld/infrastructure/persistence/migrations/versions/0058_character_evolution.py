"""Add reversible character-card evolution overlays."""

import sqlalchemy as sa
from alembic import op

revision = "0058_character_evolution"
down_revision = "0057_chat_paths"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "character_card_evolution",
        sa.Column("entry_id", sa.String(32), primary_key=True),
        sa.Column("world_id", sa.String(32), nullable=False),
        sa.Column("root_import_id", sa.String(32), nullable=False),
        sa.Column("field", sa.String(32), nullable=False),
        sa.Column("scope", sa.String(120), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("selected", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("locked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("created_at_utc", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.world_id"]),
        sa.ForeignKeyConstraint(["root_import_id"], ["world_content_imports.import_id"]),
        sa.CheckConstraint(
            "field IN ('description','personality','background','scenario','speech_guidance')",
            name="ck_character_evolution_field",
        ),
        sa.CheckConstraint("state IN ('active','inactive')", name="ck_character_evolution_state"),
        sa.CheckConstraint(
            "source IN ('user','model','import')", name="ck_character_evolution_source"
        ),
        sa.CheckConstraint("length(trim(scope)) > 0", name="ck_character_evolution_scope"),
    )
    op.create_index(
        "ix_character_evolution_lookup",
        "character_card_evolution",
        ["world_id", "root_import_id", "field", "scope", "created_at_utc"],
    )


def downgrade():
    op.drop_index("ix_character_evolution_lookup", table_name="character_card_evolution")
    op.drop_table("character_card_evolution")
