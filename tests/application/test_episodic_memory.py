import asyncio
import json
from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from livingworld.application.action_resolution import ActionResolutionService
from livingworld.application.command_handler import CommandHandler
from livingworld.application.commands import (
    AcquireKnowledge,
    AssertWorldTruth,
    PlaceCharacter,
)
from livingworld.application.errors import (
    IdempotencyConflictError,
    MemoryEvidenceAccessDeniedError,
)
from livingworld.application.memory import EpisodicMemoryService, RecordEpisodicMemory
from livingworld.application.replay import ProjectionRebuilder
from livingworld.domain.actions import (
    ActionKind,
    ActionProposal,
    ActionProposer,
    MovePlayerPayload,
    ProposerKind,
)
from livingworld.domain.contracts import RequestId
from livingworld.domain.errors import CrossWorldReferenceError
from livingworld.domain.identifiers import (
    KnowledgeAssertionId,
    MemoryId,
    ObservationId,
    WorldId,
)
from livingworld.domain.knowledge import ObservationChannel
from livingworld.domain.memory import MemorySalience
from livingworld.domain.values import Revision, WorldTime
from livingworld.infrastructure.persistence.memory_repository import (
    SqlAlchemyMemoryMutationRepository,
)
from livingworld.infrastructure.persistence.models import (
    EpisodicMemoryObservationSourceRecord,
)
from sqlalchemy import event, text


class MutableWorldTimeSource:
    def __init__(self, value: int):
        self.value = WorldTime(value)

    def read(self, _clock):
        return self.value


def service(environment, world_time=130):
    return EpisodicMemoryService(
        environment.database.unit_of_work,
        environment.clock,
        world_time_source=MutableWorldTimeSource(world_time),
    )


async def truth(environment, *, value="open"):
    result = await environment.handler.execute(
        environment.command(
            AssertWorldTruth,
            assertion_id=KnowledgeAssertionId(environment.world, uuid4()),
            subject="gate",
            predicate="state",
            value=value,
            valid_from=WorldTime(0),
        )
    )
    return result.entity_reference


async def observe(environment, source_id, principal_id, at):
    handler = CommandHandler(
        environment.database.unit_of_work,
        environment.clock,
        world_time_source=MutableWorldTimeSource(at),
    )
    result = await handler.execute(
        environment.command(
            AcquireKnowledge,
            assertion_id=KnowledgeAssertionId(environment.world, uuid4()),
            receiver_id=principal_id,
            source_assertion_id=source_id,
            channel=ObservationChannel.WITNESSED,
        )
    )
    return result.observation_id


def command(environment, sources, content="PRIVATE_MEMORY_CANARY", **values):
    return RecordEpisodicMemory(
        request_id=values.pop("request_id", RequestId(uuid4())),
        world_id=environment.world,
        owner_character_id=values.pop("owner", environment.alice),
        source_observation_ids=tuple(sources),
        content=content,
        **values,
    )


def test_explicit_multi_observation_memory_is_private_atomic_and_idempotent(environment, caplog):
    async def run():
        env = environment
        character_a = env.alice
        await env.initialize()
        try:
            source = await truth(env)
            first = await observe(env, source, character_a, 100)
            second = await observe(env, source, character_a, 120)
            assert await env.rows("character_memories") == []
            before = {
                table: await env.rows(table)
                for table in (
                    "world_events",
                    "observations",
                    "knowledge_assertions",
                    "simulation_activations",
                    "command_receipts",
                )
            }
            request = command(
                env,
                (second, first),
                salience=MemorySalience(73),
            )
            result = await service(env).execute(request)
            assert isinstance(result.memory_id, MemoryId)
            reader = env.database.character_memory_reader(character_a)
            memory = await reader.get(result.memory_id)
            assert memory.content == "PRIVATE_MEMORY_CANARY"
            assert memory.source_observation_ids == (second, first)
            assert memory.experienced_from == WorldTime(100)
            assert memory.experienced_to == WorldTime(120)
            assert memory.formed_at == WorldTime(130)
            assert memory.salience == MemorySalience(73)
            assert [
                (item.observation_id, item.observed_at, item.source_order)
                for item in await reader.evidence(result.memory_id)
            ] == [(second, WorldTime(120), 0), (first, WorldTime(100), 1)]

            after = {table: await env.rows(table) for table in before}
            for table in (
                "world_events",
                "observations",
                "knowledge_assertions",
                "simulation_activations",
            ):
                assert after[table] == before[table]
            assert len(after["command_receipts"]) == len(before["command_receipts"]) + 1
            receipt = next(
                row
                for row in after["command_receipts"]
                if row.request_id == request.request_id.value.hex
            )
            assert "PRIVATE_MEMORY_CANARY" not in receipt.result_payload
            assert json.loads(receipt.result_payload) == {
                "memory_id": str(result.memory_id.value),
                "result_version": 4,
            }
            assert "PRIVATE_MEMORY_CANARY" not in caplog.text

            repeated = await service(env, 999).execute(request)
            assert repeated.memory_id == result.memory_id and repeated.replayed
            assert len(await env.rows("character_memories")) == 1
            assert len(await env.rows("episodic_memory_observation_sources")) == 2
            with pytest.raises(IdempotencyConflictError):
                await service(env).execute(replace(request, content="different semantics"))

            snapshot = memory
            contradicting = await truth(env, value="closed")
            await observe(env, contradicting, character_a, 140)
            assert await reader.get(result.memory_id) == snapshot

            await ProjectionRebuilder(env.database.projection_rebuild_unit_of_work).rebuild(
                env.world
            )
            assert await reader.get(result.memory_id) == snapshot
            assert [item.observation_id for item in await reader.evidence(result.memory_id)] == [
                second,
                first,
            ]

            await env.restart()
            restarted = await service(env, 500).execute(request)
            assert restarted.memory_id == result.memory_id and restarted.replayed
            assert (
                await env.database.character_memory_reader(character_a).get(result.memory_id)
                == snapshot
            )
        finally:
            await env.database.close()

    asyncio.run(run())


