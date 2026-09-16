import sqlite3

import pytest
from livingworld.infrastructure.database import Migration, bootstrap_database, migrate


def test_sqlite_wal_enabled(tmp_path):
    bootstrap_database(tmp_path)
    with sqlite3.connect(tmp_path / "runtime.sqlite3") as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        connection.execute("CREATE VIRTUAL TABLE temp.fts_probe USING fts5(value)")


def test_migration_bootstrap_and_repeat(tmp_path):
    bootstrap_database(tmp_path)
    bootstrap_database(tmp_path)
    with sqlite3.connect(tmp_path / "runtime.sqlite3") as connection:
        assert connection.execute("SELECT version FROM schema_version").fetchall() == [(1,)]
        assert connection.execute("SELECT COUNT(*) FROM migration_history").fetchone()[0] == 1
        assert {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        } == {
            "schema_version",
            "migration_history",
        }


def test_migration_checksum_detects_drift(tmp_path):
    bootstrap_database(tmp_path)
    with sqlite3.connect(tmp_path / "runtime.sqlite3") as connection:
        connection.execute("UPDATE migration_history SET checksum='tampered'")
    with pytest.raises(RuntimeError, match="migration_history_mismatch"):
        bootstrap_database(tmp_path)


def test_migration_failure_rolls_back(tmp_path):
    migration = Migration(
        1, "invalid", ("CREATE TABLE schema_version(version INTEGER)", "INVALID SQL")
    )
    with sqlite3.connect(tmp_path / "rollback.sqlite3", isolation_level=None) as connection:
        with pytest.raises(sqlite3.Error):
            migrate(connection, (migration,))
        assert connection.execute("SELECT name FROM sqlite_master").fetchall() == []
