"""Knowledge boundaries tested through real SQLite and the canonical command pipeline."""

import asyncio
import json
from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

import pytest
from livingworld.application.commands import (
    AcquireKnowledge,
    AssertWorldTruth,
    CreateCharacter,
    CreateWorld,
)
from livingworld.application.errors import (
    EntityAlreadyExistsError,
    EntityNotFoundError,
    IdempotencyConflictError,
)
from livingworld.application.fingerprints import command_fingerprint
from livingworld.domain.errors import CrossWorldReferenceError, DomainInvariantError
from livingworld.domain.identifiers import CharacterId, KnowledgeAssertionId, ObservationId, WorldId
from livingworld.domain.knowledge import KnowledgeAssertion, KnowledgeScope, ObservationChannel
from livingworld.domain.values import WorldTime
from livingworld.infrastructure.persistence import knowledge_readers, unit_of_work
from livingworld.infrastructure.persistence.mapping import to_record
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError


def acquire(environment, source, receiver=None, **values):
    return environment.command(
        AcquireKnowledge,
        assertion_id=KnowledgeAssertionId(environment.world, uuid4()),
        source_assertion_id=source.assertion_id,
        receiver_id=receiver or environment.alice,
        channel=values.pop("channel", ObservationChannel.TOLD),
        **values,
    )


async def truth(environment, **values):
    command = environment.command(
        AssertWorldTruth,
        assertion_id=KnowledgeAssertionId(environment.world, uuid4()),
        subject=values.pop("subject", "Billy"),
        predicate=values.pop("predicate", "met"),
        value=values.pop("value", {"character": "Banyue", "location": "Cafe"}),
        **values,
    )
    result = await environment.handler.execute(command)
    assertion = await environment.database.world_truth_reader(environment.world).get(
        result.entity_reference
    )
    assert assertion.scope is KnowledgeScope.TRUTH and assertion.owner is None
    return command, assertion


async def private_belief_fixture(
    environment, owner, value, subject="private", predicate="believes"
):
    # Initial C-003A epistemic fixture, not a production write API or command bypass.
    assertion = KnowledgeAssertion(
        KnowledgeAssertionId(environment.world, uuid4()),
        environment.world,
        KnowledgeScope.CHARACTER_BELIEF,
        owner,
        subject,
        predicate,
        value,
        "believed",
        Decimal("0.37"),
        WorldTime(100),
    )
    async with environment.database._sessions.begin() as session:
        session.add(to_record(assertion))
    return assertion


