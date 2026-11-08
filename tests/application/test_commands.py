import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from livingworld.application.commands import (
    ChangeRelationship,
    CreateCharacter,
    CreateLocation,
    CreatePlayer,
    CreateWorld,
    MovePlayer,
    PlaceCharacter,
    SetPlayerAvailability,
)
from livingworld.application.errors import (
    EntityAlreadyExistsError,
    EntityNotFoundError,
    IdempotencyConflictError,
)
from livingworld.application.fingerprints import command_fingerprint
from livingworld.application.results import RelationshipReference
from livingworld.domain.contracts import RequestId
from livingworld.domain.errors import (
    ConcurrencyConflictError,
    CrossWorldReferenceError,
    DomainInvariantError,
)
from livingworld.domain.identifiers import CharacterId, LocationId, PlayerId, WorldId
from livingworld.domain.participants import PlayerActivity, PlayerAvailability
from livingworld.domain.relationships import RelationshipMetrics
from livingworld.domain.values import Revision, WorldTime
from livingworld.infrastructure.persistence.unit_of_work import (
    CommandReceiptRepository,
    EventAppender,
    PlayerRepository,
    SqlAlchemyUnitOfWork,
)
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


def test_create_world_atomic_and_repeated_after_restart(environment):
    async def run():
        env = environment
        try:
            await env.initialize(seed=False)
            command = env.command(CreateWorld, name="世界", initial_time=WorldTime(-7))
            result = await env.handler.execute(command)
            assert result.entity_reference == env.world and result.resulting_revision == Revision()
            assert not result.replayed
            assert len(await env.rows("worlds")) == len(await env.rows("world_clocks")) == 1
            events = await env.rows("world_events")
            assert len(events) == len(await env.rows("command_receipts")) == 1
            assert events[0].event_type == "WorldCreated" and events[0].occurred_at == -7
            state = await env.snapshot()
            await env.restart()
            assert await env.handler.execute(command) == replace(result, replayed=True)
            assert await env.snapshot() == state
            with pytest.raises(IdempotencyConflictError):
                await env.handler.execute(replace(command, name="different"))
            assert await env.snapshot() == state
        finally:
            await env.database.close()

    asyncio.run(run())


def test_create_player_two_events_presence_and_resolved_defaults(environment):
    async def run():
        env = environment
        try:
            await env.initialize()
            identity = PlayerId(env.world, uuid4())
            command = env.command(
                CreatePlayer, player_id=identity, name="New", initial_location_id=env.cafe
            )
            result = await env.handler.execute(command)
            async with env.database.unit_of_work() as uow:
                presence = await uow.players.presence(identity)
                assert presence.location_id == env.cafe
                assert presence.activity == PlayerActivity.ACTIVE
                assert presence.availability == PlayerAvailability.AVAILABLE
            events = [
                row
                for row in await env.rows("world_events")
                if row.causation_request_id == command.request_id.value.hex
            ]
            by_type = {row.event_type: row for row in events}
            assert set(by_type) == {"PlayerCreated", "PlayerPlaced"}
            assert by_type["PlayerCreated"].idempotency_key == f"{command.request_id}:0"
            assert by_type["PlayerPlaced"].idempotency_key == f"{command.request_id}:1"
            state = await env.snapshot()
            explicit = replace(
                command,
                activity_state=PlayerActivity.ACTIVE,
                availability_state=PlayerAvailability.AVAILABLE,
            )
            assert command_fingerprint(command) == command_fingerprint(explicit)
            assert await env.handler.execute(explicit) == replace(result, replayed=True)
            assert await env.snapshot() == state
        finally:
            await env.database.close()

    asyncio.run(run())


