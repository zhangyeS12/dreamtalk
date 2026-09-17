"""Upgrade the actual pre-position schema, preserving historical rows and rowids."""

import asyncio
from datetime import UTC, datetime, timedelta
from importlib import import_module
from uuid import UUID

import pytest
from alembic import command
from livingworld.application.command_handler import CommandHandler
from livingworld.application.commands import (
    CreateCharacter,
    CreateLocation,
    CreatePlayer,
    CreateWorld,
)
from livingworld.domain.contracts import RequestId
from livingworld.domain.identifiers import CharacterId, LocationId, PlayerId, WorldId
from livingworld.domain.values import WorldTime
from livingworld.infrastructure.persistence import Database
from livingworld.infrastructure.persistence.mapping import to_record
from livingworld.infrastructure.persistence.migration import (
    HEAD_REVISION,
    OBSERVATION_REVISION,
    _alembic_config,
)
from livingworld.infrastructure.persistence.models import WorldEventRecord
from livingworld.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from sqlalchemy import text


class _LegacyEventAppender:
    """Test-only reproduction of C-003D's append path on its historical schema."""

    def __init__(self, session):
        self.session = session

    async def append(self, event):
        record = to_record(event)
        values = {
            column.name: getattr(record, column.name)
            for column in WorldEventRecord.__table__.columns
            if column.name != "ledger_position"
        }
        await self.session.execute(WorldEventRecord.__table__.insert().values(**values))


class _LegacyUnitOfWork(SqlAlchemyUnitOfWork):
    async def __aenter__(self):
        await super().__aenter__()
        self.events = _LegacyEventAppender(self._session)
        return self


class _Clock:
    value = datetime(2026, 9, 17, tzinfo=UTC)

    def now_utc(self):
        self.value -= timedelta(days=1)
        return self.value


async def seed_0004(database, empty=False):
    async with database.engine.begin() as connection:
        await connection.run_sync(
            lambda sync: command.upgrade(_alembic_config(sync), OBSERVATION_REVISION)
        )
    if empty:
        return None
    handler = CommandHandler(lambda: _LegacyUnitOfWork(database._sessions), _Clock())
    a, b = WorldId(UUID("f" * 32)), WorldId(UUID("a" * 32))
    home_a, home_b = LocationId(a, UUID(int=20)), LocationId(b, UUID(int=20))
    commands = [
        CreateWorld(
            request_id=RequestId(UUID(int=1)),
            world_id=a,
            name="Legacy A",
            initial_time=WorldTime(900),
        ),
        CreateWorld(
            request_id=RequestId(UUID(int=2)),
            world_id=b,
            name="Legacy B",
            initial_time=WorldTime(-7),
        ),
        CreateLocation(
            request_id=RequestId(UUID(int=3)), world_id=a, location_id=home_a, name="A Home"
        ),
        CreateLocation(
            request_id=RequestId(UUID(int=4)), world_id=b, location_id=home_b, name="B Home"
        ),
        CreatePlayer(
            request_id=RequestId(UUID(int=5)),
            world_id=a,
            player_id=PlayerId(a, UUID(int=30)),
            name="Legacy Player",
            initial_location_id=home_a,
        ),
        CreateCharacter(
            request_id=RequestId(UUID(int=6)),
            world_id=b,
            character_id=CharacterId(b, UUID(int=30)),
            name="Legacy Character",
        ),
    ]
    for item in commands:
        await handler.execute(item)
    return a, b


async def event_rows(database):
    async with database.engine.connect() as connection:
        return [
            dict(row)
            for row in (
                await connection.execute(
                    text("SELECT _rowid_ AS legacy_rowid,* FROM world_events ORDER BY _rowid_")
                )
            ).mappings()
        ]


async def metadata(database):
    async with database.engine.connect() as connection:
        return {
            table: (await connection.execute(text(f"SELECT * FROM {table}"))).all()
            for table in (
                "schema_version",
                "migration_history",
                "command_receipts",
                "alembic_version",
            )
        }


