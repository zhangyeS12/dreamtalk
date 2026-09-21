import asyncio
from uuid import uuid4

import pytest
from alembic import command
from alembic.operations import Operations
from livingworld.application.command_handler import CommandHandler
from livingworld.application.commands import (
    AcquireKnowledge,
    AssertWorldTruth,
    CreateCharacter,
    CreateWorld,
)
from livingworld.application.simulation_clock import EffectiveWorldTimeSource, SystemMonotonicClock
from livingworld.domain.contracts import RequestId
from livingworld.domain.identifiers import CharacterId, KnowledgeAssertionId, WorldId
from livingworld.domain.knowledge import ObservationChannel
from livingworld.domain.values import WorldTime
from livingworld.infrastructure.clock import SystemWallClock
from livingworld.infrastructure.persistence import Database
from livingworld.infrastructure.persistence.migration import (
    HEAD_REVISION,
    SPARSE_REVISION,
    _alembic_config,
)
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

MEMORY_TABLES = {"character_memories", "episodic_memory_observation_sources"}
PRESERVED_TABLES = (
    "worlds",
    "characters",
    "world_events",
    "knowledge_assertions",
    "observations",
    "command_receipts",
    "migration_history",
)


async def seed_0013(database: Database) -> tuple[WorldId, CharacterId]:
    async with database.engine.begin() as connection:
        await connection.run_sync(
            lambda sync: command.upgrade(_alembic_config(sync), SPARSE_REVISION)
        )
    world_id = WorldId(uuid4())
    character_id = CharacterId(world_id, uuid4())
    source_id = KnowledgeAssertionId(world_id, uuid4())
    clock = SystemWallClock()
    handler = CommandHandler(
        database.unit_of_work,
        clock,
        world_time_source=EffectiveWorldTimeSource(clock, SystemMonotonicClock()),
    )
    await handler.execute(
        CreateWorld(
            request_id=RequestId(uuid4()),
            world_id=world_id,
            name="Preserved Memory World",
            initial_time=WorldTime(40),
        )
    )
    await handler.execute(
        CreateCharacter(
            request_id=RequestId(uuid4()),
            world_id=world_id,
            character_id=character_id,
            name="Observer",
        )
    )
    await handler.execute(
        AssertWorldTruth(
            request_id=RequestId(uuid4()),
            world_id=world_id,
            assertion_id=source_id,
            subject="gate",
            predicate="state",
            value="open",
            valid_from=WorldTime(20),
        )
    )
    await handler.execute(
        AcquireKnowledge(
            request_id=RequestId(uuid4()),
            world_id=world_id,
            assertion_id=KnowledgeAssertionId(world_id, uuid4()),
            receiver_id=character_id,
            source_assertion_id=source_id,
            channel=ObservationChannel.WITNESSED,
        )
    )
    return world_id, character_id


async def snapshot(database: Database) -> dict[str, list[tuple[object, ...]]]:
    async with database.engine.connect() as connection:
        return {
            table: [
                tuple(row) for row in (await connection.execute(text(f"SELECT * FROM {table}")))
            ]
            for table in PRESERVED_TABLES
        }


