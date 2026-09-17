"""Canonical subjective roots, optional provenance and exact replay, with no inference."""

import asyncio
from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

import pytest
from livingworld.application.commands import AcquireKnowledge, AssertWorldTruth, FormCharacterBelief
from livingworld.application.errors import (
    EntityNotFoundError,
    IdempotencyConflictError,
    InvalidEventPayloadError,
)
from livingworld.application.fingerprints import command_fingerprint
from livingworld.application.replay import ProjectionRebuilder
from livingworld.domain.errors import CrossWorldReferenceError, DomainInvariantError
from livingworld.domain.identifiers import (
    CharacterId,
    EventId,
    KnowledgeAssertionId,
    PlayerId,
    WorldId,
)
from livingworld.domain.knowledge import KnowledgeScope, ObservationChannel
from livingworld.domain.values import Revision, WorldTime
from livingworld.infrastructure.persistence import replay as persistence_replay
from livingworld.infrastructure.persistence.unit_of_work import KnowledgeMutationRepository
from test_replay import EVIDENCE, PROJECTIONS, snapshot


def belief(env, **values):
    defaults = dict(
        assertion_id=KnowledgeAssertionId(env.world, uuid4()),
        character_id=env.alice,
        subject="door",
        predicate="is",
        value="unlocked",
        epistemic_status="guessed",
        confidence=Decimal("0.37000"),
        valid_from=WorldTime(-50),
        valid_to=WorldTime(900),
    )
    return env.command(FormCharacterBelief, **(defaults | values))


def test_belief_root_without_truth_source_or_observation_replays_exactly(environment, monkeypatch):
    async def run():
        env = environment
        try:
            await env.initialize()
            command = belief(env, value={"state": "unlocked", "clues": [True, 4, None]})
            before = await env.snapshot()
            result = await env.handler.execute(command)
            assert result.observation_id is None and result.resulting_revision == Revision()
            assertion = await env.database.character_knowledge_reader(env.alice).get(
                command.assertion_id
            )
            assert assertion.scope is KnowledgeScope.CHARACTER_BELIEF
            assert assertion.owner == env.alice and assertion.assertion_id == command.assertion_id
            assert assertion.subject == command.subject and assertion.predicate == command.predicate
            assert assertion.value == command.value and assertion.epistemic_status == "guessed"
            assert assertion.confidence == Decimal("0.37")
            assert (
                assertion.valid_from == command.valid_from
                and assertion.valid_to == command.valid_to
            )
            assert assertion.source_assertion_id is assertion.provenance_event_id is None
            assert await env.database.world_truth_reader(env.world).list() == ()
            assert await env.database.character_knowledge_reader(env.bob).list() == ()
            assert await env.database.player_knowledge_reader(env.player).list() == ()
            after = await env.snapshot()
            assert after["observations"] == before["observations"] == []
            assert len(after["world_events"]) == len(before["world_events"]) + 1
            entry = (await env.database.canonical_event_reader(env.world).read())[-1]
            assert (
                entry.event.event_type == "CharacterBeliefFormed"
                and entry.event.payload_version == 1
            )
            assert entry.event.payload["owner"]["kind"] == "CharacterId"
            expected, evidence = await snapshot(env, PROJECTIONS), await snapshot(env, EVIDENCE)
            with monkeypatch.context() as patch:

                def forbidden(*args, **kwargs):
                    raise AssertionError("Replay invoked a generator/clock/command")

                patch.setattr("uuid.uuid4", forbidden)
                patch.setattr(env.handler, "execute", forbidden)
                patch.setattr(env.clock, "now_utc", forbidden)
                await ProjectionRebuilder(env.database.projection_rebuild_unit_of_work).rebuild(
                    env.world
                )
            assert await snapshot(env, PROJECTIONS) == expected
            assert await snapshot(env, EVIDENCE) == evidence
            assert (
                await env.database.character_knowledge_reader(env.alice).get(command.assertion_id)
                == assertion
            )
            await env.restart()
            assert await env.handler.execute(command) == replace(result, replayed=True)
            assert await snapshot(env, EVIDENCE) == evidence
            with pytest.raises(IdempotencyConflictError):
                await env.handler.execute(replace(command, confidence=Decimal("0.38")))
        finally:
            await env.database.close()

    asyncio.run(run())