def test_player_availability_change_is_idempotent_and_replayable(environment):
    from livingworld.application.replay import ProjectionRebuilder

    async def run():
        env = environment
        try:
            await env.initialize()
            command = env.command(
                SetPlayerAvailability,
                player_id=env.player,
                availability_state=PlayerAvailability.AVAILABLE,
                expected_presence_revision=Revision(),
            )
            result = await env.handler.execute(command)
            assert result.resulting_revision == Revision(1)
            assert await env.handler.execute(command) == replace(result, replayed=True)
            async with env.database.unit_of_work() as uow:
                presence = await uow.players.presence(env.player)
                assert presence.location_id == env.home
                assert presence.activity == PlayerActivity.INACTIVE
                assert presence.availability == PlayerAvailability.AVAILABLE
                assert presence.revision == Revision(1)
            events = [
                row
                for row in await env.rows("world_events")
                if row.event_type == "PlayerAvailabilityChanged"
            ]
            assert len(events) == 1
            assert json.loads(events[0].payload) == {
                "player_id": str(env.player.value),
                "before_availability": "busy",
                "availability": "available",
                "revision": 1,
            }
            expected = await env.snapshot()
            await ProjectionRebuilder(env.database.projection_rebuild_unit_of_work).rebuild(
                env.world
            )
            assert await env.snapshot() == expected
            stale = replace(command, request_id=RequestId(uuid4()))
            with pytest.raises(ConcurrencyConflictError):
                await env.handler.execute(stale)
        finally:
            await env.database.close()

    asyncio.run(run())


def test_move_persistent_idempotency_original_result_and_internal_time(environment):
    async def run():
        env = environment
        try:
            await env.initialize()
            command = env.command(
                MovePlayer,
                expected_presence_revision=Revision(),
                player_id=env.player,
                destination_id=env.cafe,
            )
            result = await env.handler.execute(command)
            assert result.resulting_revision == Revision(1)
            events = [
                row for row in await env.rows("world_events") if row.event_type == "PlayerMoved"
            ]
            assert len(events) == 1
            event = events[0]
            assert event.occurred_at == 123
            assert datetime.fromisoformat(event.created_at) == env.clock.value
            assert event.payload_version == 1
            assert (
                event.causation_request_id == event.correlation_id == command.request_id.value.hex
            )
            assert event.idempotency_key == f"{command.request_id}:action:0"
            payload = json.loads(event.payload)
            assert payload["from_location_id"] == str(env.home.value)
            assert payload["to_location_id"] == str(env.cafe.value)
            assert payload["revision"] == 1
            observations = [
                row
                for row in await env.rows("observations")
                if row.target_event_id == event.event_id
            ]
            assert len(observations) == 1
            assert observations[0].principal_kind == "player"
            assert observations[0].principal_id == env.player.value.hex
            assert observations[0].basis == "event_occurrence"
            receipts = [
                row
                for row in await env.rows("command_receipts")
                if row.request_id == command.request_id.value.hex
            ]
            assert len(receipts) == 1
            assert json.loads(receipts[0].result_payload)["result_version"] == 2
            async with env.database.unit_of_work() as uow:
                presence = await uow.players.presence(env.player)
                assert presence.location_id == env.cafe and presence.revision == Revision(1)
                assert presence.activity == PlayerActivity.INACTIVE
                assert presence.availability == PlayerAvailability.BUSY
            state = await env.snapshot()
            calls = env.clock.calls
            assert await env.handler.execute(command) == replace(result, replayed=True)
            await env.restart()
            env.clock.value += timedelta(days=3)
            assert await env.handler.execute(command) == replace(result, replayed=True)
            assert env.clock.calls == calls
            assert await env.snapshot() == state
            with pytest.raises(IdempotencyConflictError):
                await env.handler.execute(replace(command, destination_id=env.park))
            assert await env.snapshot() == state
            # An original result is durable even if a later independent command moves again.
            await env.handler.execute(
                env.command(
                    MovePlayer,
                    expected_presence_revision=Revision(1),
                    player_id=env.player,
                    destination_id=env.park,
                )
            )
            later = await env.snapshot()
            assert await env.handler.execute(command) == replace(result, replayed=True)
            assert await env.snapshot() == later
        finally:
            await env.database.close()

    asyncio.run(run())


