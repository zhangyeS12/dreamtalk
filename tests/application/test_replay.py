"""State equivalence, isolation and failure atomicity through real command ledgers."""

import asyncio
import json
from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

import pytest
from livingworld.application.commands import (
    AcquireKnowledge,
    AssertWorldTruth,
    ChangeRelationship,
    CreateCharacter,
    CreateLocation,
    CreatePlayer,
    CreateWorld,
    MovePlayer,
    PlaceCharacter,
)
from livingworld.application.errors import (
    InvalidEventPayloadError,
    ReplayError,
    UnsupportedEventError,
)
from livingworld.application.fingerprints import canonical_json
from livingworld.application.replay import ProjectionRebuilder
from livingworld.domain.identifiers import (
    CharacterId,
    EventId,
    KnowledgeAssertionId,
    LocationId,
    PlayerId,
    WorldId,
)
from livingworld.domain.knowledge import ObservationChannel
from livingworld.domain.values import Revision, WorldTime
from livingworld.infrastructure.persistence.replay import SqlAlchemyProjectionRebuildUnitOfWork
from sqlalchemy import text

PROJECTIONS = (
    "worlds",
    "world_clocks",
    "locations",
    "players",
    "player_presences",
    "characters",
    "character_states",
    "relationships",
    "knowledge_assertions",
    "observations",
)
EVIDENCE = (
    "world_events",
    "world_ledger_cursors",
    "command_receipts",
    "schema_version",
    "migration_history",
    "alembic_version",
    "location_connections",
)


async def snapshot(env, tables, world=None):
    result = {}
    async with env.database.engine.connect() as connection:
        for table in tables:
            query = f"SELECT * FROM {table}"
            if world and table not in ("schema_version", "migration_history", "alembic_version"):
                query += " WHERE world_id = :world"
            rows = (
                await connection.execute(text(query), {"world": world.value.hex} if world else {})
            ).mappings()
            values = []
            for row in rows:
                value = dict(row)
                # Numeric scale and JSON key order are presentation, not semantic state.
                for key in ("confidence", "time_scale"):
                    if value.get(key) is not None:
                        value[key] = Decimal(value[key])
                for key in ("value",):
                    if key in value:
                        value[key] = json.loads(value[key])
                values.append(value)
            result[table] = sorted(values, key=repr)
    return result


async def complete_history(env):
    await env.initialize()
    await env.handler.execute(
        env.command(MovePlayer, player_id=env.player, destination_id=env.cafe)
    )
    for character, locations in ((env.alice, (env.home, env.cafe)), (env.bob, (env.park,))):
        for location in locations:
            await env.handler.execute(
                env.command(PlaceCharacter, character_id=character, location_id=location)
            )
    for source, target, deltas in (
        (env.alice, env.bob, (7, 3, 9)),
        (env.alice, env.bob, (-2, 4, 1)),
        (env.bob, env.alice, (-3, -4, 2)),
        (env.player, env.alice, (1, 2, 3)),
    ):
        await env.handler.execute(
            env.command(
                ChangeRelationship,
                source_id=source,
                target_id=target,
                affinity_delta=deltas[0],
                trust_delta=deltas[1],
                familiarity_delta=deltas[2],
            )
        )
    truth = KnowledgeAssertionId(env.world, uuid4())
    await env.handler.execute(
        env.command(
            AssertWorldTruth,
            assertion_id=truth,
            subject="Billy",
            predicate="met",
            value={"character": "Banyue", "location": "Cafe", "evidence": [True, 4]},
            confidence=Decimal("0.7500"),
            valid_from=WorldTime(-50),
            valid_to=WorldTime(900),
        )
    )
    acquisitions = []
    for receiver in (env.alice, env.alice, env.bob, env.player):
        command = env.command(
            AcquireKnowledge,
            assertion_id=KnowledgeAssertionId(env.world, uuid4()),
            receiver_id=receiver,
            source_assertion_id=truth,
            channel=ObservationChannel.TOLD,
            confidence=Decimal("0.8300"),
            epistemic_status="reported",
        )
        acquisitions.append((command, await env.handler.execute(command)))
    return truth, acquisitions


