import asyncio
from decimal import Decimal
from uuid import UUID

from livingworld.application.command_handler import CommandHandler
from livingworld.application.developer_inspector import (
    INSPECTOR_TRIGGER_KIND,
    DeveloperInspectorService,
    demo_identity,
)
from livingworld.application.memory import EpisodicMemoryService
from livingworld.application.scenes import SceneService
from livingworld.application.scheduler import (
    SchedulerWakeSignal,
    SimulationScheduler,
    SimulationSchedulerRuntime,
    TriggerKindRegistry,
)
from livingworld.application.simulation_clock import (
    EffectiveWorldTimeSource,
    SystemMonotonicClock,
)
from livingworld.application.simulation_runtime import (
    WorldClockService,
    WorldRuntimeState,
    WorldSimulationRuntime,
)
from livingworld.domain.identifiers import ObservationId
from livingworld.infrastructure.clock import SystemWallClock
from livingworld.infrastructure.persistence import Database


def test_inspector_uses_real_runtime_paths_and_owner_scoped_memory(tmp_path):
    async def run():
        database = Database(tmp_path)
        await database.initialize()
        wall = SystemWallClock()
        monotonic = SystemMonotonicClock()
        source = EffectiveWorldTimeSource(wall, monotonic)
        wake = SchedulerWakeSignal()
        registry = TriggerKindRegistry({(INSPECTOR_TRIGGER_KIND, 1): lambda _payload: None})
        scheduler = SimulationScheduler(database.simulation_scheduler_store(registry), wall, wake)
        realtime = SimulationSchedulerRuntime(scheduler, source, wake)
        clocks = WorldClockService(
            database.world_clock_store(), wall, source, on_clock_changed=realtime.clock_reanchored
        )
        runtime = WorldSimulationRuntime(clocks, scheduler, realtime, source, monotonic)
        commands = CommandHandler(
            database.unit_of_work,
            wall,
            world_time_source=source,
            mutation_barrier=runtime,
            wake_signal=wake,
            world_runtime_registrar=runtime,
        )
        inspector = DeveloperInspectorService(
            database.developer_inspector_store(),
            commands,
            SceneService(database.unit_of_work, wall),
            EpisodicMemoryService(
                database.unit_of_work,
                wall,
                world_time_source=source,
                mutation_barrier=runtime,
            ),
            scheduler,
            clocks,
            runtime,
            database.character_memory_reader,
            database.unit_of_work,
        )
        ids = demo_identity()
        try:
            assert await inspector.list_worlds() == []
            assert await inspector.create_demo_world() == ids.world
            # The deterministic setup can be safely retried without duplicate state.
            assert await inspector.create_demo_world() == ids.world
            first = await inspector.snapshot(ids.world, ids.character_a)
            assert first["world"]["name"] == "world_demo"
            assert {item["name"] for item in first["locations"]} == {
                "location_a",
                "location_b",
            }
            assert first["runtime_state"] == WorldRuntimeState.READY.value
            assert first["scenes"][0]["participants"][0]["name"] == "character_a"

            await inspector.pause(ids.world)
            paused = await inspector.snapshot(ids.world, ids.character_a)
            await asyncio.sleep(0.02)
            paused_again = await inspector.snapshot(ids.world, ids.character_a)
            assert paused["runtime_state"] == WorldRuntimeState.PAUSED.value
            assert paused_again["clock"]["world_time"] == paused["clock"]["world_time"]
            await inspector.change_scale(ids.world, Decimal("4"))
            await inspector.resume(ids.world)
            await asyncio.sleep(0.02)
            resumed = await inspector.snapshot(ids.world, ids.character_a)
            assert int(resumed["clock"]["world_time"]) > int(paused["clock"]["world_time"])

            await inspector.schedule_trigger(ids.world, 0, ids.character_a)
            for _ in range(50):
                scheduled = await inspector.snapshot(ids.world, ids.character_a)
                if scheduled["activations"]:
                    break
                await asyncio.sleep(0.01)
            assert scheduled["triggers"][0]["status"] == "fired"
            assert scheduled["activations"][0]["cause_count"] == 1
            assert scheduled["activations"][0]["fidelity"] is not None

            await inspector.move_player(ids.world, ids.player_a, ids.location_b)
            moved = await inspector.snapshot(ids.world, ids.character_a)
            assert moved["players"][0]["location_id"] == str(ids.location_b.value)
            assert moved["events"][0]["type"] == "PlayerMoved"
            evidence = next(
                item
                for item in moved["observations"]
                if item["principal_id"] == str(ids.character_a.value)
            )
            memory_id = await inspector.record_memory(
                ids.world,
                ids.character_a,
                ObservationId(ids.world, UUID(evidence["observation_id"])),
                "I witnessed player_a move between locations.",
                50,
            )
            final = await inspector.snapshot(ids.world, ids.character_a)
            assert final["memories"][0]["memory_id"] == str(memory_id.value)
            assert (
                final["memories"][0]["evidence"][0]["observation_id"] == evidence["observation_id"]
            )
            owner_b = await inspector.snapshot(ids.world, ids.character_b)
            assert owner_b["memories"] == []
        finally:
            await runtime.aclose()
            await database.close()

    asyncio.run(run())
