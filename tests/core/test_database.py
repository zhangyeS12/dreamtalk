import asyncio
import sqlite3

import pytest
from alembic.operations import Operations
from livingworld.infrastructure.database import bootstrap_database
from livingworld.infrastructure.persistence.migration import HEAD_REVISION


def bootstrap(tmp_path):
    async def run():
        database = await bootstrap_database(tmp_path)
        await database.close()

    asyncio.run(run())


def test_sqlite_wal_enabled(tmp_path):
    bootstrap(tmp_path)
    with sqlite3.connect(tmp_path / "runtime.sqlite3") as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        connection.execute("CREATE VIRTUAL TABLE temp.fts_probe USING fts5(value)")


def test_migration_bootstrap_and_repeat(tmp_path):
    bootstrap(tmp_path)
    bootstrap(tmp_path)
    with sqlite3.connect(tmp_path / "runtime.sqlite3") as connection:
        assert connection.execute("SELECT version FROM schema_version").fetchall() == [(1,)]
        assert connection.execute("SELECT COUNT(*) FROM migration_history").fetchone()[0] == 1
        assert connection.execute("SELECT version_num FROM alembic_version").fetchall() == [
            (HEAD_REVISION,)
        ]


def test_migration_checksum_detects_drift(tmp_path):
    bootstrap(tmp_path)
    with sqlite3.connect(tmp_path / "runtime.sqlite3") as connection:
        connection.execute("UPDATE migration_history SET checksum='tampered'")
    with pytest.raises(RuntimeError, match="legacy_checksum_mismatch"):
        bootstrap(tmp_path)


def test_migration_failure_rolls_back(tmp_path, monkeypatch):
    original = Operations.create_table

    def fail(self, table_name, *args, **kwargs):
        if table_name == "characters":
            raise RuntimeError("injected_migration_failure")
        return original(self, table_name, *args, **kwargs)

    monkeypatch.setattr(Operations, "create_table", fail)
    with pytest.raises(RuntimeError, match="injected_migration_failure"):
        bootstrap(tmp_path)
    with sqlite3.connect(tmp_path / "runtime.sqlite3") as connection:
        assert connection.execute("SELECT name FROM sqlite_master").fetchall() == []
