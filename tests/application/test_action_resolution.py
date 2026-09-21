import asyncio
import json
from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from livingworld.application.action_resolution import ActionResolutionService, AudienceResolver
from livingworld.application.commands import PlaceCharacter
from livingworld.application.errors import EntityNotFoundError, IdempotencyConflictError
from livingworld.application.replay import ProjectionRebuilder
from livingworld.application.scenes import CreateScene, JoinScene, LeaveScene, SceneService
from livingworld.domain.actions import (
    ActionKind,
    ActionProposal,
    ActionProposer,
    ActionRejectionReason,
    ActionResolutionStatus,
    AudienceSelector,
    AudienceSelectorKind,
    MovePlayerPayload,
    PerceptionAudience,
    ProposerKind,
)
from livingworld.domain.contracts import RequestId
from livingworld.domain.errors import ConcurrencyConflictError
from livingworld.domain.identifiers import ObservationId, PlayerId, SceneId, WorldId
from livingworld.domain.knowledge import Observation, ObservationBasis, ObservationChannel
from livingworld.domain.values import Revision, WorldTime
from livingworld.infrastructure.persistence.errors import PersistenceConflictError
from livingworld.infrastructure.persistence.unit_of_work import (
    ObservationAppender,
    SqlAlchemyUnitOfWork,
)


def proposal(env, *, request_id=None, destination=None, proposer=None, revision=None):
    request_id = request_id or RequestId(uuid4())
    return request_id, ActionProposal(
        env.world,
        ActionKind.MOVE_PLAYER,
        1,
        proposer or ActionProposer(ProposerKind.PLAYER_INPUT, env.player),
        env.player,
        MovePlayerPayload(destination or env.cafe, revision or Revision()),
    )


def test_authority_rejection_idempotency_and_semantic_conflict(environment):
    async def run():
        env = environment
        try:
            await env.initialize()
            service = ActionResolutionService(
                env.database.unit_of_work, env.clock, world_time_source=env.world_time_source
            )
            request_id, action = proposal(
                env,
                proposer=ActionProposer(ProposerKind.SYSTEM),
            )
            before_events = len(await env.rows("world_events"))
            result = await service.execute(request_id, action)
            assert result.status is ActionResolutionStatus.REJECTED
            assert result.reason is ActionRejectionReason.UNAUTHORIZED_ACTOR
            assert result.event_ids == ()
            assert len(await env.rows("world_events")) == before_events
            assert await env.rows("observations") == []
            assert (await env.rows("player_presences"))[0].location_id == env.home.value.hex
            assert await service.execute(request_id, action) == replace(result, replayed=True)
            with pytest.raises(IdempotencyConflictError):
                await service.execute(
                    request_id,
                    replace(action, payload=MovePlayerPayload(env.park, Revision())),
                )
        finally:
            await env.database.close()

    asyncio.run(run())


def test_unknown_action_version_is_typed_rejection(environment):
    async def run():
        env = environment
        try:
            await env.initialize()
            service = ActionResolutionService(
                env.database.unit_of_work, env.clock, world_time_source=env.world_time_source
            )
            request_id, action = proposal(env)
            result = await service.execute(request_id, replace(action, schema_version=99))
            assert result.status is ActionResolutionStatus.REJECTED
            assert result.reason is ActionRejectionReason.UNSUPPORTED_ACTION
            assert result.event_ids == ()
            assert await env.rows("observations") == []
        finally:
            await env.database.close()

    asyncio.run(run())


def test_world_event_with_zero_observers_remains_canonical(environment):
    async def run():
        env = environment
        try:
            await env.initialize()
            events = await env.rows("world_events")
            assert events
            assert await env.rows("observations") == []
        finally:
            await env.database.close()

    asyncio.run(run())


@pytest.mark.parametrize("proposer_kind", [ProposerKind.CHARACTER_RUNTIME, ProposerKind.DIRECTOR])
def test_character_runtime_and_director_cannot_act_as_player(environment, proposer_kind):
    async def run():
        env = environment
        try:
            await env.initialize()
            proposer = (
                ActionProposer(proposer_kind, env.alice)
                if proposer_kind is ProposerKind.CHARACTER_RUNTIME
                else ActionProposer(proposer_kind)
            )
            request_id, action = proposal(env, proposer=proposer)
            result = await ActionResolutionService(
                env.database.unit_of_work, env.clock, world_time_source=env.world_time_source
            ).execute(request_id, action)
            assert result.status is ActionResolutionStatus.REJECTED
            assert result.reason is ActionRejectionReason.UNAUTHORIZED_ACTOR
        finally:
            await env.database.close()

    asyncio.run(run())


