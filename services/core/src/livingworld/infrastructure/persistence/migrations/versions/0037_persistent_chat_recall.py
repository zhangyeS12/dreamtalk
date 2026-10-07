"""Add rebuildable FTS/vector projections without rewriting authored or canonical rows."""

import sqlalchemy as sa
from alembic import op

from livingworld.infrastructure.persistence.recall_index_models import FTS_SQL, FTS_TRIGGERS

revision = "0037_persistent_chat_recall"
down_revision = "0036_character_factions"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "recall_documents",
        sa.Column("document_id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("world_id", sa.String(32), nullable=False),
        sa.Column("source_kind", sa.String(8), nullable=False),
        sa.Column("source_id", sa.String(32), nullable=False),
        sa.Column("source_revision", sa.String(96), nullable=False),
        sa.Column("tokens", sa.Text(), nullable=False),
        sa.Column("vector_model", sa.String(96)),
        sa.Column("vector", sa.LargeBinary()),
        sa.UniqueConstraint("world_id", "source_kind", "source_id", name="uq_recall_source"),
        sa.CheckConstraint("source_kind IN ('memory','message')", name="ck_recall_source_kind"),
        sa.CheckConstraint("vector IS NULL OR length(vector) = 2080", name="ck_recall_vector"),
    )
    op.execute(FTS_SQL)
    for statement in FTS_TRIGGERS.values():
        op.execute(statement)
    # Older sources are indexed in bounded, authorized pages during recall.
    # First startup does not read/re-embed the user's entire archive.


def downgrade():
    for name in FTS_TRIGGERS:
        op.execute(f"DROP TRIGGER {name}")
    op.execute("DROP TABLE recall_fts")
    op.drop_table("recall_documents")
