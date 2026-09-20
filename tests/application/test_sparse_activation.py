import asyncio
from uuid import uuid4

import pytest
from livingworld.application.action_resolution import ActionResolutionService
from livingworld.application.activation import ActivationPlanner, SparseActivationService
from livingworld.application.commands import PlaceCharacter
from livingworld.application.errors import (
    ActivationAccessDeniedError,
    ActivationFanoutTooLargeError,
    IdempotencyConflictError,
)
from livingworld.application.scenes import CreateScene, JoinScene, LeaveScene, SceneService
from livingworld.application.scheduler import (
    SchedulerWakeSignal,
    ScheduleTrigger,
    SimulationScheduler,
    TriggerKindRegistry,
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
from livingworld.domain.identifiers import CharacterId, PlayerId, SceneId, TriggerId, WorldId
from livingworld.domain.simulation import (
    ActivationAttention,
    ActivationCause,
    ActivationCauseKind,
    ActivationKind,
    ActivationRequest,
    ActivationTarget,
    ActivationTargetKind,
    EventWakeKind,
    EventWakeSpec,
    SceneActivityKind,
    SimulationFidelity,
    SimulationPayload,
    TriggerPriority,
)
from livingworld.domain.values import Revision, WorldTime
from livingworld.infrastructure.persistence.activation import SqlAlchemyActivationRepository
from sqlalchemy import text


def _service(env, *, planner=None):
    return SparseActivationService(
        env.database.unit_of_work,
        env.clock,
        SchedulerWakeSignal(),
        planner,
    )


def _explicit_request(
    character_id,
    *,
    request_id=None,
    due=100,
    priority=TriggerPriority.NORMAL,
    kind=ActivationKind.CHARACTER_REACTION,
    coalescing_key="reaction",
    attention=ActivationAttention.NONE,
):
    return ActivationRequest(
        world_id=character_id.world_id,
        target=ActivationTarget.character(character_id),
        activation_kind=kind,
        activation_version=1,
        cause=ActivationCause(
            character_id.world_id,
            ActivationCauseKind.EXPLICIT_SYSTEM,
            source_request_id=request_id or RequestId(uuid4()),
        ),
        due_at=WorldTime(due),
        priority=priority,
        coalescing_key=coalescing_key,
        attention=attention,
    )


def _move_proposal(env, *, scene_id=None):
    return ActionProposal(
        env.world,
        ActionKind.MOVE_PLAYER,
        1,
        ActionProposer(ProposerKind.PLAYER_INPUT, env.player),
        env.player,
        MovePlayerPayload(env.cafe, Revision()),
        scene_id=scene_id,
    )


async def _place(env, character, location=None):
    return await env.handler.execute(
        env.command(
            PlaceCharacter,
            character_id=character,
            location_id=location or env.home,
            expected_state_revision=None,
        )
    )


def test_typed_targets_causes_and_wake_specs_reject_invalid_shapes():
    world = WorldId(uuid4())
    other = WorldId(uuid4())
    character = CharacterId(world, uuid4())

    assert ActivationTarget.world(world).kind is ActivationTargetKind.WORLD
    assert ActivationTarget.character(character).character_id == character
    with pytest.raises(DomainInvariantError):
        ActivationTarget(world, ActivationTargetKind.CHARACTER, PlayerId(world, uuid4()))
    with pytest.raises(DomainInvariantError, match="another world"):
        ActivationRequest(
            world_id=world,
            target=ActivationTarget.character(character),
            activation_kind=ActivationKind.CHARACTER_REACTION,
            activation_version=1,
            cause=ActivationCause(
                other,
                ActivationCauseKind.EXPLICIT_SYSTEM,
                source_request_id=RequestId(uuid4()),
            ),
            due_at=WorldTime(0),
        )
    with pytest.raises(DomainInvariantError):
        EventWakeSpec(
            EventWakeKind.EXPLICIT_CHARACTERS,
            characters=(character, character),
        )
    with pytest.raises(DomainInvariantError, match="Character targets"):
        ActivationRequest(
            world_id=world,
            target=ActivationTarget.world(world),
            activation_kind=ActivationKind.WORLD_ORCHESTRATION,
            activation_version=1,
            cause=ActivationCause(
                world,
                ActivationCauseKind.EXPLICIT_SYSTEM,
                source_request_id=RequestId(uuid4()),
            ),
            due_at=WorldTime(0),
            attention=ActivationAttention.ACTIVE,
        )
    with pytest.raises(DomainInvariantError, match="payload must be empty"):
        ActivationRequest(
            world_id=world,
            target=ActivationTarget.character(character),
            activation_kind=ActivationKind.CHARACTER_REACTION,
            activation_version=1,
            cause=ActivationCause(
                world,
                ActivationCauseKind.EXPLICIT_SYSTEM,
                source_request_id=RequestId(uuid4()),
            ),
            due_at=WorldTime(0),
            payload=SimulationPayload(
                {"prompt": "PROMPT_CANARY", "private_memory": "MEMORY_CANARY"}
            ),
        )


def test_coalescing_preserves_one_hundred_causes_and_bounded_pages(environment):
    async def run():
        env = environment
        try:
            await env.initialize()
            await _place(env, env.alice)
            service = _service(env)
            identities = [RequestId(uuid4()) for _ in range(100)]
            first = await service.request(
                _explicit_request(
                    env.alice,
                    request_id=identities[0],
                    due=200,
                    priority=TriggerPriority.LOW,
                )
            )
            for index, identity in enumerate(identities[1:], 1):
                await service.request(
                    _explicit_request(
                        env.alice,
                        request_id=identity,
                        due=50 if index == 1 else 200,
                        priority=(TriggerPriority.HIGH if index == 2 else TriggerPriority.NORMAL),
                    )
                )

            activations = await env.rows("simulation_activations")
            assert len(activations) == 1
            assert activations[0].due_at == 50
            assert activations[0].priority == TriggerPriority.HIGH
            causes = await env.rows("simulation_activation_causes")
            assert len(causes) == 100
            assert len({row.cause_identity for row in causes}) == 100
            page = await service.causes(first.activation.activation_id, 20)
            assert len(page.causes) == 20 and page.more_causes
            assert [cause.position for cause in page.causes] == list(range(1, 21))
            tail = await service.causes(first.activation.activation_id, 20, 80)
            assert len(tail.causes) == 20 and not tail.more_causes

            replay = await service.request(
                _explicit_request(
                    env.alice,
                    request_id=identities[0],
                    due=200,
                    priority=TriggerPriority.LOW,
                )
            )
            assert (
                replay.replayed
                and replay.activation.activation_id == first.activation.activation_id
            )
            with pytest.raises(IdempotencyConflictError):
                await service.request(
                    _explicit_request(env.alice, request_id=identities[0], due=201)
                )
        finally:
            await env.database.close()

    asyncio.run(run())


def test_concurrent_compatible_requests_form_one_pending_activation(environment):
    async def run():
        env = environment
        try:
            await env.initialize()
            await _place(env, env.alice)
            service = _service(env)
            requests = [_explicit_request(env.alice) for _ in range(12)]
            results = await asyncio.gather(*(service.request(item) for item in requests))
            assert len({result.activation.activation_id for result in results}) == 1
            assert len(await env.rows("simulation_activations")) == 1
            assert len(await env.rows("simulation_activation_causes")) == 12
        finally:
            await env.database.close()

    asyncio.run(run())


def test_noncoalescible_activation_kinds_remain_separate(environment):
    async def run():
        env = environment
        try:
            await env.initialize()
            await _place(env, env.alice)
            service = _service(env)
            await service.request(_explicit_request(env.alice))
            await service.request(
                _explicit_request(
                    env.alice,
                    kind=ActivationKind.CHARACTER_SCHEDULE_DUE,
                    coalescing_key="schedule_due",
                )
            )
            rows = await env.rows("simulation_activations")
            assert {row.activation_kind for row in rows} == {
                "character_reaction",
                "character_schedule_due",
            }
        finally:
            await env.database.close()

    asyncio.run(run())


def test_scheduled_character_trigger_uses_generalized_atomic_activation_path(environment):
    async def run():
        env = environment
        try:
            await env.initialize()
            registry = TriggerKindRegistry({("test.character_due", 1): lambda _payload: None})
            wake = SchedulerWakeSignal()
            store = env.database.simulation_scheduler_store(registry)
            scheduler = SimulationScheduler(store, env.clock, wake)
            trigger_id = TriggerId(env.world, uuid4())
            scheduled = ScheduleTrigger(
                request_id=RequestId(uuid4()),
                trigger_id=trigger_id,
                world_id=env.world,
                due_at=WorldTime(50),
                kind="test.character_due",
                payload_version=1,
                payload=SimulationPayload({"safe": "reference-only"}),
                activation_target=ActivationTarget.character(env.alice),
                activation_kind=ActivationKind.CHARACTER_SCHEDULE_DUE,
                activation_coalescing_key="character_schedule_due",
                activation_attention=ActivationAttention.ACTIVE,
            )
            await scheduler.schedule_trigger(scheduled)
            drained = await scheduler.drain_due(env.world, WorldTime(50), 10)
            assert drained.processed_count == 1
            activation = drained.activations[0]
            assert activation.target.character_id == env.alice
            assert activation.activation_kind is ActivationKind.CHARACTER_SCHEDULE_DUE
            assert activation.source_trigger_id == trigger_id
            page = await _service(env).causes(activation.activation_id, 10)
            assert len(page.causes) == 1
            assert page.causes[0].cause.source_trigger_id == trigger_id
            assert (await scheduler.drain_due(env.world, WorldTime(50), 10)).processed_count == 0
            assert len(await env.rows("simulation_activations")) == 1
            assert len(await env.rows("simulation_activation_causes")) == 1
        finally:
            await env.database.close()

    asyncio.run(run())


def test_event_activation_requires_observation_and_does_not_grant_knowledge(environment):
    async def run():
        env = environment
        try:
            await env.initialize()
            await _place(env, env.alice)
            action = ActionResolutionService(env.database.unit_of_work, env.clock)
            event_id = (await action.execute(RequestId(uuid4()), _move_proposal(env))).event_ids[0]
            before_observations = await env.rows("observations")
            before_knowledge = await env.rows("knowledge_assertions")
            service = _service(env)

            def event_request(target):
                return ActivationRequest(
                    world_id=env.world,
                    target=ActivationTarget.character(target),
                    activation_kind=ActivationKind.CHARACTER_REACTION,
                    activation_version=1,
                    cause=ActivationCause(
                        env.world,
                        ActivationCauseKind.WORLD_EVENT,
                        source_event_id=event_id,
                    ),
                    due_at=WorldTime(123),
                    coalescing_key="event_reaction",
                    attention=ActivationAttention.ACTIVE,
                )

            accepted = await service.request(event_request(env.alice))
            assert accepted.activation.target.character_id == env.alice
            with pytest.raises(ActivationAccessDeniedError):
                await service.request(event_request(env.bob))
            assert await env.rows("observations") == before_observations
            assert await env.rows("knowledge_assertions") == before_knowledge
        finally:
            await env.database.close()

    asyncio.run(run())


def test_current_fidelity_tracks_scene_and_player_state_without_changing_priority(environment):
    async def run():
        env = environment
        try:
            await env.initialize()
            service = _service(env)
            dormant = await service.request(
                _explicit_request(env.alice, due=100, attention=ActivationAttention.ACTIVE)
            )
            candidates = await service.select_due(env.world, WorldTime(100), 10)
            assert candidates[0].activation.activation_id == dormant.activation.activation_id
            assert candidates[0].fidelity is SimulationFidelity.DORMANT

            await _place(env, env.alice)
            await _place(env, env.bob)
            background = await service.request(
                _explicit_request(
                    env.bob,
                    due=100,
                    priority=TriggerPriority.HIGH,
                    coalescing_key="background",
                )
            )
            selected = await service.select_due(env.world, WorldTime(100), 10)
            by_id = {item.activation.activation_id: item for item in selected}
            assert by_id[dormant.activation.activation_id].fidelity is SimulationFidelity.ACTIVE
            assert (
                by_id[background.activation.activation_id].fidelity is SimulationFidelity.BACKGROUND
            )
            assert selected[0].activation.activation_id == background.activation.activation_id

            scene_id = SceneId(env.world, uuid4())
            scenes = SceneService(env.database.unit_of_work, env.clock)
            await scenes.execute(
                CreateScene(
                    request_id=RequestId(uuid4()),
                    world_id=env.world,
                    scene_id=scene_id,
                    location_id=env.home,
                    initial_participants=(env.alice,),
                    started_at=WorldTime(123),
                )
            )
            selected = await service.select_due(env.world, WorldTime(100), 10)
            by_id = {item.activation.activation_id: item for item in selected}
            assert (
                by_id[dormant.activation.activation_id].fidelity is SimulationFidelity.SCENE_ACTIVE
            )
            assert (
                by_id[background.activation.activation_id].fidelity is SimulationFidelity.BACKGROUND
            )

            joined = await scenes.execute(
                JoinScene(
                    request_id=RequestId(uuid4()),
                    world_id=env.world,
                    scene_id=scene_id,
                    principal_id=env.player,
                    joined_at=WorldTime(124),
                    expected_scene_revision=Revision(),
                )
            )
            selected = await service.select_due(env.world, WorldTime(100), 10)
            by_id = {item.activation.activation_id: item for item in selected}
            assert (
                by_id[dormant.activation.activation_id].fidelity is SimulationFidelity.PLAYER_FACING
            )
            assert (
                by_id[background.activation.activation_id].fidelity is SimulationFidelity.BACKGROUND
            )

            await scenes.execute(
                LeaveScene(
                    request_id=RequestId(uuid4()),
                    world_id=env.world,
                    scene_id=scene_id,
                    principal_id=env.player,
                    left_at=WorldTime(125),
                    expected_scene_revision=joined.resulting_revision,
                )
            )
            selected = await service.select_due(env.world, WorldTime(100), 10)
            by_id = {item.activation.activation_id: item for item in selected}
            assert (
                by_id[dormant.activation.activation_id].fidelity is SimulationFidelity.SCENE_ACTIVE
            )
        finally:
            await env.database.close()

    asyncio.run(run())


def test_scene_wake_excludes_player_history_and_location_only_characters(environment):
    async def run():
        env = environment
        try:
            await env.initialize()
            await _place(env, env.alice)
            await _place(env, env.bob)
            scenes = SceneService(env.database.unit_of_work, env.clock)
            scene_id = SceneId(env.world, uuid4())
            created = await scenes.execute(
                CreateScene(
                    request_id=RequestId(uuid4()),
                    world_id=env.world,
                    scene_id=scene_id,
                    location_id=env.home,
                    initial_participants=(env.player, env.alice, env.bob),
                    started_at=WorldTime(123),
                )
            )
            await scenes.execute(
                LeaveScene(
                    request_id=RequestId(uuid4()),
                    world_id=env.world,
                    scene_id=scene_id,
                    principal_id=env.bob,
                    left_at=WorldTime(124),
                    expected_scene_revision=created.resulting_revision,
                )
            )
            results = await _service(env).request_scene_activity(
                scene_id,
                SceneActivityKind.PARTICIPANT_LEFT,
                RequestId(uuid4()),
                WorldTime(124),
            )
            assert [item.activation.target.character_id for item in results] == [env.alice]
            rows = await env.rows("simulation_activations")
            assert {row.target_id for row in rows} == {env.alice.value.hex}
        finally:
            await env.database.close()

    asyncio.run(run())


def test_scene_fanout_bound_fails_before_any_activation_write(environment):
    async def run():
        env = environment
        try:
            await env.initialize()
            await _place(env, env.alice)
            await _place(env, env.bob)
            scene_id = SceneId(env.world, uuid4())
            await SceneService(env.database.unit_of_work, env.clock).execute(
                CreateScene(
                    request_id=RequestId(uuid4()),
                    world_id=env.world,
                    scene_id=scene_id,
                    location_id=env.home,
                    initial_participants=(env.alice, env.bob),
                    started_at=WorldTime(123),
                )
            )
            service = _service(env, planner=ActivationPlanner(max_character_fanout=1))
            with pytest.raises(ActivationFanoutTooLargeError):
                await service.request_scene_activity(
                    scene_id,
                    SceneActivityKind.ACTION,
                    RequestId(uuid4()),
                    WorldTime(123),
                )
            assert await env.rows("simulation_activations") == []
            assert await env.rows("simulation_activation_causes") == []
        finally:
            await env.database.close()

    asyncio.run(run())


def test_action_event_observation_activation_and_receipt_commit_atomically(
    environment, monkeypatch
):
    async def setup(env):
        await _place(env, env.alice)
        await _place(env, env.bob)
        scene_id = SceneId(env.world, uuid4())
        await SceneService(env.database.unit_of_work, env.clock).execute(
            CreateScene(
                request_id=RequestId(uuid4()),
                world_id=env.world,
                scene_id=scene_id,
                location_id=env.home,
                initial_participants=(env.player, env.alice, env.bob),
                started_at=WorldTime(123),
            )
        )
        return scene_id

    async def run_success():
        env = environment
        try:
            await env.initialize()
            scene_id = await setup(env)
            result = await ActionResolutionService(env.database.unit_of_work, env.clock).execute(
                RequestId(uuid4()), _move_proposal(env, scene_id=scene_id)
            )
            assert result.status is ActionResolutionStatus.ACCEPTED
            activations = await env.rows("simulation_activations")
            causes = await env.rows("simulation_activation_causes")
            assert len(activations) == len(causes) == 2
            assert {row.target_id for row in activations} == {
                env.alice.value.hex,
                env.bob.value.hex,
            }
            assert {row.source_event_id for row in causes} == {result.event_ids[0].value.hex}
        finally:
            await env.database.close()

    asyncio.run(run_success())

    async def run_failure():
        # A fresh fixture path is unavailable inside one test, so restore the committed
        # player position before constructing the controlled rollback case.
        env = environment
        env.path = env.path.parent / "activation-failure"
        env.database = type(env.database)(env.path)
        env.handler = type(env.handler)(env.database.unit_of_work, env.clock)
        try:
            await env.initialize()
            scene_id = await setup(env)
            before = {
                table: await env.rows(table)
                for table in (
                    "player_presences",
                    "world_events",
                    "observations",
                    "simulation_activations",
                    "simulation_activation_causes",
                    "command_receipts",
                )
            }

            async def fail(*_args, **_kwargs):
                raise RuntimeError("controlled_activation_failure")

            monkeypatch.setattr(SqlAlchemyActivationRepository, "request", fail)
            with pytest.raises(RuntimeError, match="controlled_activation_failure"):
                await ActionResolutionService(env.database.unit_of_work, env.clock).execute(
                    RequestId(uuid4()), _move_proposal(env, scene_id=scene_id)
                )
            for table, rows in before.items():
                assert await env.rows(table) == rows
        finally:
            await env.database.close()

    asyncio.run(run_failure())


def test_large_perception_history_can_aggregate_to_one_world_activation(environment):
    async def run():
        env = environment
        try:
            await env.initialize()
            rows = []
            states = []
            for index in range(256):
                identity = uuid4()
                rows.append(
                    {
                        "world_id": env.world.value.hex,
                        "character_id": identity.hex,
                        "name": f"Witness {index}",
                        "revision": 0,
                    }
                )
                states.append(
                    {
                        "world_id": env.world.value.hex,
                        "character_id": identity.hex,
                        "location_id": env.home.value.hex,
                        "revision": 0,
                    }
                )
            async with env.database.engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO characters(world_id,character_id,name,revision) "
                        "VALUES (:world_id,:character_id,:name,:revision)"
                    ),
                    rows,
                )
                await connection.execute(
                    text(
                        "INSERT INTO character_states(world_id,character_id,location_id,revision) "
                        "VALUES (:world_id,:character_id,:location_id,:revision)"
                    ),
                    states,
                )
            event_id = (
                await ActionResolutionService(env.database.unit_of_work, env.clock).execute(
                    RequestId(uuid4()), _move_proposal(env)
                )
            ).event_ids[0]
            assert len(await env.rows("observations")) == 257
            world_request = ActivationRequest(
                world_id=env.world,
                target=ActivationTarget.world(env.world),
                activation_kind=ActivationKind.WORLD_ORCHESTRATION,
                activation_version=1,
                cause=ActivationCause(
                    env.world,
                    ActivationCauseKind.WORLD_EVENT,
                    source_event_id=event_id,
                ),
                due_at=WorldTime(123),
                coalescing_key="broad_event",
            )
            result = await _service(env).request(world_request)
            assert result.activation.target.kind is ActivationTargetKind.WORLD
            assert len(await env.rows("simulation_activations")) == 1
            assert len(await env.rows("simulation_activation_causes")) == 1
        finally:
            await env.database.close()

    asyncio.run(run())


