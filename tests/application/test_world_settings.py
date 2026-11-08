import asyncio
from decimal import Decimal
from uuid import uuid4

import pytest
from livingworld.application.command_handler import CommandHandler
from livingworld.application.errors import IdempotencyConflictError
from livingworld.application.scheduler import (
    SchedulerWakeSignal,
    SimulationScheduler,
    SimulationSchedulerRuntime,
    TriggerKindRegistry,
)
from livingworld.application.simulation_clock import EffectiveWorldTimeSource, SystemMonotonicClock
from livingworld.application.simulation_runtime import (
    WorldClockService,
    WorldRuntimeState,
    WorldSimulationRuntime,
)
from livingworld.application.world_settings import WorldSettingsService
from livingworld.domain.contracts import RequestId
from livingworld.infrastructure.clock import SystemWallClock
from livingworld.infrastructure.persistence import Database
from livingworld.infrastructure.persistence.models import WorldEventRecord
from sqlalchemy import func, select


def test_world_creation_is_idempotent_and_immediately_runtime_managed(tmp_path):
    async def run():
        database = Database(tmp_path)
        await database.initialize()
        wall = SystemWallClock()
        monotonic = SystemMonotonicClock()
        source = EffectiveWorldTimeSource(wall, monotonic)
        wake = SchedulerWakeSignal()
        scheduler = SimulationScheduler(
            database.simulation_scheduler_store(TriggerKindRegistry()), wall, wake
        )
        scheduler_runtime = SimulationSchedulerRuntime(scheduler, source, wake)
        clocks = WorldClockService(
            database.world_clock_store(),
            wall,
            source,
            on_clock_changed=scheduler_runtime.clock_reanchored,
        )
        runtime = WorldSimulationRuntime(clocks, scheduler, scheduler_runtime, source, monotonic)
        commands = CommandHandler(
            database.unit_of_work,
            wall,
            world_time_source=source,
            mutation_barrier=runtime,
            wake_signal=wake,
            world_runtime_registrar=runtime,
        )
        service = WorldSettingsService(database.world_directory(), commands, clocks, runtime)
        request_id = RequestId(uuid4())
        try:
            world = await service.create_world(request_id, "我的世界")
            assert await service.create_world(request_id, "我的世界") == world
            assert runtime.state(world) is WorldRuntimeState.READY
            items = await service.list_worlds()
            assert len(items) == 1
            assert items[0].name == "我的世界"
            async with database._sessions() as session:
                count = await session.scalar(select(func.count()).select_from(WorldEventRecord))
            assert count == 1
            with pytest.raises(IdempotencyConflictError):
                await service.create_world(request_id, "另一个世界")
            await service.pause(world)
            assert (await service.list_worlds())[0].clock_state == "paused"
            await service.change_scale(world, Decimal("2.5"))
            await service.resume(world)
            assert (await service.list_worlds())[0].time_scale == Decimal("2.5")
            assert runtime.state(world) is WorldRuntimeState.READY
        finally:
            await runtime.aclose()
            await database.close()

    asyncio.run(run())
