"""Complete Stage 2 world uses supported commands; history survives races/replay."""

import asyncio
import json
from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

import pytest
from concurrency_support import race_commands
from livingworld.application.commands import (
    AcquireKnowledge,
    AssertWorldTruth,
    ChangeRelationship,
    CreateCharacter,
    CreateLocation,
    CreatePlayer,
    CreateWorld,
    FormCharacterBelief,
    MovePlayer,
    PlaceCharacter,
)
from livingworld.application.errors import IdempotencyConflictError
from livingworld.application.replay import ProjectionRebuilder
from livingworld.domain.errors import ConcurrencyConflictError, CrossWorldReferenceError
from livingworld.domain.identifiers import (
    CharacterId,
    KnowledgeAssertionId,
    LocationId,
    PlayerId,
    WorldId,
)
from livingworld.domain.knowledge import KnowledgeScope, ObservationChannel
from livingworld.domain.participants import PlayerActivity, PlayerAvailability
from livingworld.domain.values import Revision, WorldTime
from livingworld.infrastructure.persistence.migration import HEAD_REVISION
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from test_replay import EVIDENCE, PROJECTIONS, snapshot

EVENTS = {
    CreateWorld: ("WorldCreated",),
    CreateLocation: ("LocationCreated",),
    CreatePlayer: ("PlayerCreated", "PlayerPlaced"),
    CreateCharacter: ("CharacterCreated",),
    MovePlayer: ("PlayerMoved",),
    PlaceCharacter: ("CharacterPlaced",),
    ChangeRelationship: ("RelationshipChanged",),
    AssertWorldTruth: ("WorldTruthAsserted",),
    AcquireKnowledge: ("ObservationRecorded", "KnowledgeAcquired"),
    FormCharacterBelief: ("CharacterBeliefFormed",),
}