def test_secret_billy_banyue_belle_player_and_sql_permissions(environment):
    async def run():
        await environment.initialize()
        try:
            billy_id, banyue_id, belle = (CharacterId(environment.world, uuid4()) for _ in range(3))
            for identity, name in ((billy_id, "Billy"), (banyue_id, "Banyue"), (belle, "Belle")):
                await environment.handler.execute(
                    environment.command(CreateCharacter, character_id=identity, name=name)
                )
            _, source = await truth(environment)
            billy = await environment.handler.execute(
                acquire(environment, source, billy_id, channel=ObservationChannel.WITNESSED)
            )
            banyue = await environment.handler.execute(
                acquire(environment, source, banyue_id, channel=ObservationChannel.WITNESSED)
            )
            canary = await private_belief_fixture(environment, banyue_id, "SECRET_CANARY_X")
            db = environment.database
            truth_reader = db.world_truth_reader(environment.world)
            billy_reader = db.character_knowledge_reader(billy_id)
            banyue_reader = db.character_knowledge_reader(banyue_id)
            belle_reader = db.character_knowledge_reader(belle)
            player_reader = db.player_knowledge_reader(environment.player)
            captured, materialized = [], []

            def capture(_conn, _cursor, statement, parameters, _context, _many):
                if (
                    statement.lstrip().upper().startswith("SELECT")
                    and "FROM knowledge_assertions" in statement
                ):
                    captured.append((statement, parameters))

            original = knowledge_readers.to_domain

            def record_materialization(record):
                value = original(record)
                materialized.append(value)
                return value

            event.listen(db.engine.sync_engine, "before_cursor_execute", capture)
            try:
                assert [value.assertion_id for value in await truth_reader.list()] == [
                    source.assertion_id
                ]
                assert [value.assertion_id for value in await billy_reader.list()] == [
                    billy.entity_reference
                ]
                assert {value.assertion_id for value in await banyue_reader.list()} == {
                    banyue.entity_reference,
                    canary.assertion_id,
                }
                assert await belle_reader.list() == await player_reader.list() == ()
                for reader in (billy_reader, belle_reader, player_reader):
                    # Verify rejected IDs never materialize an unauthorized ORM/domain result.
                    with pytest.MonkeyPatch.context() as patch:
                        patch.setattr(knowledge_readers, "to_domain", record_materialization)
                        assert await reader.get(source.assertion_id) is None
                        assert await reader.get(banyue.entity_reference) is None
                        assert await reader.get(canary.assertion_id) is None
                assert materialized == []
                assert await banyue_reader.get(billy.entity_reference) is None
                assert await truth_reader.get(canary.assertion_id) is None
                assert await billy_reader.get(billy.entity_reference) is not None
            finally:
                event.remove(db.engine.sync_engine, "before_cursor_execute", capture)
            for statement, parameters in captured:
                where = statement.partition("WHERE")[2]
                assert "knowledge_assertions.world_id =" in where
                assert "knowledge_assertions.scope =" in where
                assert environment.world.value.hex in parameters
                scope = parameters[1]
                if scope == KnowledgeScope.CHARACTER_BELIEF.value:
                    assert "knowledge_assertions.owner_character_id =" in where
                    assert "knowledge_assertions.owner_player_id IS NULL" in where
                    assert parameters[2] in {
                        billy_id.value.hex,
                        banyue_id.value.hex,
                        belle.value.hex,
                    }
                elif scope == KnowledgeScope.PLAYER_KNOWLEDGE.value:
                    assert "knowledge_assertions.owner_player_id =" in where
                    assert "knowledge_assertions.owner_character_id IS NULL" in where
                    assert parameters[2] == environment.player.value.hex
                else:
                    assert scope == "truth"
                    assert "knowledge_assertions.owner_character_id IS NULL" in where
                    assert "knowledge_assertions.owner_player_id IS NULL" in where
            assert len(captured) >= 15
            assert "SECRET_CANARY_X" not in repr(await billy_reader.list())
            assert "SECRET_CANARY_X" not in repr(await player_reader.list())
        finally:
            await environment.database.close()

    asyncio.run(run())


def test_truth_write_semantic_event_projection_receipt_and_retry(environment):
    async def run():
        await environment.initialize()
        try:
            before = await environment.snapshot()
            command, assertion = await truth(
                environment, confidence=Decimal("0.7500"), valid_from=WorldTime(-8)
            )
            after = await environment.snapshot()
            assert len(after["knowledge_assertions"]) == len(before["knowledge_assertions"]) + 1
            assert len(after["world_events"]) == len(before["world_events"]) + 1
            assert len(after["command_receipts"]) == len(before["command_receipts"]) + 1
            record = after["world_events"][-1]
            assert record.event_type == "WorldTruthAsserted"
            payload = json.loads(record.payload)
            assert payload["subject"] == "Billy" and payload["value"]["location"] == "Cafe"
            assert payload["owner"] is None and payload["scope"] == "truth"
            assert payload["confidence"] == "0.75" and payload["valid_from"] == -8
            assert assertion.provenance_event_id.value.hex == record.event_id
            result = await environment.handler.execute(command)
            assert result.replayed and result.entity_reference == assertion.assertion_id
            assert await environment.snapshot() == after
            with pytest.raises(IdempotencyConflictError):
                await environment.handler.execute(replace(command, value="changed"))
            with pytest.raises(EntityAlreadyExistsError):
                await environment.handler.execute(
                    replace(
                        command,
                        request_id=environment.command(
                            AssertWorldTruth,
                            assertion_id=command.assertion_id,
                            subject="x",
                            predicate="x",
                            value="x",
                        ).request_id,
                    )
                )
            assert await environment.snapshot() == after
        finally:
            await environment.database.close()

    asyncio.run(run())