@pytest.mark.parametrize("kind", ["location", "character", "placement", "relationship"])
def test_focused_commands_and_duplicate_results(environment, kind):
    async def run():
        env = environment
        try:
            await env.initialize()
            if kind == "location":
                command = env.command(
                    CreateLocation, location_id=LocationId(env.world, uuid4()), name="New"
                )
                event_type = "LocationCreated"
            elif kind == "character":
                command = env.command(
                    CreateCharacter, character_id=CharacterId(env.world, uuid4()), name="New"
                )
                event_type = "CharacterCreated"
            elif kind == "placement":
                command = env.command(
                    PlaceCharacter,
                    expected_state_revision=None,
                    character_id=env.alice,
                    location_id=env.cafe,
                )
                event_type = "CharacterPlaced"
            else:
                command = env.command(
                    ChangeRelationship,
                    expected_relationship_revision=None,
                    source_id=env.alice,
                    target_id=env.bob,
                    affinity_delta=3,
                    trust_delta=-2,
                    familiarity_delta=7,
                )
                event_type = "RelationshipChanged"
            before_count = len(await env.rows("world_events"))
            result = await env.handler.execute(command)
            assert len(await env.rows("world_events")) == before_count + 1
            assert (await env.rows("world_events"))[-1].event_type == event_type
            state = await env.snapshot()
            await env.restart()
            assert await env.handler.execute(command) == replace(result, replayed=True)
            assert await env.snapshot() == state
            if kind == "placement":
                await env.handler.execute(
                    env.command(
                        PlaceCharacter,
                        expected_state_revision=Revision(),
                        character_id=env.alice,
                        location_id=env.park,
                    )
                )
                async with env.database.unit_of_work() as uow:
                    state = await uow.characters.state(env.alice)
                    assert state.location_id == env.park and state.revision == Revision(1)
        finally:
            await env.database.close()

    asyncio.run(run())


def test_directional_relationship_creation_change_payload_and_limits(environment):
    async def run():
        env = environment
        try:
            await env.initialize()
            reverse = env.command(
                ChangeRelationship,
                expected_relationship_revision=None,
                source_id=env.bob,
                target_id=env.alice,
                trust_delta=1,
            )
            await env.handler.execute(reverse)
            command = env.command(
                ChangeRelationship,
                expected_relationship_revision=None,
                source_id=env.alice,
                target_id=env.bob,
                affinity_delta=100,
                trust_delta=-100,
                familiarity_delta=100,
            )
            result = await env.handler.execute(command)
            assert result.entity_reference == RelationshipReference(env.alice, env.bob)
            assert result.resulting_revision == Revision(1)
            async with env.database.unit_of_work() as uow:
                forward = await uow.relationships.get(env.alice, env.bob)
                reverse_before = await uow.relationships.get(env.bob, env.alice)
                assert forward.metrics == RelationshipMetrics(100, -100, 100)
                assert reverse_before.metrics == RelationshipMetrics(0, 1, 0)
            events = [
                row
                for row in await env.rows("world_events")
                if row.causation_request_id == command.request_id.value.hex
            ]
            payload = json.loads(events[0].payload)
            assert payload["source_character_id"] == str(env.alice.value)
            assert payload["target_character_id"] == str(env.bob.value)
            assert payload["before"] == {"affinity": 0, "trust": 0, "familiarity": 0}
            assert (
                payload["delta"]
                == payload["after"]
                == {"affinity": 100, "trust": -100, "familiarity": 100}
            )
            assert payload["revision"] == 1 and payload["edge_existed"] is False
            state = await env.snapshot()
            with pytest.raises(DomainInvariantError, match="affinity"):
                await env.handler.execute(
                    env.command(
                        ChangeRelationship,
                        expected_relationship_revision=Revision(1),
                        source_id=env.alice,
                        target_id=env.bob,
                        affinity_delta=1,
                    )
                )
            assert await env.snapshot() == state
            await env.handler.execute(
                env.command(
                    ChangeRelationship,
                    expected_relationship_revision=Revision(1),
                    source_id=env.alice,
                    target_id=env.bob,
                    affinity_delta=-1,
                )
            )
            async with env.database.unit_of_work() as uow:
                assert (await uow.relationships.get(env.alice, env.bob)).revision == Revision(2)
                assert await uow.relationships.get(env.bob, env.alice) == reverse_before
        finally:
            await env.database.close()

    asyncio.run(run())