def test_character_runtime_cannot_impersonate_another_character(environment):
    async def run():
        env = environment
        try:
            await env.initialize()
            request_id, action = proposal(
                env, proposer=ActionProposer(ProposerKind.CHARACTER_RUNTIME, env.alice)
            )
            action = replace(action, actor_id=env.bob)
            result = await ActionResolutionService(
                env.database.unit_of_work, env.clock, world_time_source=env.world_time_source
            ).execute(request_id, action)
            assert result.status is ActionResolutionStatus.REJECTED
            assert result.reason is ActionRejectionReason.UNAUTHORIZED_ACTOR
        finally:
            await env.database.close()

    asyncio.run(run())


def test_accepted_move_commits_event_perception_presence_and_receipt_atomically(environment):
    async def run():
        env = environment
        try:
            await env.initialize()
            await env.handler.execute(
                env.command(
                    PlaceCharacter,
                    character_id=env.alice,
                    location_id=env.home,
                    expected_state_revision=None,
                )
            )
            await env.handler.execute(
                env.command(
                    PlaceCharacter,
                    character_id=env.bob,
                    location_id=env.cafe,
                    expected_state_revision=None,
                )
            )
            service = ActionResolutionService(
                env.database.unit_of_work, env.clock, world_time_source=env.world_time_source
            )
            request_id, action = proposal(env)
            before_knowledge = len(await env.rows("knowledge_assertions"))
            result = await service.execute(request_id, action)
            assert result.status is ActionResolutionStatus.ACCEPTED
            assert result.resulting_revision == Revision(1)
            events = [
                row
                for row in await env.rows("world_events")
                if row.causation_request_id == request_id.value.hex
            ]
            assert len(events) == 1 and events[0].event_type == "PlayerMoved"
            observations = [
                row
                for row in await env.rows("observations")
                if row.target_event_id == events[0].event_id
            ]
            assert {(row.principal_kind, row.principal_id) for row in observations} == {
                ("player", env.player.value.hex),
                ("character", env.alice.value.hex),
                ("character", env.bob.value.hex),
            }
            assert all(
                row.channel == "witnessed"
                and row.basis == "event_occurrence"
                and row.observed_at == 123
                for row in observations
            )
            assert len(await env.rows("knowledge_assertions")) == before_knowledge
            async with env.database.unit_of_work() as uow:
                assert (await uow.players.presence(env.player)).location_id == env.cafe
            snapshot = (
                await env.rows("world_events"),
                await env.rows("observations"),
                await env.rows("player_presences"),
            )
            assert await service.execute(request_id, action) == replace(result, replayed=True)
            assert snapshot == (
                await env.rows("world_events"),
                await env.rows("observations"),
                await env.rows("player_presences"),
            )
            with pytest.raises(PersistenceConflictError):
                async with env.database.unit_of_work() as uow:
                    await uow.observations.add(
                        Observation(
                            env.world,
                            env.player,
                            result.event_ids[0],
                            ObservationChannel.WITNESSED,
                            WorldTime(123),
                            env.clock.value,
                            observation_id=ObservationId(env.world, uuid4()),
                            basis=ObservationBasis.EVENT_OCCURRENCE,
                        )
                    )
                    await uow.commit()
        finally:
            await env.database.close()

    asyncio.run(run())


def test_perception_insert_failure_rolls_back_entire_action(environment, monkeypatch):
    async def run():
        env = environment
        try:
            await env.initialize()
            service = ActionResolutionService(
                env.database.unit_of_work, env.clock, world_time_source=env.world_time_source
            )
            request_id, action = proposal(env)
            before = {
                table: await env.rows(table)
                for table in (
                    "player_presences",
                    "world_events",
                    "observations",
                    "command_receipts",
                )
            }

            async def fail(_self, _observation):
                raise RuntimeError("controlled_perception_failure")

            monkeypatch.setattr(ObservationAppender, "add", fail)
            with pytest.raises(RuntimeError, match="controlled_perception_failure"):
                await service.execute(request_id, action)
            for table, rows in before.items():
                assert await env.rows(table) == rows
        finally:
            await env.database.close()

    asyncio.run(run())


def test_commit_failure_after_resolution_rolls_back_all_action_state(environment, monkeypatch):
    async def run():
        env = environment
        try:
            await env.initialize()
            service = ActionResolutionService(
                env.database.unit_of_work, env.clock, world_time_source=env.world_time_source
            )
            request_id, action = proposal(env)
            before = {
                table: await env.rows(table)
                for table in (
                    "player_presences",
                    "world_events",
                    "observations",
                    "command_receipts",
                )
            }

            async def fail_commit(_self):
                raise RuntimeError("controlled_precommit_failure")

            monkeypatch.setattr(SqlAlchemyUnitOfWork, "commit", fail_commit)
            with pytest.raises(RuntimeError, match="controlled_precommit_failure"):
                await service.execute(request_id, action)
            for table, rows in before.items():
                assert await env.rows(table) == rows
        finally:
            await env.database.close()

    asyncio.run(run())


