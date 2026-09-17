import asyncio
import json
import sqlite3
import subprocess
import sys
from dataclasses import replace
from uuid import uuid4

import pytest
from alembic import command
from livingworld.domain.contracts import API_PROTOCOL
from livingworld.domain.identifiers import EventId
from livingworld.infrastructure.persistence import Database
from livingworld.infrastructure.persistence.errors import MigrationCompatibilityError
from livingworld.infrastructure.persistence.migration import (
    HEAD_REVISION,
    LEGACY_REVISION,
    _alembic_config,
)
from livingworld.infrastructure.persistence.models import CommandReceiptRecord
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


def test_alembic_baseline_database_upgrades_without_legacy_stamp(tmp_path, monkeypatch):
    async def run():
        database = Database(tmp_path)
        try:
            async with database.engine.begin() as connection:
                await connection.run_sync(
                    lambda sync: command.upgrade(_alembic_config(sync), LEGACY_REVISION)
                )

            def unexpected_stamp(*args, **kwargs):
                pytest.fail("An Alembic cursor must be used directly")

            monkeypatch.setattr(command, "stamp", unexpected_stamp)
            await database.initialize()
            await database.initialize()
            async with database.engine.connect() as connection:
                assert (
                    await connection.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar_one() == HEAD_REVISION
                assert (
                    await connection.execute(text("SELECT COUNT(*) FROM migration_history"))
                ).scalar_one() == 1
        finally:
            await database.close()

    asyncio.run(run())


def test_equal_world_time_is_not_event_identity(tmp_path, objects, populate):
    async def run():
        database = Database(tmp_path)
        try:
            await database.initialize()
            store = await populate(database)
            for _ in range(2):
                event = replace(
                    objects["event"],
                    event_id=EventId(objects["world"].world_id, uuid4()),
                    idempotency_key=None,
                )
                await store.add(event)
                assert await store.reload(event) == event
        finally:
            await database.close()

    asyncio.run(run())


@pytest.mark.parametrize(
    "changes",
    [
        {"result_kind": None},
        {"result_kind": "unknown"},
        {"result_id": None},
    ],
)
def test_command_receipt_partial_result_rejected(tmp_path, objects, populate, changes):
    async def run():
        database = Database(tmp_path)
        try:
            await database.initialize()
            await populate(database)
            with pytest.raises(IntegrityError, match="ck_command_receipt_result"):
                async with database.engine.begin() as connection:
                    await connection.execute(
                        CommandReceiptRecord.__table__.update().values(**changes)
                    )
        finally:
            await database.close()

    asyncio.run(run())


def test_world_event_replace_also_rejected(tmp_path, objects, populate):
    async def run():
        database = Database(tmp_path)
        try:
            await database.initialize()
            store = await populate(database)
            with pytest.raises(IntegrityError, match="world_event_immutable"):
                async with database.engine.begin() as connection:
                    await connection.execute(
                        text(
                            "INSERT OR REPLACE INTO world_events "
                            "SELECT world_id, event_id, 'changed', occurred_at, "
                            "payload, payload_version, causation_event_id, "
                            "causation_request_id, correlation_id, idempotency_key, "
                            "created_at, ledger_position FROM world_events WHERE event_id=:event_id"
                        ),
                        {"event_id": objects["event"].event_id.value.hex},
                    )
            assert await store.reload(objects["event"]) == objects["event"]
        finally:
            await database.close()

    asyncio.run(run())


def test_core_stops_on_invalid_legacy_and_clears_stale_ready(tmp_path):
    data_dir = tmp_path / "data"

    async def baseline():
        database = Database(data_dir)
        try:
            async with database.engine.begin() as connection:
                await connection.run_sync(
                    lambda sync: command.upgrade(_alembic_config(sync), LEGACY_REVISION)
                )
        finally:
            await database.close()

    asyncio.run(baseline())
    with sqlite3.connect(data_dir / "runtime.sqlite3") as connection:
        connection.execute("DROP TABLE alembic_version")
        connection.execute("UPDATE migration_history SET checksum='corrupt'")
    path = tmp_path / "bootstrap.json"
    secret = "isolated-compatibility-test-secret-" * 3
    path.write_text(
        json.dumps(
            {
                "bootstrap_secret": secret,
                "instance_nonce": str(uuid4()),
                "protocol_min": API_PROTOCOL,
                "protocol_max": API_PROTOCOL,
                "data_dir": str(data_dir),
                "log_dir": str(tmp_path / "logs"),
            }
        ),
        encoding="utf-8",
    )
    ready = tmp_path / "ready.json"
    ready.write_text("stale", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "livingworld.bootstrap", "--bootstrap-path", str(path)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 1
    assert not ready.exists()
    assert secret not in result.stdout + result.stderr
    assert "startup_or_runtime_failed" in result.stdout
    assert "legacy_checksum_mismatch" in result.stdout
    log = next((tmp_path / "logs").glob("core-*.jsonl")).read_text(encoding="utf-8")
    assert "legacy_checksum_mismatch" in log and secret not in log
    with sqlite3.connect(data_dir / "runtime.sqlite3") as connection:
        assert connection.execute("SELECT checksum FROM migration_history").fetchone() == (
            "corrupt",
        )
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE name='alembic_version'"
            ).fetchall()
            == []
        )


@pytest.mark.parametrize("literal", ["'RUNNING'", "'run ning'"])
def test_managed_check_literal_drift_rejected(tmp_path, literal):
    async def initialize():
        database = Database(tmp_path)
        try:
            await database.initialize()
        finally:
            await database.close()

    asyncio.run(initialize())
    with sqlite3.connect(tmp_path / "runtime.sqlite3") as connection:
        ddl = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name='world_clocks'"
        ).fetchone()[0]
        assert "'running'" in ddl
        connection.execute("DROP TABLE world_clocks")
        connection.execute(ddl.replace("'running'", literal))
    with pytest.raises(MigrationCompatibilityError, match="alembic_schema_shape_mismatch"):
        asyncio.run(initialize())


def test_wrong_cursor_after_upgrade_rolls_back(tmp_path, monkeypatch):
    original = command.upgrade

    def upgrade_with_cursor_fault(config, target):
        original(config, target)
        command.stamp(config, LEGACY_REVISION)

    monkeypatch.setattr(command, "upgrade", upgrade_with_cursor_fault)

    async def run():
        database = Database(tmp_path)
        try:
            with pytest.raises(MigrationCompatibilityError, match="alembic_schema_state_mismatch"):
                await database.initialize()
        finally:
            await database.close()

    asyncio.run(run())
    with sqlite3.connect(tmp_path / "runtime.sqlite3") as connection:
        assert (
            connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == []
        )