@pytest.mark.parametrize("failure_point", ["after_event", "after_projection"])
def test_move_failure_rolls_back_and_same_request_retries(environment, monkeypatch, failure_point):
    async def run():
        env = environment
        try:
            await env.initialize()
            command = env.command(
                MovePlayer,
                expected_presence_revision=Revision(),
                player_id=env.player,
                destination_id=env.cafe,
            )
            before = await env.snapshot()
            with monkeypatch.context() as patch:
                if failure_point == "after_event":
                    original = EventAppender.append

                    async def fail(self, event):
                        await original(self, event)
                        raise RuntimeError("injected_after_event")

                    patch.setattr(EventAppender, "append", fail)
                else:

                    async def fail(self, receipt, fingerprint, result):
                        raise RuntimeError("injected_after_projection")

                    patch.setattr(CommandReceiptRepository, "add_action", fail)
                with pytest.raises(RuntimeError, match="injected"):
                    await env.handler.execute(command)
            await env.restart()
            assert await env.snapshot() == before
            result = await env.handler.execute(command)
            assert not result.replayed and result.resulting_revision == Revision(1)
        finally:
            await env.database.close()

    asyncio.run(run())


@pytest.mark.parametrize("failure_point", ["event_0", "event_1", "projection", "receipt", "commit"])
def test_multi_event_player_creation_rollback_and_retry(environment, monkeypatch, failure_point):
    async def run():
        env = environment
        try:
            await env.initialize()
            command = env.command(
                CreatePlayer,
                player_id=PlayerId(env.world, uuid4()),
                name="New",
                initial_location_id=env.cafe,
            )
            before = await env.snapshot()
            with monkeypatch.context() as patch:
                if failure_point.startswith("event"):
                    original = EventAppender.append

                    async def fail(self, event):
                        await original(self, event)
                        if event.idempotency_key.endswith(failure_point[-1]):
                            raise RuntimeError("injected")

                    patch.setattr(EventAppender, "append", fail)
                elif failure_point == "projection":
                    original = PlayerRepository.add

                    async def fail(self, player, presence):
                        await original(self, player, presence)
                        raise RuntimeError("injected")

                    patch.setattr(PlayerRepository, "add", fail)
                elif failure_point == "receipt":
                    original = CommandReceiptRepository.add

                    async def fail(self, receipt, fingerprint, result):
                        await original(self, receipt, fingerprint, result)
                        raise RuntimeError("injected")

                    patch.setattr(CommandReceiptRepository, "add", fail)
                else:

                    async def fail(self):
                        raise RuntimeError("injected")

                    patch.setattr(SqlAlchemyUnitOfWork, "commit", fail)
                with pytest.raises(RuntimeError, match="injected"):
                    await env.handler.execute(command)
            await env.restart()
            assert await env.snapshot() == before
            result = await env.handler.execute(command)
            assert not result.replayed
            assert len(await env.rows("world_events")) == len(before["world_events"]) + 2
            assert len(await env.rows("players")) == len(before["players"]) + 1
            assert len(await env.rows("player_presences")) == len(before["player_presences"]) + 1
            assert len(await env.rows("command_receipts")) == len(before["command_receipts"]) + 1
        finally:
            await env.database.close()

    asyncio.run(run())


def test_create_world_rollback_including_fk_staging(environment, monkeypatch):
    async def run():
        env = environment
        try:
            await env.initialize(seed=False)
            command = env.command(CreateWorld, name="World")
            with monkeypatch.context() as patch:

                async def fail(self, receipt, fingerprint, result):
                    raise RuntimeError("injected")

                patch.setattr(CommandReceiptRepository, "add", fail)
                with pytest.raises(RuntimeError, match="injected"):
                    await env.handler.execute(command)
            await env.restart()
            assert all(not rows for rows in (await env.snapshot()).values())
            assert not (await env.handler.execute(command)).replayed
        finally:
            await env.database.close()

    asyncio.run(run())


