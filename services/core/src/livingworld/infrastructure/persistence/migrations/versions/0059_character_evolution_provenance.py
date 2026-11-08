"""Retain evidence metadata for model character-card suggestions."""

import sqlalchemy as sa
from alembic import op

revision = "0059_character_evolution_provenance"
down_revision = "0058_character_evolution"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "character_card_evolution",
        sa.Column("quote", sa.Text(), nullable=True),
    )
    op.add_column(
        "character_card_evolution",
        sa.Column("confidence", sa.Float(), nullable=True),
    )


def downgrade():
    raise RuntimeError("character_evolution_provenance_downgrade_not_supported")