@pytest.mark.parametrize(
    "channel",
    [channel for channel in ObservationChannel if channel is not ObservationChannel.INFERRED],
)
def test_told_or_explicit_channel_derives_owned_belief_without_source_access(environment, channel):
    async def run():
        await environment.initialize()
        try:
            source = await private_belief_fixture(
                environment, environment.bob, {"secret": ["incorrect"]}
            )
            result = await environment.handler.execute(
                acquire(environment, source, channel=channel)
            )
            reader = environment.database.character_knowledge_reader(environment.alice)
            derived = await reader.get(result.entity_reference)
            assert (
                derived.assertion_id != source.assertion_id and derived.owner == environment.alice
            )
            assert derived.scope is KnowledgeScope.CHARACTER_BELIEF
            assert (derived.subject, derived.predicate, derived.value) == (
                source.subject,
                source.predicate,
                source.value,
            )
            assert derived.epistemic_status == (
                "observed" if channel is ObservationChannel.WITNESSED else "reported"
            )
            assert derived.confidence is None  # No certainty copied/promoted from a private belief.
            assert derived.source_assertion_id == source.assertion_id
            assert derived.valid_from == WorldTime(123) and derived.valid_to is None
            assert await reader.get(source.assertion_id) is None
            assert await environment.database.world_truth_reader(environment.world).list() == ()
            assert (
                await environment.database.character_knowledge_reader(environment.bob).get(
                    source.assertion_id
                )
                == source
            )
            events = (await environment.rows("world_events"))[-2:]
            assert [row.event_type for row in events] == [
                "ObservationRecorded",
                "KnowledgeAcquired",
            ]
            assert derived.provenance_event_id.value.hex == events[1].event_id
            assert [row.idempotency_key for row in events] == [
                f"{result.request_id}:0",
                f"{result.request_id}:1",
            ]
            assert all(
                json.loads(row.payload)["observation_id"] == str(result.observation_id.value)
                for row in events
            )
            observations = await environment.rows("observations")
            assert len(observations) == 1
            row = observations[0]
            assert row.principal_id == environment.alice.value.hex
            assert row.target_id == source.assertion_id.value.hex and row.target_kind == "assertion"
            assert row.channel == channel.value and row.observed_at == 123
            assert type(result.observation_id) is ObservationId
        finally:
            await environment.database.close()

    asyncio.run(run())


def test_contradictory_belief_and_truth_are_independent(environment):
    async def run():
        await environment.initialize()
        try:
            _, source = await truth(environment, subject="door", predicate="state", value="locked")
            wrong = await private_belief_fixture(
                environment, environment.alice, "unlocked", subject="door", predicate="state"
            )
            assert await environment.database.character_knowledge_reader(
                environment.alice
            ).list() == (wrong,)
            assert await environment.database.world_truth_reader(environment.world).list() == (
                source,
            )
        finally:
            await environment.database.close()

    asyncio.run(run())


def test_player_acquisition_keeps_truth_and_other_stores_unchanged_and_can_be_source(environment):
    async def run():
        await environment.initialize()
        try:
            _, source = await truth(environment)
            before_truth = await environment.database.world_truth_reader(environment.world).list()
            result = await environment.handler.execute(
                acquire(
                    environment,
                    source,
                    environment.player,
                    channel=ObservationChannel.NEWS,
                    confidence=Decimal("0.4"),
                )
            )
            reader = environment.database.player_knowledge_reader(environment.player)
            derived = await reader.get(result.entity_reference)
            assert (
                derived.scope is KnowledgeScope.PLAYER_KNOWLEDGE
                and derived.owner == environment.player
            )
            assert (
                derived.source_assertion_id == source.assertion_id
                and derived.confidence == Decimal("0.4")
            )
            assert await reader.get(source.assertion_id) is None
            assert (
                await environment.database.world_truth_reader(environment.world).list()
                == before_truth
            )
            for principal in (environment.alice, environment.bob):
                character = environment.database.character_knowledge_reader(principal)
                assert (
                    await character.list() == ()
                    and await character.get(derived.assertion_id) is None
                )
            # An explicit trusted message may copy PlayerKnowledge without granting source access.
            copied = await environment.handler.execute(
                acquire(environment, derived, channel=ObservationChannel.MESSAGE)
            )
            character = environment.database.character_knowledge_reader(environment.alice)
            belief = await character.get(copied.entity_reference)
            assert belief.source_assertion_id == derived.assertion_id
            assert await character.get(derived.assertion_id) is None
            assert await reader.get(copied.entity_reference) is None
            assert (
                await environment.database.world_truth_reader(environment.world).list()
                == before_truth
            )
        finally:
            await environment.database.close()

    asyncio.run(run())


