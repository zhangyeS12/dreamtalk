"""SQLite bootstrap: WAL, FTS5 capability and transactional metadata migrations only."""

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    statements: tuple[str, ...]

    @property
    def checksum(self) -> str:
        return hashlib.sha256("\n".join(self.statements).encode()).hexdigest()


MIGRATIONS = (
    Migration(
        1,
        "runtime_metadata",
        (
            "CREATE TABLE schema_version (singleton INTEGER PRIMARY KEY CHECK(singleton = 1), "
            "version INTEGER NOT NULL)",
            "INSERT INTO schema_version VALUES (1, 0)",
            "CREATE TABLE migration_history (version INTEGER PRIMARY KEY, name TEXT NOT NULL, "
            "checksum TEXT NOT NULL, applied_at TEXT NOT NULL)",
        ),
    ),
)


def migrate(connection: sqlite3.Connection, migrations: tuple[Migration, ...] = MIGRATIONS) -> None:
    if [item.version for item in migrations] != list(range(1, len(migrations) + 1)):
        raise RuntimeError("migration_sequence_invalid")
    connection.execute("BEGIN IMMEDIATE")
    try:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_version'"
        ).fetchone()
        version = (
            connection.execute("SELECT version FROM schema_version").fetchone()[0] if exists else 0
        )
        if version > len(migrations):
            raise RuntimeError("schema_version_unsupported")
        for migration in migrations:
            if migration.version <= version:
                row = connection.execute(
                    "SELECT checksum FROM migration_history WHERE version = ?", (migration.version,)
                ).fetchone()
                if row is None or row[0] != migration.checksum:
                    raise RuntimeError("migration_history_mismatch")
                continue
            for statement in migration.statements:
                connection.execute(statement)
            connection.execute(
                "INSERT INTO migration_history VALUES (?, ?, ?, ?)",
                (
                    migration.version,
                    migration.name,
                    migration.checksum,
                    datetime.now(UTC).isoformat(),
                ),
            )
            connection.execute("UPDATE schema_version SET version = ?", (migration.version,))
        connection.commit()
    except BaseException:
        connection.rollback()
        raise


def bootstrap_database(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(data_dir / "runtime.sqlite3", isolation_level=None) as connection:
        connection.execute("PRAGMA busy_timeout = 5000")
        if connection.execute("PRAGMA journal_mode = WAL").fetchone()[0].lower() != "wal":
            raise RuntimeError("wal_unavailable")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("CREATE VIRTUAL TABLE temp.fts5_probe USING fts5(value)")
        migrate(connection)
