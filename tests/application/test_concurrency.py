"""Resource CAS, explicit absence, rollback and bounded duplicate resolution."""

import asyncio
from dataclasses import replace
from uuid import uuid4

import pytest
from concurrency_support import race_commands
from livingworld.application.commands import (
    AcquireKnowledge,
    AssertWorldTruth,
    ChangeRelationship,
    CreatePlayer,
    CreateWorld,
    FormCharacterBelief,
    MovePlayer,
    PlaceCharacter,
)
from livingworld.application.errors import IdempotencyConflictError
from livingworld.application.replay import ProjectionRebuilder
from livingworld.domain.errors import ConcurrencyConflictError, DomainInvariantError
from livingworld.domain.identifiers import KnowledgeAssertionId, PlayerId, WorldId
from livingworld.domain.knowledge import ObservationChannel
from livingworld.domain.values import Revision, WorldTime
from livingworld.infrastructure.persistence.mapping import to_record
from livingworld.infrastructure.persistence.models import (
    CharacterStateRecord,
    PlayerPresenceRecord,
    RelationshipRecord,
    WorldEventRecord,
)
from livingworld.infrastructure.persistence.unit_of_work import (
    CharacterRepository,
    CommandReceiptRepository,
    PlayerRepository,
    RelationshipRepository,
)
from sqlalchemy import event, func, select, update
from test_replay import EVIDENCE, PROJECTIONS, snapshot


def mutable_command(env, kind, expected, **values):
    if kind == "presence":
        return env.command(
            MovePlayer,
            player_id=env.player,
            destination_id=values.get("destination", env.cafe),
            expected_presence_revision=expected,
        )
    if kind == "state":
        return env.command(
            PlaceCharacter,
            character_id=env.alice,
            location_id=values.get("destination", env.cafe),
            expected_state_revision=expected,
        )
    return env.command(
        ChangeRelationship,
        source_id=env.alice,
        target_id=env.bob,
        affinity_delta=values.get("delta", 3),
        expected_relationship_revision=expected,
    )


@pytest.mark.parametrize("kind", ["presence", "state", "relationship"])
def test_exact_expected_revision_and_stale_retry_priority(environment, kind):
    async def run():
        env = environment
        try:
            await env.initialize()
            if kind != "presence":
                await env.handler.execute(mutable_command(env, kind, None))
            expected = Revision(1 if kind == "relationship" else 0)
            command = mutable_command(env, kind, expected)
            result = await env.handler.execute(command)
            assert result.resulting_revision == expected.advance(expected)
            state = await env.snapshot()
            await env.restart()
            assert await env.handler.execute(command) == replace(result, replayed=True)
            assert await env.snapshot() == state
            field = {
                "presence": "expected_presence_revision",
                "state": "expected_state_revision",
                "relationship": "expected_relationship_revision",
            }[kind]
            with pytest.raises(IdempotencyConflictError):
                await env.handler.execute(replace(command, **{field: result.resulting_revision}))
            with pytest.raises(ConcurrencyConflictError) as conflict:
                await env.handler.execute(
                    replace(command, request_id=env.command(CreateWorld, name="unused").request_id)
                )
            assert conflict.value.expected_revision == expected
            assert conflict.value.actual_revision == result.resulting_revision
            assert (
                conflict.value.resource_kind
                == {
                    "presence": "PlayerPresence",
                    "state": "CharacterState",
                    "relationship": "Relationship",
                }[kind]
            )
            assert conflict.value.resource_identity is not None
            assert await env.snapshot() == state
        finally:
            await env.database.close()

    asyncio.run(run())


@pytest.mark.parametrize("kind", ["state", "relationship"])
def test_absent_and_revision_zero_are_distinct(environment, kind):
    async def run():
        env = environment
        try:
            await env.initialize()
            before = await env.snapshot()
            with pytest.raises(ConcurrencyConflictError):
                await env.handler.execute(mutable_command(env, kind, Revision()))
            assert await env.snapshot() == before
            result = await env.handler.execute(mutable_command(env, kind, None))
            assert result.resulting_revision == Revision(0 if kind == "state" else 1)
            before = await env.snapshot()
            with pytest.raises(ConcurrencyConflictError):
                await env.handler.execute(mutable_command(env, kind, None))
            assert await env.snapshot() == before
        finally:
            await env.database.close()

    asyncio.run(run())