def test_request_retry_restart_and_different_request_same_observation_coordinates(environment):
    async def run():
        await environment.initialize()
        try:
            _, source = await truth(environment)
            command = acquire(environment, source)
            result = await environment.handler.execute(command)
            before = await environment.snapshot()
            retry = await environment.handler.execute(command)
            assert retry == replace(result, replayed=True)
            await environment.restart()
            assert await environment.handler.execute(command) == retry
            assert await environment.snapshot() == before
            independent = acquire(environment, source)
            second = await environment.handler.execute(independent)
            assert second.observation_id != result.observation_id
            rows = await environment.rows("observations")
            assert len(rows) == 2
            coordinates = (
                "world_id",
                "principal_kind",
                "principal_id",
                "target_kind",
                "target_id",
                "channel",
                "observed_at",
            )
            assert tuple(getattr(rows[0], key) for key in coordinates) == tuple(
                getattr(rows[1], key) for key in coordinates
            )
            assert (
                len(await environment.database.character_knowledge_reader(environment.alice).list())
                == 2
            )
            assert len(await environment.rows("world_events")) == len(before["world_events"]) + 2
        finally:
            await environment.database.close()

    asyncio.run(run())


@pytest.mark.parametrize(
    "changed",
    [
        "assertion_id",
        "source_assertion_id",
        "receiver_id",
        "channel",
        "epistemic_status",
        "confidence",
    ],
)
def test_acquisition_semantic_fingerprint_conflicts(environment, changed):
    async def run():
        await environment.initialize()
        try:
            _, source = await truth(environment)
            _, other_source = await truth(environment, value="other")
            command = acquire(environment, source)
            await environment.handler.execute(command)
            before = await environment.snapshot()
            values = {
                "assertion_id": KnowledgeAssertionId(environment.world, uuid4()),
                "source_assertion_id": other_source.assertion_id,
                "receiver_id": environment.bob,
                "channel": ObservationChannel.MESSAGE,
                "epistemic_status": "uncertain",
                "confidence": Decimal("0.8"),
            }
            with pytest.raises(IdempotencyConflictError):
                await environment.handler.execute(replace(command, **{changed: values[changed]}))
            assert await environment.snapshot() == before
        finally:
            await environment.database.close()

    asyncio.run(run())


def test_fingerprint_uses_resolved_defaults_exact_decimal_and_frozen_json(environment):
    source = KnowledgeAssertionId(environment.world, uuid4())
    command = environment.command(
        AcquireKnowledge,
        assertion_id=KnowledgeAssertionId(environment.world, uuid4()),
        receiver_id=environment.alice,
        source_assertion_id=source,
        channel=ObservationChannel.TOLD,
    )
    assert command.epistemic_status == "reported"
    assert command_fingerprint(command) == command_fingerprint(
        replace(command, epistemic_status="reported")
    )
    assert command_fingerprint(
        replace(command, confidence=Decimal("0.500"))
    ) == command_fingerprint(replace(command, confidence=Decimal("0.5")))
    value = {"array": [1, {"secret": "original"}]}
    assertion = environment.command(
        AssertWorldTruth, assertion_id=source, subject="s", predicate="p", value=value
    )
    digest = command_fingerprint(assertion)
    value["array"][1]["secret"] = "changed"
    assert command_fingerprint(assertion) == digest


