"""Retain addition/replacement meaning without activating historical drafts."""

import sqlalchemy as sa
from alembic import op

revision = "0064_character_evolution_kind"
down_revision = "0063_card_packs"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "character_card_evolution", sa.Column("change_kind", sa.String(16), nullable=True)
    )


def downgrade():
    raise RuntimeError("character_evolution_kind_downgrade_not_supported")
