import asyncio
import sqlite3
from datetime import datetime

import pytest
from alembic import command
from alembic.operations import Operations
from livingworld.infrastructure.persistence import Database
from livingworld.infrastructure.persistence.errors import MigrationCompatibilityError
from livingworld.infrastructure.persistence.migration import (
    HEAD_REVISION,
    LEGACY_CHECKSUM,
    LEGACY_REVISION,
)

SCHEMA_SQL = (
    "CREATE TABLE schema_version (singleton INTEGER PRIMARY KEY CHECK(singleton = 1), "
    "version INTEGER NOT NULL)"
)
HISTORY_SQL = (
    "CREATE TABLE migration_history (version INTEGER PRIMARY KEY, name TEXT NOT NULL, "
    "checksum TEXT NOT NULL, applied_at TEXT NOT NULL)"
)
AUDIT_ROW = (1, "runtime_metadata", LEGACY_CHECKSUM, "2026-01-01T00:00:00.123456+00:00")


def seed_legacy(tmp_path):
    with sqlite3.connect(tmp_path / "runtime.sqlite3") as connection:
        connection.execute(SCHEMA_SQL)
        connection.execute("INSERT INTO schema_version VALUES (1, 1)")
        connection.execute(HISTORY_SQL)
        connection.execute("INSERT INTO migration_history VALUES (?, ?, ?, ?)", AUDIT_ROW)


def initialize(tmp_path):
    async def run():
        database = Database(tmp_path)
        try:
            await database.initialize()
        finally:
            await database.close()

    asyncio.run(run())


def test_fresh_upgrade_head(tmp_path):
    initialize(tmp_path)
    with sqlite3.connect(tmp_path / "runtime.sqlite3") as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchall() == [
            (HEAD_REVISION,)
        ]
        assert connection.execute("SELECT COUNT(*) FROM worlds").fetchone() == (0,)
        applied = connection.execute("SELECT applied_at FROM migration_history").fetchone()[0]
        assert datetime.fromisoformat(applied).tzinfo is not None


def test_verified_legacy_stamped_and_rows_preserved(tmp_path, monkeypatch):
    seed_legacy(tmp_path)
    stamps = []
    original = command.stamp

    def stamp(config, revision, *args, **kwargs):
        stamps.append(revision)
        return original(config, revision, *args, **kwargs)

    monkeypatch.setattr(command, "stamp", stamp)
    initialize(tmp_path)
    assert stamps == [LEGACY_REVISION]
    with sqlite3.connect(tmp_path / "runtime.sqlite3") as connection:
        assert connection.execute("SELECT * FROM migration_history").fetchall() == [AUDIT_ROW]
        assert connection.execute("SELECT * FROM schema_version").fetchall() == [(1, 1)]
        assert connection.execute("SELECT version_num FROM alembic_version").fetchall() == [
            (HEAD_REVISION,)
        ]


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        ("UPDATE migration_history SET checksum='tampered'", "legacy_checksum_mismatch"),
        ("UPDATE schema_version SET version=9", "legacy_schema_version_unsupported"),
        ("ALTER TABLE schema_version ADD COLUMN extra TEXT", "legacy_schema_shape_mismatch"),
        ("DROP TABLE migration_history", "legacy_schema_ambiguous"),
        ("DELETE FROM migration_history", "legacy_migration_history_mismatch"),
        ("UPDATE migration_history SET applied_at='not-a-timestamp'", "history_corrupt"),
        ("UPDATE migration_history SET applied_at='2026-01-01T00:00:00'", "history_corrupt"),
        ("CREATE TABLE worlds (world_id TEXT)", "legacy_schema_ambiguous"),
        ("CREATE VIEW unexpected AS SELECT 1", "migration_schema_objects_mismatch"),
    ],
)
def test_ambiguous_legacy_fails_without_stamp(tmp_path, mutation, error):
    seed_legacy(tmp_path)
    with sqlite3.connect(tmp_path / "runtime.sqlite3") as connection:
        connection.execute(mutation)
        before = connection.execute("SELECT name, sql FROM sqlite_master ORDER BY name").fetchall()
    with pytest.raises(MigrationCompatibilityError, match=error):
        initialize(tmp_path)
    with sqlite3.connect(tmp_path / "runtime.sqlite3") as connection:
        assert (
            connection.execute("SELECT name, sql FROM sqlite_master ORDER BY name").fetchall()
            == before
        )