@pytest.mark.parametrize("kind", ["move", "player", "relationship", "character_place"])
def test_cross_world_rejected_without_writes(environment, kind):
    async def run():
        env = environment
        try:
            await env.initialize()
            before = await env.snapshot()
            other = WorldId(uuid4())
            with pytest.raises(CrossWorldReferenceError):
                if kind == "move":
                    command = env.command(
                        MovePlayer,
                        expected_presence_revision=Revision(),
                        player_id=env.player,
                        destination_id=LocationId(other, uuid4()),
                    )
                elif kind == "player":
                    command = env.command(
                        CreatePlayer,
                        player_id=PlayerId(env.world, uuid4()),
                        name="New",
                        initial_location_id=LocationId(other, uuid4()),
                    )
                elif kind == "relationship":
                    command = env.command(
                        ChangeRelationship,
                        expected_relationship_revision=None,
                        source_id=env.alice,
                        target_id=CharacterId(other, uuid4()),
                        affinity_delta=1,
                    )
                else:
                    command = env.command(
                        PlaceCharacter,
                        expected_state_revision=None,
                        character_id=env.alice,
                        location_id=LocationId(other, uuid4()),
                    )
                await env.handler.execute(command)
            assert await env.snapshot() == before
        finally:
            await env.database.close()

    asyncio.run(run())


@pytest.mark.parametrize(
    "kind", ["world", "location", "player", "presence", "character", "participant"]
)
def test_missing_references_are_rejected_without_canonical_mutation(environment, kind):
    async def run():
        env = environment
        try:
            await env.initialize()
            before = await env.snapshot()
            if kind == "world":
                other = WorldId(uuid4())
                command = CreateLocation(
                    request_id=RequestId(uuid4()),
                    world_id=other,
                    location_id=LocationId(other, uuid4()),
                    name="No world",
                )
            elif kind == "location":
                command = env.command(
                    CreatePlayer,
                    player_id=PlayerId(env.world, uuid4()),
                    name="New",
                    initial_location_id=LocationId(env.world, uuid4()),
                )
            elif kind == "player":
                command = env.command(
                    MovePlayer,
                    expected_presence_revision=Revision(),
                    player_id=PlayerId(env.world, uuid4()),
                    destination_id=env.cafe,
                )
            elif kind == "presence":
                # DB corruption simulation uses raw SQL only in this invariant test.
                async with env.database.engine.begin() as connection:
                    await connection.execute(text("DELETE FROM player_presences"))
                before = await env.snapshot()
                command = env.command(
                    MovePlayer,
                    expected_presence_revision=Revision(),
                    player_id=env.player,
                    destination_id=env.cafe,
                )
            elif kind == "character":
                command = env.command(
                    PlaceCharacter,
                    expected_state_revision=None,
                    character_id=CharacterId(env.world, uuid4()),
                    location_id=env.cafe,
                )
            else:
                command = env.command(
                    ChangeRelationship,
                    expected_relationship_revision=None,
                    source_id=env.alice,
                    target_id=CharacterId(env.world, uuid4()),
                    affinity_delta=1,
                )
            with pytest.raises(EntityNotFoundError):
                await env.handler.execute(command)
            after = await env.snapshot()
            if kind in {"player", "presence"}:
                # The compatibility command now uses canonical ActionResolution.
                # Rejections are durable/idempotent, but never mutate world state.
                assert {
                    key: value for key, value in after.items() if key != "command_receipts"
                } == {key: value for key, value in before.items() if key != "command_receipts"}
                assert len(after["command_receipts"]) == len(before["command_receipts"]) + 1
                receipt = next(
                    row
                    for row in await env.rows("command_receipts")
                    if row.request_id == command.request_id.value.hex
                )
                assert receipt.status == "rejected"
                assert json.loads(receipt.result_payload)["reason"] == "not_present"
            else:
                assert after == before
        finally:
            await env.database.close()

    asyncio.run(run())


@pytest.mark.parametrize("kind", ["world", "location", "player", "character"])
def test_explicit_target_collision_is_not_an_idempotent_retry(environment, kind):
    async def run():
        env = environment
        try:
            await env.initialize()
            before = await env.snapshot()
            commands = {
                "world": env.command(CreateWorld, name="World"),
                "location": env.command(CreateLocation, location_id=env.home, name="Home"),
                "player": env.command(
                    CreatePlayer, player_id=env.player, name="Player", initial_location_id=env.home
                ),
                "character": env.command(CreateCharacter, character_id=env.alice, name="Alice"),
            }
            with pytest.raises(EntityAlreadyExistsError):
                await env.handler.execute(commands[kind])
            assert await env.snapshot() == before
        finally:
            await env.database.close()

    asyncio.run(run())