def test_legacy_rowid_backfill_preserves_records_and_future_append(tmp_path):
    async def run():
        mappings = []
        for directory in (tmp_path / "first", tmp_path / "second"):
            database = Database(directory)
            try:
                a, b = await seed_0004(database)
                before = await event_rows(database)
                old_audit = await metadata(database)
                await database.initialize()
                after = await event_rows(database)
                assert [
                    {key: value for key, value in row.items() if key != "ledger_position"}
                    for row in after
                ] == before
                for world in (a, b):
                    rows = [row for row in after if row["world_id"] == world.value.hex]
                    assert [row["ledger_position"] for row in rows] == list(range(1, len(rows) + 1))
                # Timestamps intentionally go backwards; worlds and event UUIDs also
                # interleave. Only each world's historical insertion evidence is used.
                assert after[0]["created_at"] > after[-1]["created_at"]
                assert after[0]["world_id"] > after[1]["world_id"]
                mappings.append(
                    [(row["world_id"], row["event_id"], row["ledger_position"]) for row in after]
                )
                current_audit = await metadata(database)
                for table in ("schema_version", "migration_history", "command_receipts"):
                    assert current_audit[table] == old_audit[table]
                assert current_audit["alembic_version"] == [(HEAD_REVISION,)]
                await database.initialize()
                assert await event_rows(database) == after
                assert await metadata(database) == current_audit
                max_a = max(
                    row["ledger_position"] for row in after if row["world_id"] == a.value.hex
                )
                handler = CommandHandler(database.unit_of_work, _Clock())
                await handler.execute(
                    CreateLocation(
                        request_id=RequestId(UUID(int=100)),
                        world_id=a,
                        location_id=LocationId(a, UUID(int=40)),
                        name="After takeover",
                    )
                )
                entries = await database.canonical_event_reader(a).read()
                assert entries[-1].ledger_position == max_a + 1
                assert entries[-1].event.event_type == "LocationCreated"
                async with database.engine.connect() as connection:
                    assert not (await connection.execute(text("PRAGMA foreign_key_check"))).all()
            finally:
                await database.close()
        assert mappings[0] == mappings[1]

    asyncio.run(run())


def test_empty_database_reaches_head_with_empty_ledger_cursor(tmp_path):
    async def run():
        database = Database(tmp_path)
        try:
            await database.initialize()
            async with database.engine.connect() as connection:
                assert (
                    await connection.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar_one() == HEAD_REVISION
                assert not (await connection.execute(text("SELECT * FROM world_events"))).all()
                assert not (
                    await connection.execute(text("SELECT * FROM world_ledger_cursors"))
                ).all()
                assert (
                    len((await connection.execute(text("SELECT * FROM migration_history"))).all())
                    == 1
                )
        finally:
            await database.close()

    asyncio.run(run())


def test_backfill_failure_rolls_back_ddl_rows_triggers_and_cursor(tmp_path, monkeypatch):
    async def run():
        database = Database(tmp_path)
        try:
            await seed_0004(database)
            before, audit = await event_rows(database), await metadata(database)
            migration = import_module(
                "livingworld.infrastructure.persistence.migrations.versions.0005_canonical_ledger"
            )
            original = migration.op.create_index

            def fail(name, *args, **kwargs):
                if name == "uq_world_event_ledger_position":
                    raise RuntimeError("injected after position backfill")
                return original(name, *args, **kwargs)

            with monkeypatch.context() as context:
                context.setattr(migration.op, "create_index", fail)
                with pytest.raises(RuntimeError, match="injected"):
                    await database.initialize()
            assert await event_rows(database) == before
            assert await metadata(database) == audit
            async with database.engine.connect() as connection:
                assert (
                    await connection.execute(
                        text("SELECT name FROM sqlite_master WHERE name='world_ledger_cursors'")
                    )
                ).all() == []
                assert set(
                    (
                        await connection.execute(
                            text(
                                "SELECT name FROM sqlite_master WHERE type='trigger' "
                                "AND tbl_name='world_events'"
                            )
                        )
                    ).scalars()
                ) == {"world_events_no_update", "world_events_no_delete"}
            await database.initialize()
        finally:
            await database.close()

    asyncio.run(run())


def test_unavailable_legacy_rowid_fails_closed(tmp_path):
    async def run():
        database = Database(tmp_path)
        try:
            await seed_0004(database, empty=True)
            async with database.engine.begin() as connection:
                ddl = (
                    await connection.execute(
                        text("SELECT sql FROM sqlite_master WHERE name='world_events'")
                    )
                ).scalar_one()
                triggers = (
                    (
                        await connection.execute(
                            text(
                                "SELECT sql FROM sqlite_master WHERE type='trigger' "
                                "AND tbl_name='world_events'"
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                indexes = (
                    (
                        await connection.execute(
                            text(
                                "SELECT sql FROM sqlite_master WHERE type='index' "
                                "AND tbl_name='world_events' AND sql IS NOT NULL"
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                await connection.execute(text("DROP TABLE world_events"))
                await connection.execute(text(ddl + " WITHOUT ROWID"))
                for trigger in triggers:
                    await connection.execute(text(trigger))
                for index in indexes:
                    await connection.execute(text(index))
            with pytest.raises(RuntimeError, match="legacy_event_insertion_order_unavailable"):
                await database.initialize()
            async with database.engine.connect() as connection:
                assert (
                    await connection.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar_one() == OBSERVATION_REVISION
                assert "ledger_position" not in {
                    row[1]
                    for row in (
                        await connection.execute(text("PRAGMA table_info(world_events)"))
                    ).all()
                }
        finally:
            await database.close()

    asyncio.run(run())