def test_event_perception_is_historical_and_projection_replay_does_not_recompute(environment):
    async def run():
        env = environment
        try:
            await env.initialize()
            await env.handler.execute(
                env.command(
                    PlaceCharacter,
                    character_id=env.alice,
                    location_id=env.home,
                    expected_state_revision=None,
                )
            )
            service = ActionResolutionService(
                env.database.unit_of_work, env.clock, world_time_source=env.world_time_source
            )
            request_id, action = proposal(env)
            result = await service.execute(request_id, action)
            event_id = result.event_ids[0]
            before = [
                row
                for row in await env.rows("observations")
                if row.target_event_id == event_id.value.hex
            ]
            await env.handler.execute(
                env.command(
                    PlaceCharacter,
                    character_id=env.alice,
                    location_id=env.park,
                    expected_state_revision=Revision(),
                )
            )
            await ProjectionRebuilder(env.database.projection_rebuild_unit_of_work).rebuild(
                env.world
            )
            after = [
                row
                for row in await env.rows("observations")
                if row.target_event_id == event_id.value.hex
            ]
            assert after == before
            assert any(row.principal_id == env.alice.value.hex for row in after)
        finally:
            await env.database.close()

    asyncio.run(run())


def test_principal_joining_scene_after_event_does_not_gain_historical_perception(environment):
    async def run():
        env = environment
        try:
            await env.initialize()
            service = ActionResolutionService(
                env.database.unit_of_work, env.clock, world_time_source=env.world_time_source
            )
            request_id, action = proposal(env)
            event_id = (await service.execute(request_id, action)).event_ids[0]
            await env.handler.execute(
                env.command(
                    PlaceCharacter,
                    character_id=env.alice,
                    location_id=env.cafe,
                    expected_state_revision=None,
                )
            )
            await SceneService(env.database.unit_of_work, env.clock).execute(
                CreateScene(
                    request_id=RequestId(uuid4()),
                    world_id=env.world,
                    scene_id=SceneId(env.world, uuid4()),
                    location_id=env.cafe,
                    initial_participants=(env.alice,),
                    started_at=WorldTime(124),
                )
            )
            before = [
                row
                for row in await env.rows("observations")
                if row.target_event_id == event_id.value.hex
            ]
            assert all(row.principal_id != env.alice.value.hex for row in before)
            await ProjectionRebuilder(env.database.projection_rebuild_unit_of_work).rebuild(
                env.world
            )
            after = [
                row
                for row in await env.rows("observations")
                if row.target_event_id == event_id.value.hex
            ]
            assert after == before
        finally:
            await env.database.close()

    asyncio.run(run())


