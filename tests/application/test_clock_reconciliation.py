import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from livingworld.application.action_resolution import ActionResolutionService
from livingworld.application.command_handler import CommandHandler
from livingworld.application.commands import CreateWorld
from livingworld.application.errors import WorldCatchingUpError
from livingworld.application.scheduler import (
    SchedulerWakeSignal,
    ScheduleTrigger,
    SimulationScheduler,
    SimulationSchedulerRuntime,
    TriggerKindRegistry,
)
from livingworld.application.simulation_clock import EffectiveWorldTimeSource
from livingworld.application.simulation_runtime import (
    ClockAnomaly,
    WorldClockService,
    WorldRuntimeState,
    WorldSimulationRuntime,
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
from livingworld.domain.identifiers import TriggerId, WorldId
from livingworld.domain.simulation import SimulationPayload, TriggerStatus
from livingworld.domain.values import Revision, WorldTime
from livingworld.domain.world import ClockState, WorldClock
from livingworld.infrastructure.persistence import Database

ZERO_WORLD_TIME = WorldTime(0)


class FakeUtcClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now_utc(self) -> datetime:
        return self.value


class FakeMonotonicClock:
    def __init__(self) -> None:
        self.value = 0

    def now_ns(self) -> int:
        return self.value

    def advance(self, *, seconds: int = 0, nanoseconds: int = 0) -> None:
        self.value += seconds * 1_000_000_000 + nanoseconds


class AnchorTimeSource:
    def read(self, clock: WorldClock) -> WorldTime:
        return clock.logical_time


def registry() -> TriggerKindRegistry:
    return TriggerKindRegistry({("test.catch_up", 1): lambda payload: None})


async def create_world(
    database: Database,
    utc_clock: FakeUtcClock,
    world_id: WorldId,
    *,
    initial_time: WorldTime = ZERO_WORLD_TIME,
    scale: Decimal = Decimal("1"),
    state: ClockState = ClockState.RUNNING,
) -> None:
    handler = CommandHandler(
        database.unit_of_work,
        utc_clock,
        world_time_source=AnchorTimeSource(),
    )
    await handler.execute(
        CreateWorld(
            request_id=RequestId(uuid4()),
            world_id=world_id,
            name="Clock Test World",
            initial_time=initial_time,
            time_scale=scale,
            clock_state=state,
        )
    )


def runtime_components(database, utc_clock, monotonic, *, batch=128, kind_registry=None):
    source = EffectiveWorldTimeSource(utc_clock, monotonic)
    wake = SchedulerWakeSignal()
    scheduler = SimulationScheduler(
        database.simulation_scheduler_store(kind_registry or registry()), utc_clock, wake
    )
    realtime = SimulationSchedulerRuntime(scheduler, source, wake, max_batch=batch)
    clocks = WorldClockService(
        database.world_clock_store(),
        utc_clock,
        source,
        on_clock_changed=realtime.clock_reanchored,
    )
    runtime = WorldSimulationRuntime(
        clocks,
        scheduler,
        realtime,
        source,
        monotonic,
        max_batch=batch,
    )
    return source, scheduler, realtime, clocks, runtime


def test_realtime_uses_one_monotonic_base_and_ignores_utc_jumps():
    anchor = datetime(2026, 9, 20, 12, tzinfo=UTC)
    utc_clock = FakeUtcClock(anchor)
    monotonic = FakeMonotonicClock()
    world_id = WorldId(uuid4())
    clock = WorldClock(world_id, WorldTime(0), anchor, Decimal("1"), ClockState.RUNNING)
    source = EffectiveWorldTimeSource(utc_clock, monotonic)
    source.establish(clock)

    monotonic.advance(seconds=10)
    utc_clock.value += timedelta(hours=12)
    assert source.read(clock) == WorldTime(10_000_000)

    monotonic.advance(seconds=5)
    utc_clock.value -= timedelta(days=2)
    assert source.read(clock) == WorldTime(15_000_000)

    fractional = replace(clock, time_scale=Decimal("0.5"), revision=Revision(1))
    source.establish(fractional, WorldTime(0))
    monotonic.advance(nanoseconds=1_000)
    assert source.read(fractional) == WorldTime(0)
    monotonic.advance(nanoseconds=1_000)
    assert source.read(fractional) == WorldTime(1)


def test_pause_resume_scale_and_graceful_checkpoint_are_exact(tmp_path):
    async def run():
        database = Database(tmp_path)
        await database.initialize()
        anchor = datetime(2026, 9, 20, 12, tzinfo=UTC)
        utc_clock = FakeUtcClock(anchor)
        monotonic = FakeMonotonicClock()
        world_id = WorldId(uuid4())
        await create_world(database, utc_clock, world_id)
        source = EffectiveWorldTimeSource(utc_clock, monotonic)
        clocks = WorldClockService(database.world_clock_store(), utc_clock, source)
        try:
            await clocks.reconcile_startup(world_id)
            monotonic.advance(seconds=10)
            utc_clock.value += timedelta(seconds=10)
            paused = await clocks.pause(world_id)
            assert paused.logical_time == WorldTime(10_000_000)
            assert paused.state is ClockState.PAUSED

            monotonic.advance(seconds=30)
            utc_clock.value += timedelta(hours=12)
            assert clocks.current_time(paused) == WorldTime(10_000_000)

            resumed = await clocks.resume(world_id)
            monotonic.advance(seconds=10)
            utc_clock.value -= timedelta(hours=24)
            scaled = await clocks.change_scale(world_id, Decimal("2"))
            assert scaled.logical_time == WorldTime(20_000_000)
            assert scaled.time_scale == Decimal("2")
            assert scaled.observed_wall_time_utc >= resumed.observed_wall_time_utc

            monotonic.advance(seconds=10)
            assert clocks.current_time(scaled) == WorldTime(40_000_000)
            checkpoint = await clocks.checkpoint(world_id)
            assert checkpoint.logical_time == WorldTime(40_000_000)
        finally:
            await database.close()

    asyncio.run(run())


def test_startup_bridge_graceful_crash_paused_regression_and_idempotency(tmp_path):
    async def run():
        anchor = datetime(2026, 9, 20, 12, tzinfo=UTC)
        database = Database(tmp_path)
        await database.initialize()
        running, paused, regression = (WorldId(uuid4()) for _ in range(3))
        initial = FakeUtcClock(anchor)
        await create_world(database, initial, running, initial_time=WorldTime(5))
        await create_world(
            database,
            initial,
            paused,
            initial_time=WorldTime(7),
            scale=Decimal("3"),
            state=ClockState.PAUSED,
        )
        await create_world(database, initial, regression, initial_time=WorldTime(11))

        startup = FakeUtcClock(anchor + timedelta(hours=1))
        monotonic = FakeMonotonicClock()
        _, _, realtime, clocks, _ = runtime_components(database, startup, monotonic)
        try:
            running_result = await clocks.reconcile_startup(running)
            assert running_result.target_world_time == WorldTime(3_600_000_005)
            paused_result = await clocks.reconcile_startup(paused)
            assert paused_result.target_world_time == WorldTime(7)
            assert paused_result.offline_elapsed_microseconds == 3_600_000_000

            startup.value = anchor - timedelta(hours=1)
            regression_result = await clocks.reconcile_startup(regression)
            assert regression_result.target_world_time == WorldTime(11)
            assert regression_result.anomalies == (ClockAnomaly.WALL_CLOCK_REGRESSION,)
            assert regression_result.clock.observed_wall_time_utc == anchor

            # Re-running at the same wall observation changes only the revision.
            repeated = await clocks.reconcile_startup(regression)
            assert repeated.target_world_time == WorldTime(11)
        finally:
            await realtime.aclose()
            await database.close()

    asyncio.run(run())


def test_graceful_and_crash_restart_cover_exact_elapsed_intervals(tmp_path):
    async def run():
        anchor = datetime(2026, 9, 20, 12, tzinfo=UTC)
        database = Database(tmp_path)
        await database.initialize()
        graceful, crashed = WorldId(uuid4()), WorldId(uuid4())
        utc_clock = FakeUtcClock(anchor)
        await create_world(database, utc_clock, graceful)
        await create_world(database, utc_clock, crashed)
        monotonic = FakeMonotonicClock()
        _, _, realtime, clocks, _ = runtime_components(database, utc_clock, monotonic)
        await clocks.reconcile_startup(graceful)
        await clocks.reconcile_startup(crashed)
        monotonic.advance(seconds=10)
        utc_clock.value += timedelta(seconds=10)
        graceful_checkpoint = await clocks.checkpoint(graceful)
        assert graceful_checkpoint.logical_time == WorldTime(10_000_000)
        await realtime.aclose()
        await database.close()

        # The crashed clock retained its original persisted anchor. Both the ten
        # uncheckpointed seconds and the following hour are bridged exactly once.
        utc_clock.value += timedelta(hours=1)
        restarted = Database(tmp_path)
        await restarted.initialize()
        next_monotonic = FakeMonotonicClock()
        _, _, next_realtime, next_clocks, _ = runtime_components(
            restarted, utc_clock, next_monotonic
        )
        try:
            graceful_result = await next_clocks.reconcile_startup(graceful)
            crash_result = await next_clocks.reconcile_startup(crashed)
            assert graceful_result.target_world_time == WorldTime(3_610_000_000)
            assert crash_result.target_world_time == WorldTime(3_610_000_000)
        finally:
            await next_realtime.aclose()
            await restarted.close()

    asyncio.run(run())


def test_365_day_empty_gap_is_one_reconciliation_and_one_bounded_query(tmp_path):
    async def run():
        database = Database(tmp_path)
        await database.initialize()
        anchor = datetime(2025, 9, 20, 12, tzinfo=UTC)
        utc_clock = FakeUtcClock(anchor)
        monotonic = FakeMonotonicClock()
        world_id = WorldId(uuid4())
        await create_world(database, utc_clock, world_id)
        utc_clock.value += timedelta(days=365)
        _, _, _, _, runtime = runtime_components(database, utc_clock, monotonic, batch=16)
        try:
            reports = await runtime.start_all()
            assert len(reports) == 1
            report = reports[0]
            assert report.target_world_time == WorldTime(365 * 86_400_000_000)
            assert report.batches == 1
            assert report.triggers_materialized == 0
            assert report.completed
            assert runtime.state(world_id) is WorldRuntimeState.READY
        finally:
            await runtime.aclose()
            await database.close()

    asyncio.run(run())


def test_large_backlog_drains_in_bounded_stable_batches(tmp_path):
    async def run():
        database = Database(tmp_path)
        await database.initialize()
        anchor = datetime(2026, 9, 20, 12, tzinfo=UTC)
        utc_clock = FakeUtcClock(anchor)
        monotonic = FakeMonotonicClock()
        world_id = WorldId(uuid4())
        await create_world(database, utc_clock, world_id, state=ClockState.PAUSED)
        seed_scheduler = SimulationScheduler(
            database.simulation_scheduler_store(registry()),
            utc_clock,
            SchedulerWakeSignal(),
        )
        store = database.simulation_scheduler_store(registry())
        try:
            for value in (5, 1, 3, 2, 4):
                await seed_scheduler.schedule_trigger(
                    ScheduleTrigger(
                        request_id=RequestId(uuid4()),
                        trigger_id=TriggerId(world_id, uuid4()),
                        world_id=world_id,
                        due_at=WorldTime(value),
                        kind="test.catch_up",
                        payload_version=1,
                        payload=SimulationPayload({"marker": value}),
                    )
                )
            _, scheduler, _, _, runtime = runtime_components(
                database, utc_clock, monotonic, batch=2
            )
            # Paused catch-up still drains work due at the current logical coordinate.
            async with database.engine.begin() as connection:
                from sqlalchemy import text

                await connection.execute(
                    text("UPDATE world_clocks SET logical_time=5 WHERE world_id=:world"),
                    {"world": world_id.value.hex},
                )
            report = await runtime.start_world(world_id)
            assert report.batches == 3
            assert report.triggers_materialized == 5
            assert not report.more_due and report.completed
            triggers = [
                await scheduler.get_trigger(TriggerId(world_id, row.trigger_id))
                for row in await _trigger_rows(database)
            ]
            assert all(item.status is TriggerStatus.FIRED for item in triggers)
            assert len(await store.list_activations(world_id)) == 5
        finally:
            await runtime.aclose()
            await database.close()

    asyncio.run(run())


async def _trigger_rows(database):
    from livingworld.infrastructure.persistence.models import ScheduledSimulationTriggerRecord
    from sqlalchemy import select

    async with database.engine.connect() as connection:
        return (
            await connection.execute(
                select(ScheduledSimulationTriggerRecord).order_by(
                    ScheduledSimulationTriggerRecord.due_at,
                    ScheduledSimulationTriggerRecord.priority,
                    ScheduledSimulationTriggerRecord.enqueue_position,
                )
            )
        ).all()


class FailAfterFirstBatch:
    def __init__(self, scheduler):
        self.scheduler = scheduler
        self.calls = 0

    async def drain_due(self, *args, **kwargs):
        self.calls += 1
        if self.calls > 1:
            raise RuntimeError("simulated_process_stop")
        return await self.scheduler.drain_due(*args, **kwargs)

    async def list_due(self, *args, **kwargs):
        return await self.scheduler.list_due(*args, **kwargs)


class FailOneWorld:
    def __init__(self, scheduler, failed_world):
        self.scheduler = scheduler
        self.failed_world = failed_world

    async def drain_due(self, world_id, *args, **kwargs):
        if world_id == self.failed_world:
            raise RuntimeError("isolated_world_failure")
        return await self.scheduler.drain_due(world_id, *args, **kwargs)

    async def list_due(self, *args, **kwargs):
        return await self.scheduler.list_due(*args, **kwargs)


def test_multi_world_startup_isolates_running_paused_and_failed_worlds(tmp_path):
    async def run():
        database = Database(tmp_path)
        await database.initialize()
        anchor = datetime(2026, 9, 20, 12, tzinfo=UTC)
        utc_clock = FakeUtcClock(anchor)
        monotonic = FakeMonotonicClock()
        running, paused, failed = (WorldId(uuid4()) for _ in range(3))
        await create_world(database, utc_clock, running)
        await create_world(database, utc_clock, paused, state=ClockState.PAUSED)
        await create_world(database, utc_clock, failed)
        utc_clock.value += timedelta(seconds=5)
        source, scheduler, realtime, clocks, _ = runtime_components(database, utc_clock, monotonic)
        runtime = WorldSimulationRuntime(
            clocks,
            FailOneWorld(scheduler, failed),
            realtime,
            source,
            monotonic,
        )
        try:
            reports = await runtime.start_all()
            assert {report.world_id for report in reports} == {running, paused}
            assert runtime.state(running) is WorldRuntimeState.READY
            assert runtime.state(paused) is WorldRuntimeState.PAUSED
            assert runtime.state(failed) is WorldRuntimeState.DEGRADED
            assert runtime.report(failed) is None
        finally:
            await runtime.aclose()
            await database.close()

    asyncio.run(run())


def test_restart_mid_catch_up_keeps_target_and_does_not_duplicate(tmp_path):
    async def run():
        anchor = datetime(2026, 9, 20, 12, tzinfo=UTC)
        utc_clock = FakeUtcClock(anchor)
        world_id = WorldId(uuid4())
        database = Database(tmp_path)
        await database.initialize()
        await create_world(database, utc_clock, world_id)
        monotonic = FakeMonotonicClock()
        setup_wake = SchedulerWakeSignal()
        scheduler = SimulationScheduler(
            database.simulation_scheduler_store(registry()), utc_clock, setup_wake
        )
        for due in (1, 2, 3):
            await scheduler.schedule_trigger(
                ScheduleTrigger(
                    request_id=RequestId(uuid4()),
                    trigger_id=TriggerId(world_id, uuid4()),
                    world_id=world_id,
                    due_at=WorldTime(due),
                    kind="test.catch_up",
                    payload_version=1,
                    payload=SimulationPayload({"due": due}),
                )
            )
        source = EffectiveWorldTimeSource(utc_clock, monotonic)
        realtime_wake = SchedulerWakeSignal()
        realtime_scheduler = SimulationScheduler(
            database.simulation_scheduler_store(registry()), utc_clock, realtime_wake
        )
        realtime = SimulationSchedulerRuntime(
            realtime_scheduler, source, realtime_wake, max_batch=1
        )
        clocks = WorldClockService(
            database.world_clock_store(),
            utc_clock,
            source,
            on_clock_changed=realtime.clock_reanchored,
        )
        utc_clock.value += timedelta(seconds=10)
        interrupted = WorldSimulationRuntime(
            clocks,
            FailAfterFirstBatch(scheduler),
            realtime,
            source,
            monotonic,
            max_batch=1,
        )
        assert await interrupted.start_all() == ()
        assert interrupted.state(world_id) is WorldRuntimeState.DEGRADED
        persisted_target = (await database.world_clock_store().get(world_id)).logical_time
        await interrupted.aclose()
        await database.close()

        restarted = Database(tmp_path)
        await restarted.initialize()
        next_monotonic = FakeMonotonicClock()
        _, _, _, _, resumed = runtime_components(restarted, utc_clock, next_monotonic, batch=1)
        try:
            report = (await resumed.start_all())[0]
            assert report.from_world_time == report.target_world_time == persisted_target
            store = restarted.simulation_scheduler_store(registry())
            activations = await store.list_activations(world_id)
            assert len(activations) == 3
            assert len({item.activation_id for item in activations}) == 3
            assert report.triggers_materialized == 2
        finally:
            await resumed.aclose()
            await restarted.close()

    asyncio.run(run())


class BlockingScheduler:
    def __init__(self, scheduler):
        self.scheduler = scheduler
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def drain_due(self, *args, **kwargs):
        self.entered.set()
        await self.release.wait()
        return await self.scheduler.drain_due(*args, **kwargs)

    async def list_due(self, *args, **kwargs):
        return await self.scheduler.list_due(*args, **kwargs)


def test_action_cannot_overtake_temporal_catch_up(environment):
    async def run():
        env = environment
        await env.initialize()
        monotonic = FakeMonotonicClock()
        source, scheduler, realtime, clocks, _ = runtime_components(
            env.database, env.clock, monotonic
        )
        blocking = BlockingScheduler(scheduler)
        runtime = WorldSimulationRuntime(clocks, blocking, realtime, source, monotonic, max_batch=8)
        catch_up = asyncio.create_task(runtime.start_world(env.world))
        await blocking.entered.wait()
        request_id = RequestId(uuid4())
        action = ActionProposal(
            env.world,
            ActionKind.MOVE_PLAYER,
            1,
            ActionProposer(ProposerKind.PLAYER_INPUT, env.player),
            env.player,
            MovePlayerPayload(env.cafe, Revision()),
        )
        service = ActionResolutionService(
            env.database.unit_of_work,
            env.clock,
            world_time_source=clocks,
            mutation_barrier=runtime,
        )
        before_events = len(await env.rows("world_events"))
        before_observations = len(await env.rows("observations"))
        try:
            with pytest.raises(WorldCatchingUpError, match="WORLD_CATCHING_UP"):
                await service.execute(request_id, action)
            assert len(await env.rows("world_events")) == before_events
            assert len(await env.rows("observations")) == before_observations
            blocking.release.set()
            await catch_up
            assert runtime.state(env.world) is WorldRuntimeState.READY
            result = await service.execute(request_id, action)
            assert result.status is ActionResolutionStatus.ACCEPTED
        finally:
            blocking.release.set()
            await runtime.aclose()
            await env.database.close()

    asyncio.run(run())