@pytest.mark.parametrize(
    "point", ["event_0", "event_1", "observation", "assertion", "receipt", "commit"]
)
def test_acquisition_faults_roll_back_everything_and_request_can_retry(
    environment, monkeypatch, point
):
    async def run():
        await environment.initialize()
        try:
            _, source = await truth(environment)
            command = acquire(environment, source)
            before = await environment.snapshot()
            targets = {
                "event_0": (unit_of_work.EventAppender, "append"),
                "event_1": (unit_of_work.EventAppender, "append"),
                "observation": (unit_of_work.ObservationAppender, "add"),
                "assertion": (unit_of_work.KnowledgeMutationRepository, "add"),
                "receipt": (unit_of_work.CommandReceiptRepository, "add"),
                "commit": (unit_of_work.SqlAlchemyUnitOfWork, "commit"),
            }
            cls, method = targets[point]
            original = getattr(cls, method)

            async def fail(self, *args):
                if point != "commit":
                    await original(self, *args)  # Fail AFTER the actual INSERT/flush.
                if point.startswith("event_") and args[0].event_type != (
                    "ObservationRecorded" if point == "event_0" else "KnowledgeAcquired"
                ):
                    return
                raise RuntimeError("injected_acquisition_failure")

            with monkeypatch.context() as patch:
                patch.setattr(cls, method, fail)
                with pytest.raises(RuntimeError, match="injected_acquisition"):
                    await environment.handler.execute(command)
            await environment.restart()
            assert await environment.snapshot() == before
            result = await environment.handler.execute(command)
            after = await environment.snapshot()
            assert len(after["observations"]) == 1 and len(after["knowledge_assertions"]) == 2
            assert len(after["world_events"]) == len(before["world_events"]) + 2
            assert len(after["command_receipts"]) == len(before["command_receipts"]) + 1
            assert await environment.handler.execute(command) == replace(result, replayed=True)
            assert await environment.snapshot() == after
        finally:
            await environment.database.close()

    asyncio.run(run())


@pytest.mark.parametrize("missing", ["source", "receiver", "inferred", "duplicate_assertion"])
def test_invalid_acquisition_never_partially_commits(environment, missing):
    async def run():
        await environment.initialize()
        try:
            _, source = await truth(environment)
            command = acquire(environment, source)
            error = EntityNotFoundError
            if missing == "source":
                command = replace(
                    command, source_assertion_id=KnowledgeAssertionId(environment.world, uuid4())
                )
            elif missing == "receiver":
                command = replace(command, receiver_id=CharacterId(environment.world, uuid4()))
            elif missing == "inferred":
                command, error = (
                    replace(command, channel=ObservationChannel.INFERRED),
                    DomainInvariantError,
                )
            else:
                command, error = (
                    replace(command, assertion_id=source.assertion_id),
                    EntityAlreadyExistsError,
                )
            before = await environment.snapshot()
            with pytest.raises(error):
                await environment.handler.execute(command)
            assert await environment.snapshot() == before
        finally:
            await environment.database.close()

    asyncio.run(run())


@pytest.mark.parametrize("field", ["source_assertion_id", "receiver_id", "assertion_id"])
def test_cross_world_acquisition_rejected_at_command_boundary(environment, field):
    world = WorldId(uuid4())
    values = {
        "source_assertion_id": KnowledgeAssertionId(world, uuid4()),
        "receiver_id": CharacterId(world, uuid4()),
        "assertion_id": KnowledgeAssertionId(world, uuid4()),
    }
    source = KnowledgeAssertionId(environment.world, uuid4())
    command = environment.command(
        AcquireKnowledge,
        assertion_id=source,
        receiver_id=environment.alice,
        source_assertion_id=source,
        channel=ObservationChannel.TOLD,
    )
    with pytest.raises(CrossWorldReferenceError):
        replace(command, **{field: values[field]})