def test_legacy_missing_check_constraint_rejected(tmp_path):
    seed_legacy(tmp_path)
    with sqlite3.connect(tmp_path / "runtime.sqlite3") as connection:
        connection.execute("ALTER TABLE schema_version RENAME TO old_version")
        connection.execute(
            "CREATE TABLE schema_version (singleton INTEGER PRIMARY KEY, version INTEGER NOT NULL)"
        )
        connection.execute("INSERT INTO schema_version SELECT * FROM old_version")
        connection.execute("DROP TABLE old_version")
    with pytest.raises(MigrationCompatibilityError, match="legacy_schema_shape_mismatch"):
        initialize(tmp_path)


def test_repeated_startup_no_replay_or_duplicate_audit(tmp_path, monkeypatch):
    seed_legacy(tmp_path)
    initialize(tmp_path)

    def unexpected_stamp(*args, **kwargs):
        pytest.fail("Alembic-managed restart must not stamp from legacy metadata")

    monkeypatch.setattr(command, "stamp", unexpected_stamp)
    calls = []
    original = command.upgrade

    def upgrade(config, target):
        calls.append(target)
        return original(config, target)

    monkeypatch.setattr(command, "upgrade", upgrade)
    initialize(tmp_path)
    initialize(tmp_path)
    assert calls == ["head", "head"]
    with sqlite3.connect(tmp_path / "runtime.sqlite3") as connection:
        assert connection.execute("SELECT * FROM migration_history").fetchall() == [AUDIT_ROW]


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        ("UPDATE schema_version SET version=2", "legacy_schema_version_unsupported"),
        ("UPDATE alembic_version SET version_num='unknown'", "alembic_revision_unsupported"),
        (
            f"UPDATE alembic_version SET version_num='{LEGACY_REVISION}'",
            "alembic_schema_state_mismatch",
        ),
        ("DROP TABLE player_presences", "alembic_schema_state_mismatch"),
        ("DROP TRIGGER world_events_no_update", "migration_schema_objects_mismatch"),
        ("DELETE FROM alembic_version", "alembic_cursor_corrupt"),
    ],
)
def test_mixed_or_partial_managed_state_fails_explicitly(tmp_path, mutation, error):
    initialize(tmp_path)
    with sqlite3.connect(tmp_path / "runtime.sqlite3") as connection:
        connection.execute(mutation)
    with pytest.raises(MigrationCompatibilityError, match=error):
        initialize(tmp_path)


@pytest.mark.parametrize("legacy", [False, True])
def test_alembic_failure_rolls_back_ddl_and_takeover(tmp_path, monkeypatch, legacy):
    if legacy:
        seed_legacy(tmp_path)
    original = Operations.create_table

    def fail_after_some_ddl(self, table_name, *args, **kwargs):
        if table_name == "locations":
            raise RuntimeError("injected_migration_failure")
        return original(self, table_name, *args, **kwargs)

    monkeypatch.setattr(Operations, "create_table", fail_after_some_ddl)
    with pytest.raises(RuntimeError, match="injected_migration_failure"):
        initialize(tmp_path)
    with sqlite3.connect(tmp_path / "runtime.sqlite3") as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert tables == ({"schema_version", "migration_history"} if legacy else set())
        if legacy:
            assert connection.execute("SELECT * FROM migration_history").fetchall() == [AUDIT_ROW]