def test_contradictory_root_and_false_information_propagation_preserve_truth(environment):
    async def run():
        env = environment
        try:
            await env.initialize()
            truth_id = KnowledgeAssertionId(env.world, uuid4())
            await env.handler.execute(
                env.command(
                    AssertWorldTruth,
                    assertion_id=truth_id,
                    subject="door",
                    predicate="is",
                    value="locked",
                )
            )
            alice = belief(env)
            await env.handler.execute(alice)
            billy = env.command(
                AcquireKnowledge,
                assertion_id=KnowledgeAssertionId(env.world, uuid4()),
                receiver_id=env.bob,
                source_assertion_id=alice.assertion_id,
                channel=ObservationChannel.TOLD,
                confidence=Decimal("0.8"),
            )
            acquisition = await env.handler.execute(billy)

            async def verify():
                truth = await env.database.world_truth_reader(env.world).get(truth_id)
                belief_a = await env.database.character_knowledge_reader(env.alice).get(
                    alice.assertion_id
                )
                belief_b = await env.database.character_knowledge_reader(env.bob).get(
                    billy.assertion_id
                )
                assert truth.value == "locked" and truth.scope is KnowledgeScope.TRUTH
                assert belief_a.value == belief_b.value == "unlocked"
                assert belief_a.owner == env.alice and belief_b.owner == env.bob
                assert belief_b.source_assertion_id == belief_a.assertion_id
                assert (
                    await env.database.character_knowledge_reader(env.bob).get(alice.assertion_id)
                    is None
                )
                assert (
                    await env.database.character_knowledge_reader(env.alice).get(truth_id) is None
                )
                assert await env.database.player_knowledge_reader(env.player).list() == ()
                assert len(await env.rows("observations")) == 1
                assert (await env.rows("observations"))[
                    0
                ].observation_id == acquisition.observation_id.value.hex
                return truth, belief_a, belief_b

            expected = await verify()
            await ProjectionRebuilder(env.database.projection_rebuild_unit_of_work).rebuild(
                env.world
            )
            assert await verify() == expected
        finally:
            await env.database.close()

    asyncio.run(run())


def test_optional_private_source_and_event_provenance_are_preserved_without_access_grant(
    environment,
):
    async def run():
        env = environment
        try:
            await env.initialize()
            private = belief(env, character_id=env.bob, subject="private", value="private canary")
            await env.handler.execute(private)
            event_id = (await env.database.canonical_event_reader(env.world).read())[
                -1
            ].event.event_id
            command = belief(
                env,
                source_assertion_id=private.assertion_id,
                provenance_event_id=event_id,
                epistemic_status="mistaken inference",
            )
            await env.handler.execute(command)
            assertion = await env.database.character_knowledge_reader(env.alice).get(
                command.assertion_id
            )
            assert assertion.value == "unlocked"  # A supplied source does not require copying it.
            assert assertion.source_assertion_id == private.assertion_id
            assert assertion.provenance_event_id == event_id
            assert (
                await env.database.character_knowledge_reader(env.alice).get(private.assertion_id)
                is None
            )
            assert (
                await env.database.character_knowledge_reader(env.bob).get(command.assertion_id)
                is None
            )
            assert await env.rows("observations") == []
            await ProjectionRebuilder(env.database.projection_rebuild_unit_of_work).rebuild(
                env.world
            )
            assert (
                await env.database.character_knowledge_reader(env.alice).get(command.assertion_id)
                == assertion
            )
            assert (
                await env.database.character_knowledge_reader(env.alice).get(private.assertion_id)
                is None
            )
        finally:
            await env.database.close()

    asyncio.run(run())


@pytest.mark.parametrize("field", ["character_id", "source_assertion_id", "provenance_event_id"])
def test_missing_belief_references_fail_without_canonical_trace(environment, field):
    async def run():
        env = environment
        try:
            await env.initialize()
            identity = {
                "character_id": CharacterId,
                "source_assertion_id": KnowledgeAssertionId,
                "provenance_event_id": EventId,
            }[field](env.world, uuid4())
            before = await env.snapshot()
            with pytest.raises(EntityNotFoundError):
                await env.handler.execute(belief(env, **{field: identity}))
            assert await env.snapshot() == before
        finally:
            await env.database.close()

    asyncio.run(run())