@pytest.mark.parametrize("kind", ["presence", "state", "relationship"])
def test_two_independent_mutations_have_one_winner_and_replay(environment, kind):
    async def run():
        env = environment
        try:
            await env.initialize()
            before = await env.snapshot()
            expected = Revision() if kind == "presence" else None
            commands = [
                mutable_command(env, kind, expected, destination=destination, delta=delta)
                for destination, delta in ((env.cafe, 3), (env.park, 7))
            ]
            outcomes = await race_commands(env, *commands)
            failures = [value for value in outcomes if isinstance(value, Exception)]
            assert len(failures) == 1 and isinstance(failures[0], ConcurrencyConflictError)
            winner = next(
                index for index, value in enumerate(outcomes) if not isinstance(value, Exception)
            )
            loser = 1 - winner
            result = outcomes[winner]
            expected_result = Revision(0 if kind == "state" else 1)
            assert result.resulting_revision == expected_result
            after = await env.snapshot()
            assert len(after["world_events"]) == len(before["world_events"]) + 1
            assert len(after["command_receipts"]) == len(before["command_receipts"]) + 1
            assert not any(
                row.causation_request_id == commands[loser].request_id.value.hex
                for row in after["world_events"]
            )
            assert not any(
                row.request_id == commands[loser].request_id.value.hex
                for row in after["command_receipts"]
            )
            async with env.database.unit_of_work() as uow:
                if kind == "presence":
                    state = await uow.players.presence(env.player)
                    assert state.location_id == commands[winner].destination_id
                elif kind == "state":
                    state = await uow.characters.state(env.alice)
                    assert state.location_id == commands[winner].location_id
                else:
                    state = await uow.relationships.get(env.alice, env.bob)
                    assert state.metrics.affinity == commands[winner].affinity_delta
                    assert await uow.relationships.get(env.bob, env.alice) is None
                assert state.revision == expected_result
            entries = await env.database.canonical_event_reader(env.world).read()
            positions = [entry.ledger_position for entry in entries]
            assert positions == sorted(set(positions))
            assert after["world_ledger_cursors"][0].last_position == positions[-1]
            state, evidence = await snapshot(env, PROJECTIONS), await snapshot(env, EVIDENCE)
            await ProjectionRebuilder(env.database.projection_rebuild_unit_of_work).rebuild(
                env.world
            )
            assert await snapshot(env, PROJECTIONS) == state
            assert await snapshot(env, EVIDENCE) == evidence
        finally:
            await env.database.close()

    asyncio.run(run())


@pytest.mark.parametrize("kind", ["presence", "player", "acquisition", "belief"])
def test_concurrent_exact_duplicate_has_one_durable_outcome(environment, kind):
    async def run():
        env = environment
        try:
            await env.initialize()
            if kind == "presence":
                command = mutable_command(env, "presence", Revision())
                count = 1
            elif kind == "player":
                command = env.command(
                    CreatePlayer,
                    player_id=PlayerId(env.world, uuid4()),
                    name="Other player",
                    initial_location_id=env.cafe,
                )
                count = 2
            elif kind == "belief":
                command = env.command(
                    FormCharacterBelief,
                    assertion_id=KnowledgeAssertionId(env.world, uuid4()),
                    character_id=env.alice,
                    subject="door",
                    predicate="is",
                    value="unlocked",
                    epistemic_status="guessed",
                    valid_from=WorldTime(100),
                )
                count = 1
            else:
                source = KnowledgeAssertionId(env.world, uuid4())
                await env.handler.execute(
                    env.command(
                        AssertWorldTruth,
                        assertion_id=source,
                        subject="door",
                        predicate="is",
                        value="locked",
                    )
                )
                command = env.command(
                    AcquireKnowledge,
                    assertion_id=KnowledgeAssertionId(env.world, uuid4()),
                    source_assertion_id=source,
                    receiver_id=env.alice,
                    channel=ObservationChannel.TOLD,
                )
                count = 2
            before = await env.snapshot()
            outcomes = await race_commands(env, command, command)
            assert all(not isinstance(value, Exception) for value in outcomes)
            assert replace(outcomes[0], replayed=False) == replace(outcomes[1], replayed=False)
            assert sorted(value.replayed for value in outcomes) == [False, True]
            after = await env.snapshot()
            assert len(after["world_events"]) == len(before["world_events"]) + count
            assert len(after["command_receipts"]) == len(before["command_receipts"]) + 1
            if kind == "acquisition":
                assert outcomes[0].observation_id == outcomes[1].observation_id
                assert len(after["observations"]) == len(before["observations"]) + 1
            elif kind == "presence":
                assert after["player_presences"][0].revision == 1
            elif kind == "player":
                assert len(after["players"]) == len(before["players"]) + 1
                assert len(after["player_presences"]) == len(before["player_presences"]) + 1
            else:
                assert len(after["knowledge_assertions"]) == len(before["knowledge_assertions"]) + 1
                assert after["observations"] == before["observations"]
        finally:
            await env.database.close()

    asyncio.run(run())