def test_audience_selectors_union_dedup_and_world_isolation(environment):
    async def run():
        env = environment
        try:
            await env.initialize()
            await env.handler.execute(
                env.command(
                    PlaceCharacter,
                    character_id=env.alice,
                    location_id=env.home,
                    expected_state_revision=None,
                )
            )
            await env.handler.execute(
                env.command(
                    PlaceCharacter,
                    character_id=env.bob,
                    location_id=env.home,
                    expected_state_revision=None,
                )
            )
            scene_id = SceneId(env.world, uuid4())
            scene_service = SceneService(env.database.unit_of_work, env.clock)
            await scene_service.execute(
                CreateScene(
                    request_id=RequestId(uuid4()),
                    world_id=env.world,
                    scene_id=scene_id,
                    location_id=env.home,
                    initial_participants=(env.alice,),
                    started_at=WorldTime(123),
                )
            )
            audience = PerceptionAudience(
                (
                    AudienceSelector(AudienceSelectorKind.ACTOR_ONLY),
                    AudienceSelector(AudienceSelectorKind.SCENE_PARTICIPANTS, scene_id=scene_id),
                    AudienceSelector(AudienceSelectorKind.LOCATION_PRESENT, location_id=env.home),
                    AudienceSelector(
                        AudienceSelectorKind.EXPLICIT_PRINCIPALS,
                        principals=(env.alice, env.player),
                    ),
                )
            )
            async with env.database.unit_of_work() as uow:
                assert (
                    await AudienceResolver().resolve(
                        uow,
                        PerceptionAudience((AudienceSelector(AudienceSelectorKind.NONE),)),
                        actor_id=None,
                        world_id=env.world,
                    )
                    == ()
                )
                assert await AudienceResolver().resolve(
                    uow,
                    PerceptionAudience((AudienceSelector(AudienceSelectorKind.ACTOR_ONLY),)),
                    actor_id=env.player,
                    world_id=env.world,
                ) == (env.player,)
                assert await AudienceResolver().resolve(
                    uow,
                    PerceptionAudience(
                        (
                            AudienceSelector(
                                AudienceSelectorKind.SCENE_PARTICIPANTS, scene_id=scene_id
                            ),
                        )
                    ),
                    actor_id=None,
                    world_id=env.world,
                ) == (env.alice,)
                assert set(
                    await AudienceResolver().resolve(
                        uow,
                        PerceptionAudience(
                            (
                                AudienceSelector(
                                    AudienceSelectorKind.LOCATION_PRESENT,
                                    location_id=env.home,
                                ),
                            )
                        ),
                        actor_id=None,
                        world_id=env.world,
                    )
                ) == {env.alice, env.bob}
                resolved = await AudienceResolver().resolve(
                    uow, audience, actor_id=env.player, world_id=env.world
                )
                assert set(resolved) == {env.player, env.alice, env.bob}
            left = await scene_service.execute(
                LeaveScene(
                    request_id=RequestId(uuid4()),
                    world_id=env.world,
                    scene_id=scene_id,
                    principal_id=env.alice,
                    left_at=WorldTime(124),
                    expected_scene_revision=Revision(),
                )
            )
            async with env.database.unit_of_work() as uow:
                assert (
                    await AudienceResolver().resolve(
                        uow,
                        PerceptionAudience(
                            (
                                AudienceSelector(
                                    AudienceSelectorKind.SCENE_PARTICIPANTS, scene_id=scene_id
                                ),
                            )
                        ),
                        actor_id=None,
                        world_id=env.world,
                    )
                    == ()
                )
            await scene_service.execute(
                JoinScene(
                    request_id=RequestId(uuid4()),
                    world_id=env.world,
                    scene_id=scene_id,
                    principal_id=env.bob,
                    joined_at=WorldTime(125),
                    expected_scene_revision=left.resulting_revision,
                )
            )
            async with env.database.unit_of_work() as uow:
                assert await AudienceResolver().resolve(
                    uow,
                    PerceptionAudience(
                        (
                            AudienceSelector(
                                AudienceSelectorKind.SCENE_PARTICIPANTS, scene_id=scene_id
                            ),
                        )
                    ),
                    actor_id=None,
                    world_id=env.world,
                ) == (env.bob,)
            other = WorldId(uuid4())
            invalid = PerceptionAudience(
                (
                    AudienceSelector(
                        AudienceSelectorKind.EXPLICIT_PRINCIPALS,
                        principals=(PlayerId(other, uuid4()),),
                    ),
                )
            )
            async with env.database.unit_of_work() as uow:
                with pytest.raises(EntityNotFoundError, match="another World"):
                    await AudienceResolver().resolve(
                        uow, invalid, actor_id=None, world_id=env.world
                    )
        finally:
            await env.database.close()

    asyncio.run(run())


def test_conflicting_actions_have_one_acceptance_and_unique_ledger_positions(environment):
    async def run():
        env = environment
        try:
            await env.initialize()
            service = ActionResolutionService(
                env.database.unit_of_work, env.clock, world_time_source=env.world_time_source
            )
            left = proposal(env, destination=env.cafe)
            right = proposal(env, destination=env.park)
            results = await asyncio.gather(
                service.execute(*left), service.execute(*right), return_exceptions=True
            )
            accepted = [
                item
                for item in results
                if not isinstance(item, BaseException)
                and item.status is ActionResolutionStatus.ACCEPTED
            ]
            rejected = [
                item
                for item in results
                if not isinstance(item, BaseException)
                and item.status is ActionResolutionStatus.REJECTED
            ]
            conflicts = [item for item in results if isinstance(item, ConcurrencyConflictError)]
            assert len(accepted) == 1
            assert len(rejected) + len(conflicts) == 1
            positions = [row.ledger_position for row in await env.rows("world_events")]
            assert len(positions) == len(set(positions))
            observations = await env.rows("observations")
            assert len(
                {
                    (row.target_event_id, row.principal_kind, row.principal_id)
                    for row in observations
                }
            ) == len(observations)
        finally:
            await env.database.close()

    asyncio.run(run())


def test_rejected_payload_canary_is_not_persisted_or_logged(environment, caplog):
    async def run():
        env = environment
        try:
            await env.initialize()
            service = ActionResolutionService(
                env.database.unit_of_work, env.clock, world_time_source=env.world_time_source
            )
            private_destination = type(env.home)(
                env.world, UUID("decafbad-dec0-afba-ddec-afbaddecafba")
            )
            request_id, action = proposal(
                env,
                destination=private_destination,
                proposer=ActionProposer(ProposerKind.DIRECTOR),
            )
            await service.execute(request_id, action)
            canary = private_destination.value.hex
            dump = json.dumps(
                [tuple(str(value) for value in row) for row in await env.rows("command_receipts")]
            )
            assert canary not in dump
            assert all(canary not in str(row) for row in await env.rows("world_events"))
            assert canary not in caplog.text
        finally:
            await env.database.close()

    asyncio.run(run())
