import asyncio
from uuid import uuid4

import pytest
from livingworld.application.action_resolution import ActionResolutionService
from livingworld.application.commands import MovePlayer, PlaceCharacter
from livingworld.application.scenes import (
    CreateScene,
    EndScene,
    JoinScene,
    LeaveScene,
    SceneService,
)
from livingworld.domain.actions import (
    ActionKind,
    ActionProposal,
    ActionProposer,
    ActionResolutionStatus,
    MovePlayerPayload,
    ProposerKind,
)
from livingworld.domain.contracts import RequestId
from livingworld.domain.errors import DomainInvariantError
from livingworld.domain.identifiers import SceneId
from livingworld.domain.scenes import SceneStatus
from livingworld.domain.values import Revision, WorldTime


def test_scene_lifecycle_history_and_one_active_scene_invariant(environment):
    async def run():
        env = environment
        try:
            await env.initialize()
            for character in (env.alice, env.bob):
                await env.handler.execute(
                    env.command(
                        PlaceCharacter,
                        character_id=character,
                        location_id=env.home,
                        expected_state_revision=None,
                    )
                )
            service = SceneService(env.database.unit_of_work, env.clock)
            scene_id = SceneId(env.world, uuid4())
            created = await service.execute(
                CreateScene(
                    request_id=RequestId(uuid4()),
                    world_id=env.world,
                    scene_id=scene_id,
                    location_id=env.home,
                    initial_participants=(env.alice,),
                    started_at=WorldTime(10),
                )
            )
            assert created.resulting_revision == Revision()
            second = SceneId(env.world, uuid4())
            with pytest.raises(DomainInvariantError, match="already participates"):
                await service.execute(
                    CreateScene(
                        request_id=RequestId(uuid4()),
                        world_id=env.world,
                        scene_id=second,
                        location_id=env.home,
                        initial_participants=(env.alice,),
                        started_at=WorldTime(11),
                    )
                )
            joined = await service.execute(
                JoinScene(
                    request_id=RequestId(uuid4()),
                    world_id=env.world,
                    scene_id=scene_id,
                    principal_id=env.bob,
                    joined_at=WorldTime(12),
                    expected_scene_revision=Revision(),
                )
            )
            left_command = LeaveScene(
                request_id=RequestId(uuid4()),
                world_id=env.world,
                scene_id=scene_id,
                principal_id=env.bob,
                left_at=WorldTime(13),
                expected_scene_revision=joined.resulting_revision,
            )
            left = await service.execute(left_command)
            assert (await service.execute(left_command)).replayed
            ended = await service.execute(
                EndScene(
                    request_id=RequestId(uuid4()),
                    world_id=env.world,
                    scene_id=scene_id,
                    ended_at=WorldTime(14),
                    expected_scene_revision=left.resulting_revision,
                )
            )
            async with env.database.unit_of_work() as uow:
                scene = await uow.scenes.get(scene_id)
                assert scene.status is SceneStatus.CLOSED
                assert scene.ended_at == WorldTime(14)
                assert await uow.scenes.active_participants(scene_id) == ()
            history = [
                row
                for row in await env.rows("scene_participants")
                if row.scene_id == scene_id.value.hex
            ]
            assert len(history) == 2
            assert {row.left_at for row in history} == {13, 14}
            with pytest.raises(DomainInvariantError, match="Closed Scene"):
                await service.execute(
                    JoinScene(
                        request_id=RequestId(uuid4()),
                        world_id=env.world,
                        scene_id=scene_id,
                        principal_id=env.bob,
                        joined_at=WorldTime(15),
                        expected_scene_revision=ended.resulting_revision,
                    )
                )
        finally:
            await env.database.close()

    asyncio.run(run())


