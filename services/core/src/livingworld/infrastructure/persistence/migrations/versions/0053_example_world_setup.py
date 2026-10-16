"""Keep interrupted built-in example creation resumable and hidden until ready."""

import sqlalchemy as sa
from alembic import op

revision = "0053_example_world_setup"
down_revision = "0052_sticker_entry_description"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "example_world_setups",
        sa.Column("request_id", sa.String(32), primary_key=True),
        sa.Column("world_id", sa.String(32), nullable=False, unique=True),
        sa.Column("template_id", sa.String(32), nullable=False),
        sa.Column("reviewed_hash", sa.String(64), nullable=False),
        sa.Column("public_entries_json", sa.Text(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.CheckConstraint("state IN ('pending','complete')", name="ck_example_setup_state"),
        sa.CheckConstraint("length(reviewed_hash) = 64", name="ck_example_setup_hash"),
        sa.CheckConstraint("json_valid(public_entries_json)", name="ck_example_setup_entries"),
    )


def downgrade():
    raise RuntimeError("example_world_setup_downgrade_not_supported")