@pytest.mark.parametrize(
    "field", ["assertion_id", "character_id", "source_assertion_id", "provenance_event_id"]
)
def test_cross_world_belief_references_are_rejected(environment, field):
    other = WorldId(uuid4())
    identity = {
        "assertion_id": KnowledgeAssertionId,
        "character_id": CharacterId,
        "source_assertion_id": KnowledgeAssertionId,
        "provenance_event_id": EventId,
    }[field](other, uuid4())
    with pytest.raises(CrossWorldReferenceError):
        belief(environment, **{field: identity})


@pytest.mark.parametrize(
    "values",
    [
        dict(character_id="Alice"),
        dict(character_id=None),
        dict(confidence=Decimal("1.1")),
        dict(epistemic_status=""),
        dict(valid_from=None),
        dict(valid_from=0),
        dict(character_id="player"),
    ],
)
def test_belief_boundary_uses_existing_domain_types(environment, values):
    if values.get("character_id") == "player":
        values = dict(character_id=PlayerId(environment.world, uuid4()))
    with pytest.raises(DomainInvariantError):
        belief(environment, **values)


def test_invalid_validity_and_post_projection_failure_are_atomic(environment, monkeypatch):
    async def run():
        env = environment
        try:
            await env.initialize()
            before = await env.snapshot()
            with pytest.raises(DomainInvariantError):
                await env.handler.execute(
                    belief(env, valid_from=WorldTime(5), valid_to=WorldTime(4))
                )
            assert await env.snapshot() == before
            command = belief(env)
            original = KnowledgeMutationRepository.add
            with monkeypatch.context() as patch:

                async def fail(self, assertion):
                    await original(self, assertion)
                    raise RuntimeError("injected_after_belief_projection")

                patch.setattr(KnowledgeMutationRepository, "add", fail)
                with pytest.raises(RuntimeError, match="injected_after_belief_projection"):
                    await env.handler.execute(command)
            assert await env.snapshot() == before
            assert not (await env.handler.execute(command)).replayed
            assert await env.rows("observations") == []
        finally:
            await env.database.close()

    asyncio.run(run())


def test_belief_fingerprint_covers_all_semantics_and_canonical_values(environment):
    command = belief(environment, value={"a": True, "b": 1})
    assert command_fingerprint(command) == command_fingerprint(
        replace(command, value={"b": 1, "a": True}, confidence=Decimal("0.37"))
    )
    mutations = dict(
        character_id=environment.bob,
        value={"a": 1, "b": 1},
        assertion_id=KnowledgeAssertionId(environment.world, uuid4()),
        subject="window",
        predicate="was",
        confidence=Decimal("0.38"),
        epistemic_status="reported",
        valid_from=WorldTime(-49),
        valid_to=None,
        source_assertion_id=KnowledgeAssertionId(environment.world, uuid4()),
        provenance_event_id=EventId(environment.world, uuid4()),
    )
    for field, value in mutations.items():
        assert command_fingerprint(command) != command_fingerprint(
            replace(command, **{field: value})
        )


@pytest.mark.parametrize(
    "damage", ["scope", "owner", "source", "provenance", "revision", "version"]
)
def test_invalid_belief_event_rolls_back_entire_rebuild(environment, monkeypatch, damage):
    async def run():
        env = environment
        try:
            await env.initialize()
            await env.handler.execute(belief(env))
            entries = list(await env.database.canonical_event_reader(env.world).read())
            entry = entries[-1]
            payload = dict(entry.event.payload)
            key, bad = {
                "scope": ("scope", "truth"),
                "owner": ("owner", None),
                "source": ("source_assertion_id", str(uuid4())),
                "provenance": ("provenance_event_id", str(uuid4())),
                "revision": ("revision", 1),
                "version": ("unused", None),
            }[damage]
            if damage == "version":
                from livingworld.application.errors import UnsupportedEventError

                event = replace(entry.event, payload_version=2)
                error = UnsupportedEventError
            else:
                payload[key] = bad
                event = replace(entry.event, payload=payload)
                error = InvalidEventPayloadError
            entries[-1] = replace(entry, event=event)
            before = await env.snapshot()
            with monkeypatch.context() as patch:

                async def damaged(session, world_id):
                    return tuple(entries)

                patch.setattr(persistence_replay, "_read", damaged)
                with pytest.raises(error):
                    await ProjectionRebuilder(env.database.projection_rebuild_unit_of_work).rebuild(
                        env.world
                    )
            assert await env.snapshot() == before
        finally:
            await env.database.close()

    asyncio.run(run())