def test_0014_upgrade_preserves_stage5_rows_and_restart_is_stable(tmp_path):
    async def run():
        database = Database(tmp_path)
        try:
            await seed_0013(database)
            before = await snapshot(database)
            await database.initialize()
            after = await snapshot(database)
            assert after == before
            async with database.engine.connect() as connection:
                revision = (
                    await connection.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar_one()
                counts = {
                    table: (
                        await connection.execute(text(f"SELECT count(*) FROM {table}"))
                    ).scalar_one()
                    for table in MEMORY_TABLES
                }
                assert not (await connection.execute(text("PRAGMA foreign_key_check"))).all()
            assert revision == HEAD_REVISION
            assert counts == {table: 0 for table in MEMORY_TABLES}

            await database.initialize()
            assert await snapshot(database) == before
            async with database.engine.connect() as connection:
                assert {
                    table: (
                        await connection.execute(text(f"SELECT count(*) FROM {table}"))
                    ).scalar_one()
                    for table in MEMORY_TABLES
                } == counts
        finally:
            await database.close()

    asyncio.run(run())


def test_fresh_database_has_memory_schema_and_indexes(tmp_path):
    async def run():
        database = Database(tmp_path)
        try:
            await database.initialize()
            async with database.engine.connect() as connection:
                tables = set(
                    (
                        await connection.execute(
                            text("SELECT name FROM sqlite_master WHERE type='table'")
                        )
                    )
                    .scalars()
                    .all()
                )
                indexes = set(
                    (
                        await connection.execute(
                            text("SELECT name FROM sqlite_master WHERE type='index'")
                        )
                    )
                    .scalars()
                    .all()
                )
                revision = (
                    await connection.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar_one()
            assert revision == HEAD_REVISION
            assert MEMORY_TABLES <= tables
            assert {
                "ix_character_memories_world_owner",
                "ix_character_memories_owner_experienced",
                "ix_character_memories_owner_formed",
                "ix_episodic_memory_source_observation",
            } <= indexes
        finally:
            await database.close()

    asyncio.run(run())


@pytest.mark.parametrize(
    ("content", "experienced_from", "experienced_to", "formed_at", "salience"),
    [
        ("   ", 20, 20, 40, None),
        ("remembered", 30, 20, 40, None),
        ("remembered", 20, 30, 29, None),
        ("remembered", 20, 20, 40, 101),
    ],
)
def test_0014_database_rejects_invalid_memory_shape(
    tmp_path, content, experienced_from, experienced_to, formed_at, salience
):
    async def run():
        database = Database(tmp_path)
        try:
            world_id, character_id = await seed_0013(database)
            await database.initialize()
            with pytest.raises(IntegrityError):
                async with database.engine.begin() as connection:
                    await connection.execute(
                        text(
                            "INSERT INTO character_memories("
                            "world_id,memory_id,owner_character_id,kind,kind_version,content,"
                            "content_format,content_version,experienced_from,experienced_to,"
                            "formed_at,created_at_utc,salience,provenance_kind,provenance_version) "
                            "VALUES (:world,:memory,:owner,'episodic',1,:content,'plain_text',1,"
                            ":experienced_from,:experienced_to,:formed_at,"
                            "'2026-09-21T12:00:00.000000Z',:salience,'observation_evidence',1)"
                        ),
                        {
                            "world": world_id.value.hex,
                            "memory": uuid4().hex,
                            "owner": character_id.value.hex,
                            "content": content,
                            "experienced_from": experienced_from,
                            "experienced_to": experienced_to,
                            "formed_at": formed_at,
                            "salience": salience,
                        },
                    )
            async with database.engine.connect() as connection:
                assert (
                    await connection.execute(text("SELECT count(*) FROM character_memories"))
                ).scalar_one() == 0
        finally:
            await database.close()

    asyncio.run(run())


def test_0014_controlled_ddl_failure_rolls_back_schema_cursor_and_rows(tmp_path, monkeypatch):
    async def run():
        database = Database(tmp_path)
        try:
            await seed_0013(database)
            before = await snapshot(database)
            original = Operations.create_index

            def fail(self, name, *args, **kwargs):
                if name == "ix_character_memories_owner_experienced":
                    raise RuntimeError("controlled_memory_ddl_failure")
                return original(self, name, *args, **kwargs)

            with monkeypatch.context() as patch:
                patch.setattr(Operations, "create_index", fail)
                with pytest.raises(RuntimeError, match="controlled_memory_ddl_failure"):
                    await database.initialize()
            assert await snapshot(database) == before
            async with database.engine.connect() as connection:
                revision = (
                    await connection.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar_one()
                tables = set(
                    (
                        await connection.execute(
                            text("SELECT name FROM sqlite_master WHERE type='table'")
                        )
                    )
                    .scalars()
                    .all()
                )
            assert revision == SPARSE_REVISION
            assert MEMORY_TABLES.isdisjoint(tables)
            await database.initialize()
        finally:
            await database.close()

    asyncio.run(run())
