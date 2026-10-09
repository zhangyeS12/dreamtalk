"""Explicit whole-world erasure and group dissolution without memory loss."""

import sqlalchemy as sa
from alembic import op

from livingworld.infrastructure.persistence.deletion_models import (
    WORLD_DELETE_TRIGGER,
    WORLD_RECREATE_TRIGGER,
)

revision = "0042_world_deletion"
down_revision = "0041_director_rotation"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "group_dissolutions",
        sa.Column("world_id", sa.String(32), primary_key=True),
        sa.Column("conversation_id", sa.String(32), primary_key=True),
        sa.Column("dissolved_at", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(
            ["world_id", "conversation_id"],
            ["chat_conversations.world_id", "chat_conversations.conversation_id"],
        ),
    )
    op.create_table(
        "world_deletions",
        sa.Column("world_id", sa.String(32), primary_key=True),
        sa.Column("deleted_at", sa.String(32), nullable=False),
        sa.Column("pending_assets_json", sa.Text(), nullable=False),
    )
    op.execute("DROP TRIGGER world_events_no_delete")
    op.execute(WORLD_DELETE_TRIGGER)
    op.execute(WORLD_RECREATE_TRIGGER)


def downgrade():
    op.execute("DROP TRIGGER worlds_no_recreate")
    op.execute("DROP TRIGGER world_events_no_delete")
    op.execute(
        "CREATE TRIGGER world_events_no_delete BEFORE DELETE ON world_events "
        "BEGIN SELECT RAISE(ABORT, 'world_event_immutable'); END"
    )
    op.drop_table("world_deletions")
    op.drop_table("group_dissolutions")