def test_stage_2_command_world_history_concurrency_knowledge_and_replay(environment):
    async def run():
        env = environment
        try:
            await env.initialize(seed=False)
            committed = []

            async def apply(command):
                result = await env.handler.execute(command)
                assert not result.replayed
                committed.append((command, result))
                return result

            def command(kind, **values):
                return env.command(kind, **values)

            await apply(command(CreateWorld, name="Acceptance World", initial_time=WorldTime(123)))
            for identity, name in ((env.home, "Home"), (env.cafe, "Cafe"), (env.park, "Park")):
                await apply(command(CreateLocation, location_id=identity, name=name))
            await apply(
                command(
                    CreatePlayer,
                    player_id=env.player,
                    name="Player",
                    initial_location_id=env.home,
                    activity_state=PlayerActivity.INACTIVE,
                    availability_state=PlayerAvailability.BUSY,
                )
            )
            alice, billy = env.alice, env.bob
            banyue, belle = CharacterId(env.world, uuid4()), CharacterId(env.world, uuid4())
            for identity, name, location in (
                (alice, "Alice", env.home),
                (billy, "Billy", env.cafe),
                (banyue, "Banyue", env.cafe),
                (belle, "Belle", env.park),
            ):
                await apply(command(CreateCharacter, character_id=identity, name=name))
                await apply(
                    command(
                        PlaceCharacter,
                        character_id=identity,
                        location_id=location,
                        expected_state_revision=None,
                    )
                )
            await apply(
                command(
                    PlaceCharacter,
                    character_id=alice,
                    location_id=env.park,
                    expected_state_revision=Revision(),
                )
            )
            await apply(
                command(
                    ChangeRelationship,
                    source_id=billy,
                    target_id=banyue,
                    affinity_delta=7,
                    trust_delta=3,
                    familiarity_delta=9,
                    expected_relationship_revision=None,
                )
            )
            await apply(
                command(
                    ChangeRelationship,
                    source_id=banyue,
                    target_id=billy,
                    affinity_delta=-2,
                    trust_delta=4,
                    familiarity_delta=10,
                    expected_relationship_revision=None,
                )
            )
            relationship = command(
                ChangeRelationship,
                source_id=billy,
                target_id=banyue,
                trust_delta=2,
                expected_relationship_revision=Revision(1),
            )
            relationship_result = await apply(relationship)
            secret_id = KnowledgeAssertionId(env.world, uuid4())
            await apply(
                command(
                    AssertWorldTruth,
                    assertion_id=secret_id,
                    subject="Billy",
                    predicate="met",
                    value={"character": "Banyue", "location": "Cafe"},
                )
            )
            learned = {}
            for receiver in (billy, banyue):
                assertion_id = KnowledgeAssertionId(env.world, uuid4())
                acquisition = command(
                    AcquireKnowledge,
                    assertion_id=assertion_id,
                    receiver_id=receiver,
                    source_assertion_id=secret_id,
                    channel=ObservationChannel.WITNESSED,
                )
                learned[receiver] = (acquisition, await apply(acquisition))
            door_truth = KnowledgeAssertionId(env.world, uuid4())
            await apply(
                command(
                    AssertWorldTruth,
                    assertion_id=door_truth,
                    subject="door",
                    predicate="is",
                    value="locked",
                )
            )
            door_belief = command(
                FormCharacterBelief,
                assertion_id=KnowledgeAssertionId(env.world, uuid4()),
                character_id=alice,
                subject="door",
                predicate="is",
                value="unlocked",
                epistemic_status="misperceived",
                confidence=Decimal("0.4100"),
                valid_from=WorldTime(20),
                valid_to=WorldTime(800),
            )
            belief_result = await apply(door_belief)
            provenance = (await env.database.canonical_event_reader(env.world).read())[
                -1
            ].event.event_id
            await apply(
                command(
                    FormCharacterBelief,
                    assertion_id=KnowledgeAssertionId(env.world, uuid4()),
                    character_id=belle,
                    subject="vault",
                    predicate="code",
                    value={"guess": 17, "exact": False},
                    epistemic_status="mistaken reasoning",
                    confidence=Decimal("0.123456789123456789"),
                    valid_from=WorldTime(-30),
                    source_assertion_id=door_belief.assertion_id,
                    provenance_event_id=provenance,
                )
            )
            public_id = KnowledgeAssertionId(env.world, uuid4())
            await apply(
                command(
                    AssertWorldTruth,
                    assertion_id=public_id,
                    subject="season",
                    predicate="is",
                    value="autumn",
                )
            )
            await apply(
                command(
                    AcquireKnowledge,
                    assertion_id=KnowledgeAssertionId(env.world, uuid4()),
                    receiver_id=env.player,
                    source_assertion_id=public_id,
                    channel=ObservationChannel.DOCUMENT,
                )
            )

            # Another complete world deliberately reuses raw UUIDs; typed/world identity differs.
            other = WorldId(uuid4())
            other_home, other_cafe = (
                LocationId(other, env.home.value),
                LocationId(other, env.cafe.value),
            )
            other_player = PlayerId(other, env.player.value)
            other_alice, other_billy = (
                CharacterId(other, alice.value),
                CharacterId(other, billy.value),
            )

            def other_command(kind, **values):
                from livingworld.domain.contracts import RequestId

                return kind(request_id=RequestId(uuid4()), world_id=other, **values)

            await apply(other_command(CreateWorld, name="Other World", initial_time=WorldTime(123)))
            for identity, name in ((other_home, "Other Home"), (other_cafe, "Other Cafe")):
                await apply(other_command(CreateLocation, location_id=identity, name=name))
            await apply(
                other_command(
                    CreatePlayer,
                    player_id=other_player,
                    name="Other Player",
                    initial_location_id=other_home,
                )
            )
            for identity, name in ((other_alice, "Other Alice"), (other_billy, "Other Billy")):
                await apply(other_command(CreateCharacter, character_id=identity, name=name))
                await apply(
                    other_command(
                        PlaceCharacter,
                        character_id=identity,
                        location_id=other_home,
                        expected_state_revision=None,
                    )
                )
            await apply(
                other_command(
                    ChangeRelationship,
                    source_id=other_alice,
                    target_id=other_billy,
                    trust_delta=-3,
                    expected_relationship_revision=None,
                )
            )
            other_truth = KnowledgeAssertionId(other, door_truth.value)
            await apply(
                other_command(
                    AssertWorldTruth,
                    assertion_id=other_truth,
                    subject="door",
                    predicate="is",
                    value="sealed",
                )
            )
            await apply(
                other_command(
                    FormCharacterBelief,
                    assertion_id=KnowledgeAssertionId(other, door_belief.assertion_id.value),
                    character_id=other_alice,
                    subject="door",
                    predicate="is",
                    value="open",
                    epistemic_status="guessed",
                    valid_from=WorldTime(123),
                )
            )
            await apply(
                other_command(
                    AcquireKnowledge,
                    assertion_id=KnowledgeAssertionId(other, uuid4()),
                    source_assertion_id=other_truth,
                    receiver_id=other_billy,
                    channel=ObservationChannel.TOLD,
                )
            )
            other_before = await snapshot(env, PROJECTIONS + EVIDENCE, other)

            # Competing intentions were constructed from the same Presence revision.
            movements = [
                command(
                    MovePlayer,
                    player_id=env.player,
                    destination_id=destination,
                    expected_presence_revision=Revision(),
                )
                for destination in (env.cafe, env.park)
            ]
            results = await race_commands(env, *movements)
            winner = next(i for i, value in enumerate(results) if not isinstance(value, Exception))
            assert isinstance(results[1 - winner], ConcurrencyConflictError)
            assert results[winner].resulting_revision == Revision(1)
            committed.append((movements[winner], results[winner]))
            losing_request = movements[1 - winner].request_id
            async with env.database.unit_of_work() as uow:
                presence = await uow.players.presence(env.player)
                assert presence.location_id == movements[winner].destination_id
                assert presence.revision == Revision(1)
                assert (
                    presence.activity is PlayerActivity.INACTIVE
                    and presence.availability is PlayerAvailability.BUSY
                )

            unrelated = (
                command(
                    MovePlayer,
                    player_id=env.player,
                    destination_id=env.home,
                    expected_presence_revision=Revision(1),
                ),
                command(
                    ChangeRelationship,
                    source_id=billy,
                    target_id=banyue,
                    affinity_delta=1,
                    expected_relationship_revision=Revision(2),
                ),
            )
            results = await race_commands(env, *unrelated)
            assert all(not isinstance(result, Exception) for result in results)
            committed.extend(zip(unrelated, results, strict=True))
            duplicate = command(
                MovePlayer,
                player_id=env.player,
                destination_id=env.cafe,
                expected_presence_revision=Revision(2),
            )
            results = await race_commands(env, duplicate, duplicate)
            assert all(not isinstance(result, Exception) for result in results)
            assert replace(results[0], replayed=False) == replace(results[1], replayed=False)
            assert sorted(result.replayed for result in results) == [False, True]
            duplicate_result = next(result for result in results if not result.replayed)
            committed.append((duplicate, duplicate_result))
            assert duplicate_result.resulting_revision == Revision(3)
            assert await snapshot(env, PROJECTIONS + EVIDENCE, other) == other_before

            async def verify_knowledge():
                authority = env.database.world_truth_reader(env.world)
                authoritative = await authority.get(secret_id)
                assert authoritative.value == {"character": "Banyue", "location": "Cafe"}
                assert authoritative.scope is KnowledgeScope.TRUTH and authoritative.owner is None
                for receiver, (acquisition, result) in learned.items():
                    reader = env.database.character_knowledge_reader(receiver)
                    assertion = await reader.get(acquisition.assertion_id)
                    assert assertion.owner == receiver and assertion.value == authoritative.value
                    assert assertion.source_assertion_id == secret_id
                    assert await reader.get(secret_id) is None
                    assert result.observation_id is not None
                for reader in (
                    env.database.character_knowledge_reader(belle),
                    env.database.player_knowledge_reader(env.player),
                ):
                    assert await reader.get(secret_id) is None
                    for acquisition, _ in learned.values():
                        assert await reader.get(acquisition.assertion_id) is None
                    assert not any(
                        assertion.subject == "Billy" and assertion.predicate == "met"
                        for assertion in await reader.list()
                    )
                truth = await authority.get(door_truth)
                subjective = await env.database.character_knowledge_reader(alice).get(
                    door_belief.assertion_id
                )
                assert truth.value == "locked" and subjective.value == "unlocked"
                assert truth.assertion_id != subjective.assertion_id
                assert subjective.confidence == Decimal(
                    "0.41"
                ) and subjective.valid_from == WorldTime(20)
                assert (
                    subjective.valid_to == WorldTime(800)
                    and subjective.epistemic_status == "misperceived"
                )
                assert subjective.source_assertion_id is subjective.provenance_event_id is None
                assert await authority.get(subjective.assertion_id) is None
                assert await env.database.character_knowledge_reader(alice).get(door_truth) is None
                assert (
                    await env.database.world_truth_reader(other).get(other_truth)
                ).value == "sealed"
                for reader, wrong in (
                    (authority, other_truth),
                    (env.database.character_knowledge_reader(alice), other_truth),
                    (env.database.player_knowledge_reader(env.player), other_truth),
                ):
                    with pytest.raises(CrossWorldReferenceError):
                        await reader.get(wrong)
                return truth, subjective

            knowledge_before = await verify_knowledge()
            async with env.database.unit_of_work() as uow:
                assert (await uow.relationships.get(billy, banyue)).revision == Revision(3)
                reverse = await uow.relationships.get(banyue, billy)
                assert reverse.revision == Revision(1) and reverse.metrics.affinity == -2
            before_retry = await snapshot(env, PROJECTIONS + EVIDENCE)
            await env.restart()
            for retry, result in (
                (door_belief, belief_result),
                (relationship, relationship_result),
                (duplicate, duplicate_result),
            ):
                assert await env.handler.execute(retry) == replace(result, replayed=True)
            with pytest.raises(IdempotencyConflictError):
                await env.handler.execute(replace(relationship, affinity_delta=2))
            with pytest.raises(CrossWorldReferenceError):
                command(
                    MovePlayer,
                    player_id=env.player,
                    destination_id=other_home,
                    expected_presence_revision=Revision(3),
                )
            with pytest.raises(CrossWorldReferenceError):
                command(
                    FormCharacterBelief,
                    assertion_id=KnowledgeAssertionId(env.world, uuid4()),
                    character_id=alice,
                    subject="door",
                    predicate="is",
                    value="open",
                    epistemic_status="guessed",
                    valid_from=WorldTime(123),
                    source_assertion_id=other_truth,
                )
            assert await snapshot(env, PROJECTIONS + EVIDENCE) == before_retry

            # Successful commands and their per-command ordinals match ledger/receipt exactly.
            for world in (env.world, other):
                entries = await env.database.canonical_event_reader(world).read()
                expected_count = sum(
                    len(EVENTS[type(cmd)]) for cmd, _ in committed if cmd.world_id == world
                )
                assert len(entries) == expected_count
                positions = [entry.ledger_position for entry in entries]
                assert positions == list(range(1, expected_count + 1))
                assert entries[0].event.event_type == "WorldCreated"
                assert not any(entry.event.causation_id == losing_request for entry in entries)
                for cmd, _result in committed:
                    if cmd.world_id != world:
                        continue
                    events = [
                        entry.event
                        for entry in entries
                        if entry.event.causation_id == cmd.request_id
                    ]
                    assert tuple(event.event_type for event in events) == EVENTS[type(cmd)]
                    suffix = "action:" if isinstance(cmd, MovePlayer) else ""
                    assert [event.idempotency_key for event in events] == [
                        f"{cmd.request_id}:{suffix}{ordinal}" for ordinal in range(len(events))
                    ]
            receipts = await env.rows("command_receipts")
            assert len(receipts) == len(committed) + 1
            losing_receipt = next(
                row for row in receipts if row.request_id == losing_request.value.hex
            )
            assert losing_receipt.status == "rejected"
            for cmd, result in committed:
                receipt = next(
                    row for row in receipts if row.request_id == cmd.request_id.value.hex
                )
                assert receipt.status == "committed" and receipt.command_fingerprint
                assert (
                    json.loads(receipt.result_payload)["resulting_revision"]
                    == result.resulting_revision.value
                )
            for mutation in (
                "UPDATE world_events SET ledger_position=ledger_position+100",
                "DELETE FROM world_events",
            ):
                with pytest.raises(IntegrityError, match="world_event_immutable"):
                    async with env.database.engine.begin() as connection:
                        await connection.execute(text(mutation))
            assert await snapshot(env, PROJECTIONS + EVIDENCE) == before_retry

            projections, evidence = await snapshot(env, PROJECTIONS), await snapshot(env, EVIDENCE)
            rebuilder = ProjectionRebuilder(env.database.projection_rebuild_unit_of_work)
            rebuilt = await rebuilder.rebuild(env.world)
            assert await snapshot(env, PROJECTIONS) == projections
            assert await snapshot(env, EVIDENCE) == evidence
            assert await snapshot(env, PROJECTIONS + EVIDENCE, other) == other_before
            assert await verify_knowledge() == knowledge_before
            presence = next(item for item in rebuilt.presences if item.player_id == env.player)
            assert presence.location_id == env.cafe and presence.revision == Revision(3)
            # Replay returns the three ObservationRecorded projections. Event-occurrence
            # observations remain durable evidence and are intentionally not recomputed.
            assert len(rebuilt.observations) == 3
            await rebuilder.rebuild(other)
            assert await snapshot(env, PROJECTIONS) == projections
            assert await snapshot(env, EVIDENCE) == evidence
            assert await verify_knowledge() == knowledge_before
            assert await env.handler.execute(door_belief) == replace(belief_result, replayed=True)
            assert await env.handler.execute(duplicate) == replace(duplicate_result, replayed=True)
            assert (await env.rows("alembic_version"))[0].version_num == HEAD_REVISION
        finally:
            await env.database.close()

    asyncio.run(run())