def test_complete_normal_command_history_rebuilds_twice_equivalently(environment, monkeypatch):
    async def run():
        env = environment
        try:
            _, acquisitions = await complete_history(env)
            expected = await snapshot(env, PROJECTIONS)
            evidence = await snapshot(env, EVIDENCE)
            calls = env.clock.calls
            entries = await env.database.canonical_event_reader(env.world).read()
            assert {entry.event.event_type for entry in entries} == {
                "WorldCreated",
                "LocationCreated",
                "PlayerCreated",
                "PlayerPlaced",
                "PlayerMoved",
                "CharacterCreated",
                "CharacterPlaced",
                "RelationshipChanged",
                "WorldTruthAsserted",
                "ObservationRecorded",
                "KnowledgeAcquired",
            }
            assert [entry.ledger_position for entry in entries] == list(range(1, len(entries) + 1))
            assert len({entry.event.occurred_at for entry in entries}) == 1
            assert len({entry.event.created_at for entry in entries}) == 1

            def forbidden(*args, **kwargs):
                raise AssertionError("Replay used nondeterministic command side effects")

            with monkeypatch.context() as context:
                context.setattr(env.handler, "execute", forbidden)
                context.setattr(env.clock, "now_utc", forbidden)
                context.setattr("uuid.uuid4", forbidden)
                rebuilder = ProjectionRebuilder(env.database.projection_rebuild_unit_of_work)
                first = await rebuilder.rebuild(env.world)
                assert await snapshot(env, PROJECTIONS) == expected
                second = await rebuilder.rebuild(env.world)
                assert second == first
            assert await snapshot(env, PROJECTIONS) == expected
            assert await snapshot(env, EVIDENCE) == evidence
            assert env.clock.calls == calls
            assert {observation.observation_id for observation in second.observations} == {
                result.observation_id for _, result in acquisitions
            }
            first_two = second.observations[:2]
            assert first_two[0].observation_id != first_two[1].observation_id
            assert (
                first_two[0].principal_id,
                first_two[0].target_id,
                first_two[0].channel,
                first_two[0].observed_at,
            ) == (
                first_two[1].principal_id,
                first_two[1].target_id,
                first_two[1].channel,
                first_two[1].observed_at,
            )
            await env.restart()
            for command, result in acquisitions:
                assert await env.handler.execute(command) == replace(result, replayed=True)
            assert await snapshot(env, PROJECTIONS) == expected
            assert await snapshot(env, EVIDENCE) == evidence
        finally:
            await env.database.close()

    asyncio.run(run())


@pytest.mark.parametrize("damage", ["missing_presence", "wrong_presence", "wrong_world_clock"])
def test_projection_damage_restored_from_ledger(environment, damage):
    async def run():
        env = environment
        try:
            await complete_history(env)
            expected = await snapshot(env, PROJECTIONS)
            async with env.database.engine.begin() as connection:
                if damage == "missing_presence":
                    await connection.execute(
                        text("DELETE FROM player_presences WHERE world_id=:world"),
                        {"world": env.world.value.hex},
                    )
                elif damage == "wrong_presence":
                    await connection.execute(
                        text(
                            "UPDATE player_presences SET location_id=:home, revision=42 "
                            "WHERE world_id=:world"
                        ),
                        {"world": env.world.value.hex, "home": env.home.value.hex},
                    )
                else:
                    await connection.execute(
                        text(
                            "UPDATE worlds SET name='corrupted', revision=42 WHERE world_id=:world"
                        ),
                        {"world": env.world.value.hex},
                    )
                    await connection.execute(
                        text(
                            "UPDATE world_clocks SET logical_time=999, time_scale='42', "
                            "state='paused', revision=42 WHERE world_id=:world"
                        ),
                        {"world": env.world.value.hex},
                    )
            restored = await ProjectionRebuilder(
                env.database.projection_rebuild_unit_of_work
            ).rebuild(env.world)
            assert await snapshot(env, PROJECTIONS) == expected
            assert restored.presences[0].location_id == env.cafe
            assert restored.presences[0].revision == Revision(1)
        finally:
            await env.database.close()

    asyncio.run(run())