def test_scoped_readers_isolate_worlds_with_colliding_uuid_values(environment):
    async def run():
        await environment.initialize()
        try:
            _, source = await truth(environment)
            await environment.handler.execute(acquire(environment, source))
            other = WorldId(uuid4())
            request = environment.command(CreateWorld, name="placeholder").request_id
            await environment.handler.execute(
                CreateWorld(request_id=request, world_id=other, name="Other")
            )
            other_character = CharacterId(other, environment.alice.value)
            await environment.handler.execute(
                CreateCharacter(
                    request_id=environment.command(CreateWorld, name="x").request_id,
                    world_id=other,
                    character_id=other_character,
                    name="Same UUID",
                )
            )
            reader = environment.database.character_knowledge_reader(other_character)
            assert await reader.list() == ()
            with pytest.raises(CrossWorldReferenceError):
                await reader.get(source.assertion_id)
            assert await reader.get(KnowledgeAssertionId(other, source.assertion_id.value)) is None
            assert await environment.database.world_truth_reader(other).list() == ()
            assert (
                await environment.database.world_truth_reader(other).get(
                    KnowledgeAssertionId(other, source.assertion_id.value)
                )
                is None
            )
        finally:
            await environment.database.close()

    asyncio.run(run())


def test_knowledge_events_remain_append_only(environment):
    async def run():
        await environment.initialize()
        try:
            _, source = await truth(environment)
            await environment.handler.execute(acquire(environment, source))
            before = await environment.snapshot()
            for operation in (
                "UPDATE world_events SET event_type = 'corrupt' "
                "WHERE event_type = 'KnowledgeAcquired'",
                "DELETE FROM world_events WHERE event_type = 'ObservationRecorded'",
            ):
                with pytest.raises(IntegrityError, match="world_event_immutable"):
                    async with environment.database.engine.begin() as connection:
                        await connection.execute(text(operation))
            assert await environment.snapshot() == before
        finally:
            await environment.database.close()

    asyncio.run(run())


def test_rolled_back_observation_has_no_durable_identity_and_retry_generates_new(
    environment, monkeypatch
):
    async def run():
        await environment.initialize()
        try:
            _, source = await truth(environment)
            command = acquire(environment, source)
            first_id, retry_id = uuid4(), uuid4()
            generations = iter((first_id, retry_id))
            from livingworld.application import command_handler

            with monkeypatch.context() as patch:
                patch.setattr(command_handler, "uuid4", lambda: next(generations))
                original = unit_of_work.ObservationAppender.add

                async def fail(self, observation):
                    assert observation.observation_id.value == first_id
                    await original(self, observation)
                    raise RuntimeError("rollback_observation")

                with monkeypatch.context() as failure:
                    failure.setattr(unit_of_work.ObservationAppender, "add", fail)
                    with pytest.raises(RuntimeError, match="rollback_observation"):
                        await environment.handler.execute(command)
                assert await environment.rows("observations") == []
                result = await environment.handler.execute(command)
                assert result.observation_id.value == retry_id
                assert result.observation_id.value.version == 4
                assert (await environment.rows("observations"))[0].observation_id == retry_id.hex
                assert (
                    await environment.handler.execute(command)
                ).observation_id == result.observation_id
        finally:
            await environment.database.close()

    asyncio.run(run())


def test_truth_projection_failure_rolls_back_event_and_receipt(environment, monkeypatch):
    async def run():
        await environment.initialize()
        try:
            command = environment.command(
                AssertWorldTruth,
                assertion_id=KnowledgeAssertionId(environment.world, uuid4()),
                subject="s",
                predicate="p",
                value=True,
            )
            before = await environment.snapshot()
            original = unit_of_work.KnowledgeMutationRepository.add

            async def fail(self, assertion):
                await original(self, assertion)
                raise RuntimeError("rollback_truth")

            with monkeypatch.context() as patch:
                patch.setattr(unit_of_work.KnowledgeMutationRepository, "add", fail)
                with pytest.raises(RuntimeError, match="rollback_truth"):
                    await environment.handler.execute(command)
            await environment.restart()
            assert await environment.snapshot() == before
            assert not (await environment.handler.execute(command)).replayed
        finally:
            await environment.database.close()

    asyncio.run(run())