@pytest.mark.parametrize("deltas", [(0, 0, 0), (True, 0, 0), (0, 1.5, 0), (0, 0, -1)])
def test_invalid_relationship_delta_no_event_or_new_edge(environment, deltas):
    async def run():
        env = environment
        try:
            await env.initialize()
            before = await env.snapshot()
            with pytest.raises(DomainInvariantError):
                command = env.command(
                    ChangeRelationship,
                    expected_relationship_revision=None,
                    source_id=env.alice,
                    target_id=env.bob,
                    affinity_delta=deltas[0],
                    trust_delta=deltas[1],
                    familiarity_delta=deltas[2],
                )
                await env.handler.execute(command)
            assert await env.snapshot() == before
        finally:
            await env.database.close()

    asyncio.run(run())


def test_wall_clock_injection_normalizes_utc_and_rejects_naive(environment):
    async def run():
        env = environment
        try:
            await env.initialize(seed=False)
            env.clock.value = datetime(2026, 9, 17, 20, tzinfo=timezone(timedelta(hours=8)))
            await env.handler.execute(
                env.command(CreateWorld, name="World", initial_time=WorldTime(99))
            )
            event = (await env.rows("world_events"))[0]
            assert datetime.fromisoformat(event.created_at) == datetime(2026, 9, 17, 12, tzinfo=UTC)
            assert event.created_at.endswith("+00:00") and event.occurred_at == 99
            before = await env.snapshot()
            env.clock.value = datetime(2026, 9, 17)
            with pytest.raises(DomainInvariantError, match="timezone-aware"):
                await env.handler.execute(
                    env.command(CreateLocation, location_id=env.home, name="Home")
                )
            assert await env.snapshot() == before
        finally:
            await env.database.close()

    asyncio.run(run())


def test_fingerprint_semantics_request_independence_decimal_and_scope(environment):
    env = environment
    command = env.command(CreateWorld, name="World", time_scale=Decimal("1.000"))
    assert command_fingerprint(command) == command_fingerprint(
        replace(command, request_id=RequestId(uuid4()), time_scale=Decimal("1"))
    )
    assert command_fingerprint(command) != command_fingerprint(
        replace(command, initial_time=WorldTime(1))
    )
    assert command_fingerprint(command) != command_fingerprint(
        replace(command, world_id=WorldId(uuid4()))
    )


@pytest.mark.parametrize(
    "mutation", ["UPDATE world_events SET event_type='changed'", "DELETE FROM world_events"]
)
def test_pipeline_events_remain_append_only(environment, mutation):
    async def run():
        env = environment
        try:
            await env.initialize()
            before = await env.snapshot()
            with pytest.raises(IntegrityError, match="world_event_immutable"):
                async with env.database.engine.begin() as connection:
                    await connection.execute(text(mutation))
            assert await env.snapshot() == before
        finally:
            await env.database.close()

    asyncio.run(run())


def test_request_identity_conflict_across_command_types_and_worlds(environment):
    async def run():
        env = environment
        try:
            await env.initialize()
            command = env.command(
                MovePlayer,
                expected_presence_revision=Revision(),
                player_id=env.player,
                destination_id=env.cafe,
            )
            await env.handler.execute(command)
            before = await env.snapshot()
            changed_type = CreateCharacter(
                request_id=command.request_id,
                world_id=env.world,
                character_id=CharacterId(env.world, uuid4()),
                name="Other",
            )
            changed_world = CreateWorld(
                request_id=command.request_id, world_id=WorldId(uuid4()), name="Other"
            )
            for changed in (changed_type, changed_world):
                with pytest.raises(IdempotencyConflictError):
                    await env.handler.execute(changed)
                assert await env.snapshot() == before
        finally:
            await env.database.close()

    asyncio.run(run())
