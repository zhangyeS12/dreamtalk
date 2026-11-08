"""Persist group-chat span audiences without changing existing message visibility."""

import sqlalchemy as sa
from alembic import op

revision = "0065_chat_privacy"
down_revision = "0064_character_evolution_kind"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("chat_messages", sa.Column("privacy_json", sa.Text(), nullable=True))


def downgrade():
    raise RuntimeError("chat_privacy_downgrade_not_supported")