def test_ten_thousand_characters_create_only_three_targeted_records_and_no_tasks(environment):
    async def run():
        env = environment
        try:
            await env.initialize()
            identities = [uuid4() for _ in range(9_998)]
            async with env.database.engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO characters(world_id,character_id,name,revision) "
                        "VALUES (:world_id,:character_id,:name,0)"
                    ),
                    [
                        {
                            "world_id": env.world.value.hex,
                            "character_id": identity.hex,
                            "name": f"Sparse {index}",
                        }
                        for index, identity in enumerate(identities)
                    ],
                )
                plan = (
                    await connection.execute(
                        text(
                            "EXPLAIN QUERY PLAN SELECT * FROM characters "
                            "WHERE world_id=:world_id AND character_id=:character_id"
                        ),
                        {
                            "world_id": env.world.value.hex,
                            "character_id": identities[0].hex,
                        },
                    )
                ).all()
            assert all("SCAN characters" not in row[3] for row in plan)
            targets = (
                env.alice,
                env.bob,
                CharacterId(env.world, identities[0]),
            )
            task_snapshot = set(asyncio.all_tasks())
            service = _service(env)
            await asyncio.gather(
                *(service.request(_explicit_request(target)) for target in targets)
            )
            assert set(asyncio.all_tasks()) == task_snapshot
            assert len(await env.rows("characters")) == 10_000
            assert len(await env.rows("simulation_activations")) == 3
            assert len(await env.rows("simulation_activation_causes")) == 3
        finally:
            await env.database.close()

    asyncio.run(run())


def test_activation_rows_do_not_persist_private_payload_canaries(environment):
    async def run():
        env = environment
        try:
            await env.initialize()
            await _place(env, env.alice)
            await _service(env).promote_character_active(
                env.alice,
                RequestId(uuid4()),
                WorldTime(123),
            )
            serialized = " ".join(
                str(value)
                for table in (
                    await env.rows("simulation_activations"),
                    await env.rows("simulation_activation_causes"),
                )
                for row in table
                for value in row
            )
            for canary in (
                "PRIVATE_DIALOGUE_CANARY",
                "SECRET_TOKEN_CANARY",
                "PROMPT_CANARY",
                "MEMORY_CANARY",
            ):
                assert canary not in serialized
        finally:
            await env.database.close()

    asyncio.run(run())