def test_unrelated_resources_do_not_use_a_global_world_revision(environment):
    async def run():
        env = environment
        try:
            await env.initialize()
            reverse = env.command(
                ChangeRelationship,
                source_id=env.bob,
                target_id=env.alice,
                affinity_delta=-4,
                expected_relationship_revision=None,
            )
            await env.handler.execute(reverse)
            before_world = await env.rows("worlds")
            commands = (
                mutable_command(env, "presence", Revision()),
                mutable_command(env, "relationship", None),
            )
            results = await race_commands(env, *commands)
            assert all(not isinstance(result, Exception) for result in results)
            assert await env.rows("worlds") == before_world
            async with env.database.unit_of_work() as uow:
                assert (await uow.relationships.get(env.bob, env.alice)).metrics.affinity == -4
            after = await env.snapshot()
            with pytest.raises(ConcurrencyConflictError):
                await env.handler.execute(mutable_command(env, "relationship", None))
            assert await env.snapshot() == after
        finally:
            await env.database.close()

    asyncio.run(run())


@pytest.mark.parametrize("kind", ["presence", "state", "relationship"])
def test_cas_zero_after_events_rolls_back_cursor_events_projection_receipt(
    environment, monkeypatch, kind
):
    async def run():
        env = environment
        try:
            await env.initialize()
            if kind != "presence":
                await env.handler.execute(mutable_command(env, kind, None))
            expected = Revision(1 if kind == "relationship" else 0)
            command = mutable_command(env, kind, expected)
            before = await env.snapshot()
            repository, method, record = {
                "presence": (PlayerRepository, "replace_presence", PlayerPresenceRecord),
                "state": (CharacterRepository, "put_state", CharacterStateRecord),
                "relationship": (RelationshipRepository, "put", RelationshipRecord),
            }[kind]
            original = getattr(repository, method)
            statements = []

            def capture(connection, cursor, statement, parameters, context, executemany):
                if statement.startswith("UPDATE " + record.__tablename__):
                    statements.append(statement)

            event.listen(env.database.engine.sync_engine, "before_cursor_execute", capture)
            try:
                with monkeypatch.context() as patch:

                    async def intervening_write(self, state, expected_revision):
                        count = await self._session.scalar(
                            select(func.count())
                            .select_from(WorldEventRecord)
                            .where(
                                WorldEventRecord.causation_request_id == command.request_id.value
                            )
                        )
                        assert count == 1
                        # Test-only competing version introduced after handler read/event flush.
                        await self._session.execute(
                            update(record).values(revision=record.revision + 1)
                        )
                        await original(self, state, expected_revision)

                    patch.setattr(repository, method, intervening_write)
                    with pytest.raises(ConcurrencyConflictError) as conflict:
                        await env.handler.execute(command)
                    assert conflict.value.expected_revision == expected
                    assert conflict.value.actual_revision is None
                assert await env.snapshot() == before
                cas = statements[-1]
                assert (
                    "WHERE" in cas
                    and ".world_id = " in cas
                    and ".revision = " in cas.split("WHERE")[1]
                )
                assert not (await env.handler.execute(command)).replayed
            finally:
                event.remove(env.database.engine.sync_engine, "before_cursor_execute", capture)
        finally:
            await env.database.close()

    asyncio.run(run())