def test_memory_evidence_is_sql_authorized_before_formation(environment):
    async def run():
        env = environment
        character_a, character_b = env.alice, env.bob
        await env.initialize()
        try:
            source = await truth(env)
            owned = await observe(env, source, character_a, 100)
            other_character = await observe(env, source, character_b, 101)
            player = await observe(env, source, env.player, 102)
            for evidence in ((other_character,), (player,), (owned, other_character)):
                with pytest.raises(MemoryEvidenceAccessDeniedError):
                    await service(env).execute(command(env, evidence))
            with pytest.raises(MemoryEvidenceAccessDeniedError):
                await service(env).execute(command(env, (ObservationId(env.world, uuid4()),)))
            assert await env.rows("character_memories") == []
            assert await env.rows("episodic_memory_observation_sources") == []

            other_world = WorldId(uuid4())
            with pytest.raises(CrossWorldReferenceError):
                RecordEpisodicMemory(
                    request_id=RequestId(uuid4()),
                    world_id=env.world,
                    owner_character_id=character_a,
                    source_observation_ids=(ObservationId(other_world, uuid4()),),
                    content="cross world",
                )
        finally:
            await env.database.close()

    asyncio.run(run())


def test_one_observation_supports_separate_memories_and_owner_read_isolation(environment):
    async def run():
        env = environment
        character_a, character_b = env.alice, env.bob
        await env.initialize()
        try:
            source = await truth(env)
            observation = await observe(env, source, character_a, 100)
            first = await service(env).execute(command(env, (observation,), "first recollection"))
            second = await service(env).execute(
                command(env, (observation,), "second independent recollection")
            )
            assert first.memory_id != second.memory_id
            assert len(await env.rows("character_memories")) == 2
            assert len(await env.rows("episodic_memory_observation_sources")) == 2

            for identity in (character_a, character_b):
                await env.handler.execute(
                    env.command(
                        PlaceCharacter,
                        character_id=identity,
                        location_id=env.home,
                        expected_state_revision=None,
                    )
                )
            action = ActionProposal(
                env.world,
                ActionKind.MOVE_PLAYER,
                1,
                ActionProposer(ProposerKind.PLAYER_INPUT, env.player),
                env.player,
                MovePlayerPayload(env.cafe, Revision()),
            )
            action_result = await ActionResolutionService(
                env.database.unit_of_work,
                env.clock,
                world_time_source=env.world_time_source,
            ).execute(RequestId(uuid4()), action)
            event_id = action_result.event_ids[0].value.hex
            rows = [
                row
                for row in await env.rows("observations")
                if row.target_event_id == event_id and row.principal_kind == "character"
            ]
            by_owner = {
                row.principal_id: ObservationId(env.world, UUID(hex=row.observation_id))
                for row in rows
            }
            memory_a = await service(env).execute(
                command(env, (by_owner[character_a.value.hex],), "character_a recalls movement")
            )
            memory_b = await service(env).execute(
                command(
                    env,
                    (by_owner[character_b.value.hex],),
                    "character_b recalls movement differently",
                    owner=character_b,
                )
            )
            reader_a = env.database.character_memory_reader(character_a)
            reader_b = env.database.character_memory_reader(character_b)
            assert await reader_a.get(memory_a.memory_id) is not None
            assert await reader_b.get(memory_b.memory_id) is not None
            assert await reader_a.get(memory_b.memory_id) is None
            assert await reader_b.get(memory_a.memory_id) is None
        finally:
            await env.database.close()

    asyncio.run(run())