def test_scene_requires_colocation_and_movement_ends_membership(environment):
    async def run():
        env = environment
        try:
            await env.initialize()
            await env.handler.execute(
                env.command(
                    PlaceCharacter,
                    character_id=env.alice,
                    location_id=env.cafe,
                    expected_state_revision=None,
                )
            )
            service = SceneService(env.database.unit_of_work, env.clock)
            with pytest.raises(DomainInvariantError, match="not physically present"):
                await service.execute(
                    CreateScene(
                        request_id=RequestId(uuid4()),
                        world_id=env.world,
                        scene_id=SceneId(env.world, uuid4()),
                        location_id=env.home,
                        initial_participants=(env.alice,),
                        started_at=WorldTime(20),
                    )
                )
            scene_id = SceneId(env.world, uuid4())
            await service.execute(
                CreateScene(
                    request_id=RequestId(uuid4()),
                    world_id=env.world,
                    scene_id=scene_id,
                    location_id=env.home,
                    initial_participants=(env.player,),
                    started_at=WorldTime(20),
                )
            )
            await env.handler.execute(
                env.command(
                    MovePlayer,
                    player_id=env.player,
                    destination_id=env.park,
                    expected_presence_revision=Revision(),
                )
            )
            async with env.database.unit_of_work() as uow:
                assert await uow.scenes.active_for_principal(env.player) is None
                scene = await uow.scenes.get(scene_id)
                assert scene.status is SceneStatus.OPEN and scene.revision == Revision(1)
            history = [
                row
                for row in await env.rows("scene_participants")
                if row.scene_id == scene_id.value.hex
            ]
            assert len(history) == 1 and history[0].left_at == 123
        finally:
            await env.database.close()

    asyncio.run(run())


def test_character_movement_ends_membership_and_preserves_history(environment):
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
            scene_id = SceneId(env.world, uuid4())
            await SceneService(env.database.unit_of_work, env.clock).execute(
                CreateScene(
                    request_id=RequestId(uuid4()),
                    world_id=env.world,
                    scene_id=scene_id,
                    location_id=env.home,
                    initial_participants=(env.alice,),
                    started_at=WorldTime(20),
                )
            )
            await env.handler.execute(
                env.command(
                    PlaceCharacter,
                    character_id=env.alice,
                    location_id=env.cafe,
                    expected_state_revision=Revision(),
                )
            )
            async with env.database.unit_of_work() as uow:
                assert await uow.scenes.active_for_principal(env.alice) is None
                scene = await uow.scenes.get(scene_id)
                assert scene.status is SceneStatus.OPEN and scene.revision == Revision(1)
            history = [
                row
                for row in await env.rows("scene_participants")
                if row.scene_id == scene_id.value.hex
            ]
            assert len(history) == 1 and history[0].left_at == 123
        finally:
            await env.database.close()

    asyncio.run(run())


def test_concurrent_scene_creation_cannot_activate_principal_twice(environment):
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
            service = SceneService(env.database.unit_of_work, env.clock)

            def create():
                return CreateScene(
                    request_id=RequestId(uuid4()),
                    world_id=env.world,
                    scene_id=SceneId(env.world, uuid4()),
                    location_id=env.home,
                    initial_participants=(env.alice,),
                    started_at=WorldTime(30),
                )

            outcomes = await asyncio.gather(
                service.execute(create()), service.execute(create()), return_exceptions=True
            )
            assert sum(not isinstance(item, BaseException) for item in outcomes) == 1
            async with env.database.unit_of_work() as uow:
                active = await uow.scenes.active_for_principal(env.alice)
                assert active is not None
            active_rows = [
                row for row in await env.rows("scene_participants") if row.left_at is None
            ]
            assert len(active_rows) == 1
        finally:
            await env.database.close()

    asyncio.run(run())


def test_concurrent_move_and_join_settle_without_zombie_membership(environment):
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
            scene_service = SceneService(env.database.unit_of_work, env.clock)
            scene_id = SceneId(env.world, uuid4())
            await scene_service.execute(
                CreateScene(
                    request_id=RequestId(uuid4()),
                    world_id=env.world,
                    scene_id=scene_id,
                    location_id=env.home,
                    initial_participants=(env.alice,),
                    started_at=WorldTime(40),
                )
            )
            action_request = RequestId(uuid4())
            move = ActionProposal(
                env.world,
                ActionKind.MOVE_PLAYER,
                1,
                ActionProposer(ProposerKind.PLAYER_INPUT, env.player),
                env.player,
                MovePlayerPayload(env.cafe, Revision()),
            )
            join = JoinScene(
                request_id=RequestId(uuid4()),
                world_id=env.world,
                scene_id=scene_id,
                principal_id=env.player,
                joined_at=WorldTime(40),
                expected_scene_revision=Revision(),
            )
            outcomes = await asyncio.gather(
                ActionResolutionService(env.database.unit_of_work, env.clock).execute(
                    action_request, move
                ),
                scene_service.execute(join),
                return_exceptions=True,
            )
            action_result = outcomes[0]
            assert not isinstance(action_result, BaseException)
            assert action_result.status is ActionResolutionStatus.ACCEPTED
            async with env.database.unit_of_work() as uow:
                assert (await uow.players.presence(env.player)).location_id == env.cafe
                assert await uow.scenes.active_for_principal(env.player) is None
        finally:
            await env.database.close()

    asyncio.run(run())
