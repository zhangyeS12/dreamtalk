"""World-local allocation, command atomicity and canonical append protection."""

import asyncio
from dataclasses import FrozenInstanceError, replace
from uuid import uuid4

import pytest
from livingworld.application.commands import CreateLocation, CreatePlayer, CreateWorld
from livingworld.application.ledger import CanonicalEvent
from livingworld.application.replay import ProjectionRebuilder
from livingworld.domain.errors import DomainInvariantError
from livingworld.domain.identifiers import EventId, LocationId, PlayerId
from livingworld.infrastructure.persistence.unit_of_work import EventAppender
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


def test_new_world_and_multi_event_command_have_stable_positions(environment):
    async def run():
        env = environment
        try:
            await env.initialize()
            entries = await env.database.canonical_event_reader(env.world).read()
            assert entries[0].ledger_position == 1 and entries[0].event.event_type == "WorldCreated"
            player_events = [
                entry
                for entry in entries
                if entry.event.event_type in ("PlayerCreated", "PlayerPlaced")
            ]
            assert [entry.event.event_type for entry in player_events] == [
                "PlayerCreated",
                "PlayerPlaced",
            ]
            assert player_events[1].ledger_position == player_events[0].ledger_position + 1
            assert player_events[0].event.idempotency_key.endswith(":0")
            assert player_events[1].event.idempotency_key.endswith(":1")
            assert player_events[0].event.causation_id == player_events[1].event.causation_id
            with pytest.raises(FrozenInstanceError):
                entries[0].ledger_position = 2
            for value in (0, -1, 1.5, True):
                with pytest.raises(DomainInvariantError):
                    CanonicalEvent(entries[0].event, value)
        finally:
            await env.database.close()

    asyncio.run(run())


@pytest.mark.parametrize("new_world", [True, False])
def test_failed_command_rolls_back_allocator_events_projections_and_receipt(
    environment, monkeypatch, new_world
):
    async def run():
        env = environment
        try:
            await env.initialize(seed=not new_world)
            before = await env.snapshot()
            original = EventAppender.append
            calls = 0

            async def fail(self, event):
                nonlocal calls
                await original(self, event)
                calls += 1
                if calls == (1 if new_world else 2):
                    raise RuntimeError("injected after allocation and event flush")

            monkeypatch.setattr(EventAppender, "append", fail)
            command = (
                env.command(CreateWorld, name="Failed")
                if new_world
                else env.command(
                    CreatePlayer,
                    player_id=PlayerId(env.world, uuid4()),
                    name="Failed",
                    initial_location_id=env.cafe,
                )
            )
            with pytest.raises(RuntimeError, match="injected"):
                await env.handler.execute(command)
            assert await env.snapshot() == before
            if new_world:
                assert await env.rows("world_ledger_cursors") == []
            monkeypatch.setattr(EventAppender, "append", original)
            await env.handler.execute(command)
            after = await env.database.canonical_event_reader(env.world).read()
            assert after[-1].ledger_position == len(after)
            if new_world:
                assert after[0].ledger_position == 1
        finally:
            await env.database.close()

    asyncio.run(run())


@pytest.mark.parametrize("position", [0, -1, 1.5, None, 1])
def test_positive_integer_and_world_local_unique_position_enforced(environment, position):
    async def run():
        env = environment
        try:
            await env.initialize()
            before = await env.snapshot()
            with pytest.raises(IntegrityError):
                async with env.database.engine.begin() as connection:
                    await connection.execute(
                        text(
                            "INSERT INTO world_events (world_id,event_id,event_type,occurred_at,"
                            "payload,payload_version,created_at,ledger_position) "
                            "SELECT world_id,:id,event_type,occurred_at,payload,payload_version,"
                            "created_at,:position "
                            "FROM world_events WHERE ledger_position=1"
                        ),
                        {"id": uuid4().hex, "position": position},
                    )
            assert await env.snapshot() == before
        finally:
            await env.database.close()

    asyncio.run(run())


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE world_events SET ledger_position=ledger_position+100",
        "DELETE FROM world_events",
        "INSERT OR REPLACE INTO world_events SELECT * FROM world_events",
    ],
)
def test_ledger_update_delete_replace_remain_rejected(environment, statement):
    async def run():
        env = environment
        try:
            await env.initialize()
            before = await env.snapshot()
            with pytest.raises(IntegrityError, match="world_event_immutable"):
                async with env.database.engine.begin() as connection:
                    await connection.execute(text(statement))
            assert await env.snapshot() == before
        finally:
            await env.database.close()

    asyncio.run(run())


def test_gaps_and_reverse_timestamps_still_use_canonical_order(environment):
    async def run():
        env = environment
        try:
            await env.initialize()
            entries = await env.database.canonical_event_reader(env.world).read()
            # Test a permitted reserved gap without ever editing canonical events.
            async with env.database.engine.begin() as connection:
                await connection.execute(
                    text(
                        "UPDATE world_ledger_cursors SET last_position=last_position+5 "
                        "WHERE world_id=:world"
                    ),
                    {"world": env.world.value.hex},
                )
            from datetime import timedelta

            env.clock.value -= timedelta(days=30)
            command = env.command(
                CreateLocation,
                location_id=LocationId(env.world, uuid4()),
                name="Earlier wall clock",
            )
            result = await env.handler.execute(command)
            ordered = await env.database.canonical_event_reader(env.world).read()
            assert ordered[-1].ledger_position == entries[-1].ledger_position + 6
            assert ordered[-1].event.created_at < ordered[0].event.created_at
            restored = await ProjectionRebuilder(
                env.database.projection_rebuild_unit_of_work
            ).rebuild(env.world)
            assert restored.locations[-1].location_id == command.location_id
            before = await env.snapshot()
            await env.restart()
            assert await env.handler.execute(command) == replace(result, replayed=True)
            assert await env.snapshot() == before
        finally:
            await env.database.close()

    asyncio.run(run())


def test_allocator_atomic_across_independent_sqlite_transactions(environment):
    async def run():
        env = environment
        try:
            await env.initialize()
            before = await env.database.canonical_event_reader(env.world).read()
            template = before[0].event

            async def append(index):
                event = replace(
                    template,
                    event_id=EventId(env.world, uuid4()),
                    event_type="TestOnlyAllocation",
                    payload={"index": index},
                    idempotency_key=f"parallel:{index}",
                )
                async with env.database.unit_of_work() as uow:
                    await uow.events.append(event)
                    await uow.commit()
                return event.event_id

            identities = await asyncio.gather(*(append(index) for index in range(4)))
            entries = await env.database.canonical_event_reader(env.world).read()
            added = entries[len(before) :]
            assert {entry.event.event_id for entry in added} == set(identities)
            assert [entry.ledger_position for entry in added] == list(
                range(len(before) + 1, len(before) + 5)
            )
            cursor = (await env.rows("world_ledger_cursors"))[0]
            assert cursor.last_position == entries[-1].ledger_position
        finally:
            await env.database.close()

    asyncio.run(run())