def test_exact_concurrent_retry_and_evidence_failure_are_atomic(environment, monkeypatch):
    async def run():
        env = environment
        await env.initialize()
        try:
            source = await truth(env)
            observation = await observe(env, source, env.alice, 100)
            request = command(env, (observation,), "concurrent recollection")
            first, second = await asyncio.gather(
                service(env).execute(request),
                service(env).execute(request),
            )
            assert first.memory_id == second.memory_id
            assert {first.replayed, second.replayed} == {False, True}
            assert len(await env.rows("character_memories")) == 1
            assert len(await env.rows("episodic_memory_observation_sources")) == 1

            before_receipts = await env.rows("command_receipts")

            async def fail_during_evidence(self, memory):
                self._session.add(
                    EpisodicMemoryObservationSourceRecord(
                        world_id=memory.world_id.value,
                        memory_id=memory.memory_id.value,
                        position=0,
                        observation_id=memory.source_observation_ids[0].value,
                    )
                )
                await self._session.flush()
                raise RuntimeError("controlled_evidence_failure")

            monkeypatch.setattr(
                SqlAlchemyMemoryMutationRepository,
                "_insert_sources",
                fail_during_evidence,
            )
            with pytest.raises(RuntimeError, match="controlled_evidence_failure"):
                await service(env).execute(command(env, (observation,), "rolled back memory"))
            assert len(await env.rows("character_memories")) == 1
            assert len(await env.rows("episodic_memory_observation_sources")) == 1
            assert await env.rows("command_receipts") == before_receipts
        finally:
            await env.database.close()

    asyncio.run(run())


def test_owner_scoped_indexed_pagination_and_evidence_lookup(environment):
    async def run():
        env = environment
        await env.initialize()
        captured = []

        def capture(_conn, _cursor, statement, parameters, _context, _many):
            if statement.lstrip().upper().startswith("SELECT") and (
                "FROM character_memories" in statement or "JOIN character_memories" in statement
            ):
                captured.append((statement, parameters))

        try:
            source = await truth(env)
            observation = await observe(env, source, env.alice, 100)
            formed = []
            for at in (130, 140, 150):
                formed.append(
                    await service(env, at).execute(
                        command(env, (observation,), f"recollection formed at {at}")
                    )
                )
            reader = env.database.character_memory_reader(env.alice)
            event.listen(env.database.engine.sync_engine, "before_cursor_execute", capture)
            try:
                first_page = await reader.list(
                    experienced_from=WorldTime(90), experienced_to=WorldTime(110), limit=2
                )
                second_page = await reader.list(limit=2, after=first_page.next_cursor)
                assert [item.formed_at for item in first_page.items] == [
                    WorldTime(150),
                    WorldTime(140),
                ]
                assert [item.formed_at for item in second_page.items] == [WorldTime(130)]
                assert first_page.next_cursor is not None
                assert second_page.next_cursor is None
                await reader.get(formed[0].memory_id)
                await reader.evidence(formed[0].memory_id)
            finally:
                event.remove(env.database.engine.sync_engine, "before_cursor_execute", capture)
            assert captured
            for statement, parameters in captured:
                if "FROM character_memories" in statement:
                    where = statement.partition("WHERE")[2]
                    assert "character_memories.world_id =" in where
                    assert "character_memories.owner_character_id =" in where
                    assert env.world.value.hex in parameters
                    assert env.alice.value.hex in parameters

            async with env.database.engine.connect() as connection:
                plan = (
                    await connection.execute(
                        text(
                            "EXPLAIN QUERY PLAN SELECT memory_id FROM character_memories "
                            "WHERE world_id=:world AND owner_character_id=:owner "
                            "ORDER BY experienced_to DESC, formed_at DESC, memory_id ASC LIMIT 10"
                        ),
                        {"world": env.world.value.hex, "owner": env.alice.value.hex},
                    )
                ).all()
                indexes = {
                    row.name
                    for row in (
                        await connection.execute(
                            text(
                                "SELECT name FROM sqlite_master WHERE type='index' "
                                "AND tbl_name IN ('character_memories',"
                                "'episodic_memory_observation_sources')"
                            )
                        )
                    ).all()
                }
            assert any("ix_character_memories_owner_experienced" in row.detail for row in plan)
            assert {
                "ix_character_memories_world_owner",
                "ix_character_memories_owner_experienced",
                "ix_character_memories_owner_formed",
                "ix_episodic_memory_source_observation",
            } <= indexes
        finally:
            await env.database.close()

    asyncio.run(run())