@pytest.mark.parametrize("kind", ["state", "relationship"])
def test_optional_insert_constraint_collision_is_domain_conflict_and_atomic(
    environment, monkeypatch, kind
):
    async def run():
        env = environment
        try:
            await env.initialize()
            before = await env.snapshot()
            repository, method = (
                (CharacterRepository, "put_state")
                if kind == "state"
                else (RelationshipRepository, "put")
            )
            original = getattr(repository, method)
            with monkeypatch.context() as patch:

                async def colliding_insert(self, state, expected_revision):
                    self._session.add(to_record(state))
                    await self._session.flush()
                    await original(self, state, expected_revision)

                patch.setattr(repository, method, colliding_insert)
                with pytest.raises(ConcurrencyConflictError):
                    await env.handler.execute(mutable_command(env, kind, None))
            assert await env.snapshot() == before
        finally:
            await env.database.close()

    asyncio.run(run())


def test_event_collision_rolls_back_then_resolves_receipt_once(environment, monkeypatch):
    async def run():
        env = environment
        try:
            await env.initialize()
            command = mutable_command(env, "presence", Revision())
            async with env.database.unit_of_work() as uow:
                old_presence = await uow.players.presence(env.player)
            result = await env.handler.execute(command)
            before = await env.snapshot()
            original = CommandReceiptRepository.existing
            reads = []
            with monkeypatch.context() as patch:

                async def miss_once(self, request_id, fingerprint):
                    reads.append(self._session)
                    return (
                        None if len(reads) == 1 else await original(self, request_id, fingerprint)
                    )

                patch.setattr(CommandReceiptRepository, "existing", miss_once)

                async def stale_snapshot(self, player_id):
                    return old_presence

                patch.setattr(PlayerRepository, "presence", stale_snapshot)
                # Simulate a raced receipt lookup and stale read; event PK/key collides.
                # Only receipt resolution follows rollback, never another mutation execution.
                assert await env.handler.execute(command) == replace(result, replayed=True)
            assert len(reads) == 2 and reads[0] is not reads[1]
            assert await env.snapshot() == before
        finally:
            await env.database.close()

    asyncio.run(run())


def test_receipt_unique_collision_rolls_back_world_then_checks_once(environment, monkeypatch):
    async def run():
        env = environment
        try:
            await env.initialize()
            original_command = mutable_command(env, "presence", Revision())
            await env.handler.execute(original_command)
            different = CreateWorld(
                request_id=original_command.request_id, world_id=WorldId(uuid4()), name="Other"
            )
            before = await env.snapshot()
            original = CommandReceiptRepository.existing
            sessions = []
            with monkeypatch.context() as patch:

                async def miss_once(self, request_id, fingerprint):
                    sessions.append(self._session)
                    return (
                        None
                        if len(sessions) == 1
                        else await original(self, request_id, fingerprint)
                    )

                patch.setattr(CommandReceiptRepository, "existing", miss_once)
                with pytest.raises(IdempotencyConflictError):
                    await env.handler.execute(different)
            assert len(sessions) == 2 and sessions[0] is not sessions[1]
            assert await env.snapshot() == before
        finally:
            await env.database.close()

    asyncio.run(run())


@pytest.mark.parametrize("kind", ["presence", "state", "relationship"])
@pytest.mark.parametrize("value", [0, True, "0"])
def test_revision_inputs_are_typed(environment, kind, value):
    with pytest.raises(DomainInvariantError):
        mutable_command(environment, kind, value)


@pytest.mark.parametrize("kind", ["presence", "state", "relationship"])
def test_mutation_cannot_omit_concurrency_expectation(environment, kind):
    env = environment
    command, fields, required = {
        "presence": (
            MovePlayer,
            dict(player_id=env.player, destination_id=env.cafe),
            "expected_presence_revision",
        ),
        "state": (
            PlaceCharacter,
            dict(character_id=env.alice, location_id=env.cafe),
            "expected_state_revision",
        ),
        "relationship": (
            ChangeRelationship,
            dict(source_id=env.alice, target_id=env.bob, trust_delta=1),
            "expected_relationship_revision",
        ),
    }[kind]
    with pytest.raises(TypeError, match=required):
        env.command(command, **fields)


def test_presence_expectation_cannot_be_absent(environment):
    with pytest.raises(DomainInvariantError):
        mutable_command(environment, "presence", None)