def test_world_isolation_and_knowledge_secret_after_replay(environment):
    async def run():
        env = environment
        try:
            await env.initialize()
            billy, banyue = CharacterId(env.world, uuid4()), CharacterId(env.world, uuid4())
            belle = CharacterId(env.world, uuid4())
            for identity, name in ((billy, "Billy"), (banyue, "Banyue"), (belle, "Belle")):
                await env.handler.execute(
                    env.command(CreateCharacter, character_id=identity, name=name)
                )
            source = KnowledgeAssertionId(env.world, uuid4())
            await env.handler.execute(
                env.command(
                    AssertWorldTruth,
                    assertion_id=source,
                    subject="Billy",
                    predicate="secretly_met",
                    value={"person": "Banyue", "place": "Cafe", "canary": "private-evidence"},
                )
            )
            owned = {}
            for receiver in (billy, banyue):
                owned[receiver] = KnowledgeAssertionId(env.world, uuid4())
                await env.handler.execute(
                    env.command(
                        AcquireKnowledge,
                        assertion_id=owned[receiver],
                        receiver_id=receiver,
                        source_assertion_id=source,
                        channel=ObservationChannel.WITNESSED,
                    )
                )
            other = WorldId(uuid4())
            other_location = LocationId(other, env.home.value)
            await env.handler.execute(
                CreateWorld(
                    request_id=env.command(CreateWorld, name="unused").request_id,
                    world_id=other,
                    name="Other",
                    initial_time=WorldTime(123),
                )
            )
            await env.handler.execute(
                CreateLocation(
                    request_id=env.command(CreateWorld, name="unused").request_id,
                    world_id=other,
                    location_id=other_location,
                    name="Other Home",
                )
            )
            from livingworld.domain.contracts import RequestId

            other_player = PlayerId(other, env.player.value)
            other_character = CharacterId(other, env.alice.value)

            def command(kind, **values):
                return kind(request_id=RequestId(uuid4()), world_id=other, **values)

            await env.handler.execute(
                command(
                    CreatePlayer,
                    player_id=other_player,
                    name="Other player",
                    initial_location_id=other_location,
                )
            )
            await env.handler.execute(
                command(CreateCharacter, character_id=other_character, name="Other character")
            )
            await env.handler.execute(
                command(PlaceCharacter, character_id=other_character, location_id=other_location)
            )
            await env.handler.execute(
                command(
                    ChangeRelationship,
                    source_id=other_player,
                    target_id=other_character,
                    affinity_delta=7,
                    trust_delta=3,
                    familiarity_delta=9,
                )
            )
            other_truth = KnowledgeAssertionId(other, uuid4())
            await env.handler.execute(
                command(
                    AssertWorldTruth,
                    assertion_id=other_truth,
                    subject="other",
                    predicate="exists",
                    value=True,
                )
            )
            for receiver in (other_player, other_character):
                await env.handler.execute(
                    command(
                        AcquireKnowledge,
                        assertion_id=KnowledgeAssertionId(other, uuid4()),
                        receiver_id=receiver,
                        source_assertion_id=other_truth,
                        channel=ObservationChannel.TOLD,
                    )
                )
            other_before = await snapshot(env, PROJECTIONS + EVIDENCE, other)
            other_entries = await env.database.canonical_event_reader(other).read()
            assert [entry.ledger_position for entry in other_entries] == list(
                range(1, len(other_entries) + 1)
            )
            await ProjectionRebuilder(env.database.projection_rebuild_unit_of_work).rebuild(
                env.world
            )
            assert await snapshot(env, PROJECTIONS + EVIDENCE, other) == other_before
            for reader in (
                env.database.character_knowledge_reader(belle),
                env.database.player_knowledge_reader(env.player),
            ):
                assert await reader.list() == ()
                for identity in (source, *owned.values()):
                    assert await reader.get(identity) is None
            for receiver, identity in owned.items():
                reader = env.database.character_knowledge_reader(receiver)
                assert len(await reader.list()) == 1
                assert (await reader.get(identity)).owner == receiver
                assert await reader.get(source) is None
                assert all(
                    [
                        await reader.get(other_identity) is None
                        for owner, other_identity in owned.items()
                        if owner != receiver
                    ]
                )
            this_world_before = await snapshot(env, PROJECTIONS + EVIDENCE, env.world)
            await ProjectionRebuilder(env.database.projection_rebuild_unit_of_work).rebuild(other)
            assert await snapshot(env, PROJECTIONS + EVIDENCE, other) == other_before
            assert await snapshot(env, PROJECTIONS + EVIDENCE, env.world) == this_world_before
        finally:
            await env.database.close()

    asyncio.run(run())


