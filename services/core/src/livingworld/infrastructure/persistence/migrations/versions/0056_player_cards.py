"""Store personal cards outside the world's NPC/content catalogs."""

import sqlalchemy as sa
from alembic import op

revision = "0056_player_cards"
down_revision = "0055_world_styles"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "world_player_cards",
        sa.Column("world_id", sa.String(32), primary_key=True),
        sa.Column("player_id", sa.String(32), primary_key=True),
        sa.Column("card_id", sa.String(32), nullable=False),
        sa.Column("content_id", sa.String(32), nullable=False),
        sa.Column("reviewed_hash", sa.String(64), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("raw_payload", sa.LargeBinary(), nullable=False),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["world_id", "player_id"], ["players.world_id", "players.player_id"]
        ),
        sa.CheckConstraint("json_valid(snapshot_json)", name="ck_player_card_json"),
    )


def downgrade():
    raise RuntimeError("player_card_downgrade_not_supported")
