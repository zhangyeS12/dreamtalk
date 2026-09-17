import asyncio
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from livingworld.domain.commands import CommandReceipt
from livingworld.domain.contracts import RequestId
from livingworld.domain.identifiers import CharacterId, EventId, KnowledgeAssertionId, PlayerId
from livingworld.domain.knowledge import ObservationChannel
from livingworld.domain.values import Revision, WorldTime
from livingworld.domain.world import ClockState
from livingworld.infrastructure.persistence import Database
from livingworld.infrastructure.persistence.errors import (
    PersistenceConflictError,
    PersistenceDataError,
)
from livingworld.infrastructure.persistence.mapping import to_record
from livingworld.infrastructure.persistence.models import WorldClockRecord
from livingworld.infrastructure.persistence.types import SQLITE_INT64_MAX, SQLITE_INT64_MIN
from sqlalchemy import insert, text
from sqlalchemy.exc import StatementError


def test_all_domain_snapshots_roundtrip_and_restart(tmp_path, objects, populate):
    async def run():
        database = Database(tmp_path)
        try:
            await database.initialize()
            store = await populate(database)
            expected = list(objects.values()) + [objects["world"].clock]
            for entity in expected:
                loaded = await store.reload(entity)
                assert loaded == entity
                assert type(loaded) is type(entity)
            event = await store.reload(objects["event"])
            assert event.occurred_at.microseconds == 2**53 + 123
            assert isinstance(event.event_id, EventId)
            assert isinstance(event.causation_id, RequestId)
            assert (await store.reload(objects["caused_event"])).causation_id == objects[
                "event"
            ].event_id
            assert isinstance((await store.reload(objects["alice"])).character_id, CharacterId)
            assert isinstance((await store.reload(objects["player"])).player_id, PlayerId)
            knowledge = await store.reload(objects["belief"])
            assert isinstance(knowledge.assertion_id, KnowledgeAssertionId)
            assert isinstance(knowledge.owner, CharacterId)
            assert knowledge.confidence == Decimal("0.1234567890123456789")
            assert knowledge.revision == Revision(17)
            assert (await store.reload(objects["presence"])).location_id == objects[
                "location"
            ].location_id
            assert event.created_at.tzinfo is UTC
            assert event.payload_version == 3
            assert event.correlation_id == objects["event"].correlation_id
            with pytest.raises(TypeError):
                event.payload["unexpected"] = True
            with pytest.raises(FrozenInstanceError):
                event.event_type = "changed"
        finally:
            await database.close()
        restarted = Database(tmp_path)
        try:
            await restarted.initialize()
            for entity in expected:
                assert await restarted.store().reload(entity) == entity
        finally:
            await restarted.close()

    asyncio.run(run())


@pytest.mark.parametrize("microseconds", [SQLITE_INT64_MIN, -1, 0, 2**53 + 1, SQLITE_INT64_MAX])
def test_world_clock_signed_integer_exactness(tmp_path, objects, microseconds):
    async def run():
        database = Database(tmp_path)
        try:
            await database.initialize()
            clock = replace(
                objects["world"].clock,
                logical_time=WorldTime(microseconds),
                state=ClockState.RUNNING,
            )
            world = replace(objects["world"], clock=clock)
            await database.store().add(world)
            assert await database.store().reload(clock) == clock
            async with database.engine.connect() as connection:
                assert (
                    await connection.execute(
                        text("SELECT logical_time, typeof(logical_time) FROM world_clocks")
                    )
                ).one() == (microseconds, "integer")
        finally:
            await database.close()

    asyncio.run(run())


@pytest.mark.parametrize("microseconds", [SQLITE_INT64_MIN - 1, SQLITE_INT64_MAX + 1])
def test_unrepresentable_world_time_rejected_without_rounding(tmp_path, objects, microseconds):
    async def run():
        database = Database(tmp_path)
        try:
            await database.initialize()
            world = replace(
                objects["world"],
                clock=replace(objects["world"].clock, logical_time=WorldTime(microseconds)),
            )
            with pytest.raises(StatementError, match="world_time_outside_sqlite_integer_range"):
                await database.store().add(world)
            assert await database.store().reload(world) is None
        finally:
            await database.close()

    asyncio.run(run())


def test_naive_datetime_rejected_on_bind_and_load(tmp_path, objects):
    async def run():
        database = Database(tmp_path)
        try:
            await database.initialize()
            await database.store().add(objects["world"])
            async with database.engine.begin() as connection:
                await connection.execute(
                    text("UPDATE world_clocks SET observed_wall_time_utc='2026-09-17T00:00:00'")
                )
            with pytest.raises(PersistenceDataError, match="stored_timestamp_not_utc_aware"):
                await database.store().reload(objects["world"].clock)
            record = to_record(objects["world"].clock)
            record.observed_wall_time_utc = datetime(2026, 9, 17)
            with pytest.raises(StatementError, match="timezone-aware"):
                async with database.engine.begin() as connection:
                    await connection.execute(
                        insert(WorldClockRecord).values(
                            world_id=record.world_id,
                            logical_time=record.logical_time,
                            observed_wall_time_utc=record.observed_wall_time_utc,
                            time_scale=record.time_scale,
                            state=record.state,
                            revision=record.revision,
                        )
                    )
        finally:
            await database.close()

    asyncio.run(run())


@pytest.mark.parametrize("channel", list(ObservationChannel))
def test_observation_channels_roundtrip_without_propagation(tmp_path, objects, populate, channel):
    async def run():
        database = Database(tmp_path)
        try:
            await database.initialize()
            store = await populate(database)
            observation = replace(objects["observation"], channel=channel, observed_at=WorldTime(1))
            await store.add(observation)
            assert await store.reload(observation) == observation
            async with database.engine.connect() as connection:
                assert (
                    await connection.execute(text("SELECT COUNT(*) FROM knowledge_assertions"))
                ).scalar_one() == 3
        finally:
            await database.close()

    asyncio.run(run())


def test_optional_receipt_assertion_reference_roundtrip(tmp_path, objects, populate):
    async def run():
        database = Database(tmp_path)
        try:
            await database.initialize()
            store = await populate(database)
            now = datetime.now(timezone(timedelta(hours=-5)))
            for target in (None, objects["truth"].assertion_id):
                receipt = CommandReceipt(
                    RequestId(uuid4()),
                    objects["world"].world_id,
                    "test.command",
                    "pending",
                    now,
                    result_reference=target,
                )
                await store.add(receipt)
                loaded = await store.reload(receipt)
                assert loaded == receipt
                assert loaded.created_at.tzinfo is UTC
        finally:
            await database.close()

    asyncio.run(run())


@pytest.mark.parametrize(
    "name", ["presence", "character_state", "relationship", "event", "receipt"]
)
def test_database_identity_and_idempotency_reject_duplicates(tmp_path, objects, populate, name):
    async def run():
        database = Database(tmp_path)
        try:
            await database.initialize()
            store = await populate(database)
            entity = objects[name]
            if name == "presence":
                entity = replace(entity, location_id=objects["other_location"].location_id)
            if name == "event":
                entity = replace(entity, event_id=EventId(entity.world_id, uuid4()))
            with pytest.raises(PersistenceConflictError):
                await store.add(entity)
            assert await store.reload(objects[name]) == objects[name]
        finally:
            await database.close()

    asyncio.run(run())


def test_database_location_policy():
    with pytest.raises(ValueError, match="absolute"):
        Database(Path("relative"))
    with pytest.raises(ValueError, match="source_tree"):
        Database(Path(__file__).resolve().parents[2] / "runtime-data")