@pytest.mark.parametrize(
    "failure",
    [
        "unknown_type",
        "unknown_version",
        "invalid_payload",
        "invalid_relationship",
        "incomplete_acquisition",
        "invalid_knowledge_value",
    ],
)
def test_replay_failure_restores_all_old_projections(environment, failure):
    async def run():
        env = environment
        try:
            await complete_history(env)
            before = await snapshot(env, PROJECTIONS)
            entries = await env.database.canonical_event_reader(env.world).read()
            source = next(
                entry.event for entry in entries if entry.event.event_type == "RelationshipChanged"
            )
            error = InvalidEventPayloadError
            payload = json.loads(canonical_json(source.payload))
            bad = replace(
                source, event_id=EventId(env.world, uuid4()), idempotency_key=f"bad:{uuid4()}"
            )
            prefix = []
            if failure == "unknown_type":
                bad = replace(bad, event_type="FutureUnsupportedType")
                error = UnsupportedEventError
            elif failure == "unknown_version":
                bad = replace(bad, payload_version=2)
                error = UnsupportedEventError
            elif failure == "invalid_payload":
                bad = replace(bad, payload={"private_canary": "never-log-this"})
            elif failure == "invalid_relationship":
                payload["edge_existed"] = True
                payload["before"] = {"affinity": 5, "trust": 7, "familiarity": 10}
                payload["after"]["trust"] = 99
                bad = replace(bad, payload=payload)
            elif failure == "invalid_knowledge_value":
                source = next(
                    entry.event
                    for entry in entries
                    if entry.event.event_type == "KnowledgeAcquired"
                )
                payload = json.loads(canonical_json(source.payload))
                payload["observation_id"] = str(uuid4())
                payload["assertion_id"] = str(uuid4())
                identity = EventId(env.world, uuid4())
                payload["provenance_event_id"] = str(identity.value)
                payload["value"]["evidence"][0] = 1  # JSON true is not the number 1.
                observation_payload = {
                    key: payload[key]
                    for key in (
                        "observation_id",
                        "receiver",
                        "source_assertion_id",
                        "channel",
                        "observed_at",
                        "created_at",
                    )
                }
                prefix = [
                    replace(
                        source,
                        event_type="ObservationRecorded",
                        event_id=EventId(env.world, uuid4()),
                        payload=observation_payload,
                        idempotency_key=f"bad-observation:{uuid4()}",
                    )
                ]
                bad = replace(
                    source,
                    event_id=identity,
                    payload=payload,
                    idempotency_key=f"bad-acquisition:{uuid4()}",
                )
            else:
                source = next(
                    entry.event
                    for entry in entries
                    if entry.event.event_type == "ObservationRecorded"
                )
                payload = json.loads(canonical_json(source.payload))
                payload["observation_id"] = str(uuid4())
                bad = replace(
                    source,
                    event_id=EventId(env.world, uuid4()),
                    payload=payload,
                    idempotency_key=f"bad:{uuid4()}",
                )
            async with env.database.unit_of_work() as uow:
                for event in prefix:
                    await uow.events.append(event)
                await uow.events.append(bad)
                await uow.commit()
            evidence = await snapshot(env, EVIDENCE)
            with pytest.raises(error) as caught:
                await ProjectionRebuilder(env.database.projection_rebuild_unit_of_work).rebuild(
                    env.world
                )
            assert "never-log-this" not in str(caught.value)
            assert await snapshot(env, PROJECTIONS) == before
            assert await snapshot(env, EVIDENCE) == evidence
        finally:
            await env.database.close()

    asyncio.run(run())


