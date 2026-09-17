"""Represent the C-002 runtime metadata schema as the Alembic baseline."""

from datetime import UTC, datetime

from alembic import op
from sqlalchemy import text

revision = "0001_legacy_runtime_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE schema_version (singleton INTEGER PRIMARY KEY CHECK(singleton = 1), "
        "version INTEGER NOT NULL)"
    )
    op.execute("INSERT INTO schema_version VALUES (1, 1)")
    op.execute(
        "CREATE TABLE migration_history (version INTEGER PRIMARY KEY, name TEXT NOT NULL, "
        "checksum TEXT NOT NULL, applied_at TEXT NOT NULL)"
    )
    op.get_bind().execute(
        text(
            "INSERT INTO migration_history (version, name, checksum, applied_at) "
            "VALUES (:version, :name, :checksum, :applied_at)"
        ),
        {
            "version": 1,
            "name": "runtime_metadata",
            "checksum": "0345ec9d50fd45b01ba0f97ff6f14a25f683fb8d01f08f04ff9dc4892ad1cac5",
            "applied_at": datetime.now(UTC).isoformat(),
        },
    )


def downgrade() -> None:
    op.drop_table("migration_history")
    op.drop_table("schema_version")