def test_replacement_failure_rolls_back_and_protections_remain(environment, monkeypatch):
    async def run():
        env = environment
        try:
            await complete_history(env)
            before = await snapshot(env, PROJECTIONS + EVIDENCE)
            original = SqlAlchemyProjectionRebuildUnitOfWork.replace

            async def fail(self, value):
                await original(self, value)
                raise ReplayError("injected after replacement flush")

            monkeypatch.setattr(SqlAlchemyProjectionRebuildUnitOfWork, "replace", fail)
            with pytest.raises(ReplayError, match="injected"):
                await ProjectionRebuilder(env.database.projection_rebuild_unit_of_work).rebuild(
                    env.world
                )
            assert await snapshot(env, PROJECTIONS + EVIDENCE) == before
            async with env.database.engine.connect() as connection:
                triggers = (
                    (
                        await connection.execute(
                            text(
                                "SELECT name FROM sqlite_master WHERE type='trigger' "
                                "AND tbl_name='world_events' ORDER BY name"
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                assert triggers == ["world_events_no_delete", "world_events_no_update"]
                assert (await connection.execute(text("PRAGMA foreign_keys"))).scalar_one() == 1
                assert (
                    await connection.execute(text("PRAGMA defer_foreign_keys"))
                ).scalar_one() == 0
        finally:
            await env.database.close()

    asyncio.run(run())


def test_empty_world_ledger_rejected_without_clearing(environment):
    async def run():
        env = environment
        try:
            await env.initialize()
            before = await snapshot(env, PROJECTIONS + EVIDENCE)
            with pytest.raises(ReplayError, match="no canonical"):
                await ProjectionRebuilder(env.database.projection_rebuild_unit_of_work).rebuild(
                    WorldId(uuid4())
                )
            assert await snapshot(env, PROJECTIONS + EVIDENCE) == before
        finally:
            await env.database.close()

    asyncio.run(run())


@pytest.mark.parametrize("missing_location_event", [False, True])
def test_preserved_connection_references_validate_at_end_or_roll_back(
    environment, missing_location_event
):
    async def run():
        env = environment
        try:
            await complete_history(env)
            extra = LocationId(env.world, uuid4())
            async with env.database.engine.begin() as connection:
                if missing_location_event:
                    # Test-only corruption: a referenced projection has no canonical
                    # creation event. Replay must fail instead of copying current state.
                    await connection.execute(
                        text("INSERT INTO locations VALUES (:world,:id,'Unlogged',0)"),
                        {"world": env.world.value.hex, "id": extra.value.hex},
                    )
                await connection.execute(
                    text("INSERT INTO location_connections VALUES (:world,:source,:target,0)"),
                    {
                        "world": env.world.value.hex,
                        "source": extra.value.hex if missing_location_event else env.home.value.hex,
                        "target": env.cafe.value.hex,
                    },
                )
            before = await snapshot(env, PROJECTIONS + EVIDENCE)
            rebuilder = ProjectionRebuilder(env.database.projection_rebuild_unit_of_work)
            if missing_location_event:
                with pytest.raises(ReplayError, match="foreign key"):
                    await rebuilder.rebuild(env.world)
            else:
                await rebuilder.rebuild(env.world)
            assert await snapshot(env, PROJECTIONS + EVIDENCE) == before
        finally:
            await env.database.close()

    asyncio.run(run())


@pytest.mark.parametrize("damage", ["reversed", "duplicate_position", "cross_world"])
def test_replay_rejects_broken_reader_contract_atomically(environment, monkeypatch, damage):
    async def run():
        env = environment
        try:
            await complete_history(env)
            entries = await env.database.canonical_event_reader(env.world).read()
            before = await snapshot(env, PROJECTIONS + EVIDENCE)
            from livingworld.infrastructure.persistence import replay

            async def broken(_session, _world):
                if damage == "reversed":
                    return tuple(reversed(entries))
                if damage == "duplicate_position":
                    return (entries[0], replace(entries[1], ledger_position=1), *entries[2:])
                other = WorldId(uuid4())
                event = replace(entries[0].event, world_id=other, event_id=EventId(other, uuid4()))
                return (replace(entries[0], event=event), *entries[1:])

            monkeypatch.setattr(replay, "_read", broken)
            with pytest.raises(InvalidEventPayloadError):
                await ProjectionRebuilder(env.database.projection_rebuild_unit_of_work).rebuild(
                    env.world
                )
            assert await snapshot(env, PROJECTIONS + EVIDENCE) == before
        finally:
            await env.database.close()

    asyncio.run(run())
