import asyncio
import io
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from livingworld.application.command_handler import CommandHandler
from livingworld.application.commands import CreateWorld
from livingworld.application.errors import (
    IdempotencyConflictError,
    TriggerAlreadyFiredError,
    UnsupportedTriggerError,
)
from livingworld.application.scheduler import (
    SchedulerDiagnostic,
    SchedulerWakeSignal,
    ScheduleTrigger,
    SimulationScheduler,
    SimulationSchedulerRuntime,
    TriggerKindRegistry,
)
from livingworld.application.simulation_clock import EffectiveWorldTimeSource, SystemMonotonicClock
from livingworld.domain.contracts import RequestId
from livingworld.domain.identifiers import TriggerId, WorldId
from livingworld.domain.simulation import SimulationPayload, TriggerPriority, TriggerStatus
from livingworld.domain.values import WorldTime
from livingworld.domain.world import ClockState
from livingworld.infrastructure.clock import SystemWallClock
from livingworld.infrastructure.logging import StructuredLogger
from livingworld.infrastructure.persistence import Database
from livingworld.infrastructure.persistence.models import ScheduledSimulationTriggerRecord
from livingworld.infrastructure.scheduler_runtime import StructuredSchedulerDiagnosticSink
from sqlalchemy import insert, text


class FixedClock:
    def __init__(self):
        self.value = datetime(2026, 9, 19, 12, tzinfo=UTC)

    def now_utc(self):
        return self.value


def marker_registry():
    def validate(payload):
        if "marker" not in payload.data:
            raise ValueError("marker_required")

    return TriggerKindRegistry({("test.simulation_marker", 1): validate})


class SchedulerEnvironment:
    def __init__(self, path):
        self.database = Database(path)
        self.clock = FixedClock()
        self.world = WorldId(uuid4())
        self.registry = marker_registry()
        self.wake = SchedulerWakeSignal()

    async def initialize(self, *, state=ClockState.PAUSED, scale=Decimal("1")):
        await self.database.initialize()
        handler = CommandHandler(self.database.unit_of_work, self.clock)
        await handler.execute(
            CreateWorld(
                request_id=RequestId(uuid4()),
                world_id=self.world,
                name="Scheduler World",
                initial_time=WorldTime(0),
                time_scale=scale,
                clock_state=state,
            )
        )
        self.store = self.database.simulation_scheduler_store(self.registry)
        self.scheduler = SimulationScheduler(self.store, self.clock, self.wake)
        return self

    def request(
        self,
        due,
        *,
        request_id=None,
        trigger_id=None,
        priority=TriggerPriority.NORMAL,
        marker="marker",
        world=None,
    ):
        world = world or self.world
        return ScheduleTrigger(
            request_id=request_id or RequestId(uuid4()),
            trigger_id=trigger_id or TriggerId(world, uuid4()),
            world_id=world,
            due_at=WorldTime(due),
            priority=priority,
            kind="test.simulation_marker",
            payload_version=1,
            payload=SimulationPayload({"marker": marker}),
        )


async def wait_for_activation(env, *, max_wait_seconds=1.0):
    deadline = asyncio.get_running_loop().time() + max_wait_seconds
    while asyncio.get_running_loop().time() < deadline:
        activations = await env.store.list_activations(env.world)
        if activations:
            return activations
        await asyncio.sleep(0.01)
    return ()


@pytest.fixture
def scheduler_environment(tmp_path):
    return SchedulerEnvironment(tmp_path)


def test_deterministic_order_and_world_isolation(scheduler_environment, tmp_path):
    async def run():
        env = await scheduler_environment.initialize()
        other = WorldId(uuid4())
        handler = CommandHandler(env.database.unit_of_work, env.clock)
        await handler.execute(
            CreateWorld(request_id=RequestId(uuid4()), world_id=other, name="Other")
        )
        requests = (
            env.request(10, priority=TriggerPriority.LOW, marker="low"),
            env.request(10, priority=TriggerPriority.HIGH, marker="first-high"),
            env.request(10, priority=TriggerPriority.HIGH, marker="second-high"),
            env.request(9, priority=TriggerPriority.LOW, marker="earlier"),
            env.request(0, world=other, marker="other"),
        )
        try:
            for request in requests:
                await env.scheduler.schedule_trigger(request)
            due = await env.scheduler.list_due(env.world, WorldTime(10), 10)
            assert [item.payload.data["marker"] for item in due] == [
                "earlier",
                "first-high",
                "second-high",
                "low",
            ]
            assert due[1].enqueue_position < due[2].enqueue_position
            assert all(item.world_id == env.world for item in due)
            materialized = await env.scheduler.drain_due(env.world, WorldTime(10), 10)
            assert [item.payload.data["marker"] for item in materialized.activations] == [
                "earlier",
                "first-high",
                "second-high",
                "low",
            ]
        finally:
            await env.database.close()

    asyncio.run(run())


def test_unsupported_kind_version_fails_closed_without_queue_write(scheduler_environment):
    async def run():
        env = await scheduler_environment.initialize()
        unsupported = replace(env.request(10), payload_version=2)
        try:
            with pytest.raises(UnsupportedTriggerError, match="unsupported_trigger"):
                await env.scheduler.schedule_trigger(unsupported)
            assert await env.scheduler.peek_next(env.world) is None
            async with env.database.engine.connect() as connection:
                assert (
                    await connection.execute(text("SELECT count(*) FROM simulation_queue_cursors"))
                ).scalar_one() == 0
        finally:
            await env.database.close()

    asyncio.run(run())


def test_schedule_idempotency_and_semantic_conflict(scheduler_environment):
    async def run():
        env = await scheduler_environment.initialize()
        request = env.request(10)
        try:
            first = await env.scheduler.schedule_trigger(request)
            replay = await env.scheduler.schedule_trigger(request)
            assert replay.replayed and replay.trigger == first.trigger
            replay_only = SimulationScheduler(
                env.database.simulation_scheduler_store(TriggerKindRegistry()),
                env.clock,
                SchedulerWakeSignal(),
            )
            assert (await replay_only.schedule_trigger(request)).replayed
            with pytest.raises(IdempotencyConflictError):
                await env.scheduler.schedule_trigger(replace(request, due_at=WorldTime(11)))
            next_result = await env.scheduler.schedule_trigger(env.request(12))
            assert next_result.trigger.enqueue_position == 2
        finally:
            await env.database.close()

    asyncio.run(run())


def test_cancel_is_idempotent_and_cancel_after_fired_is_explicit(scheduler_environment):
    async def run():
        env = await scheduler_environment.initialize()
        cancelled_request = env.request(1)
        fired_request = env.request(1)
        try:
            await env.scheduler.schedule_trigger(cancelled_request)
            first = await env.scheduler.cancel_trigger(cancelled_request.trigger_id)
            second = await env.scheduler.cancel_trigger(cancelled_request.trigger_id)
            assert first == second and first.status is TriggerStatus.CANCELLED
            await env.scheduler.schedule_trigger(fired_request)
            assert (await env.scheduler.drain_due(env.world, WorldTime(1), 10)).processed_count == 1
            with pytest.raises(TriggerAlreadyFiredError):
                await env.scheduler.cancel_trigger(fired_request.trigger_id)
        finally:
            await env.database.close()

    asyncio.run(run())


def test_due_boundary_bounded_drain_and_retry_uniqueness(scheduler_environment):
    async def run():
        env = await scheduler_environment.initialize()
        requests = [env.request(value) for value in (10, 10, 11, 12)]
        try:
            for request in requests:
                await env.scheduler.schedule_trigger(request)
            first = await env.scheduler.drain_due(env.world, WorldTime(10), 1)
            assert first.processed_count == 1 and first.more_due
            second = await env.scheduler.materialize_due(env.world, WorldTime(10), 10)
            assert second.processed_count == 1 and not second.more_due
            retry = await env.scheduler.drain_due(env.world, WorldTime(10), 10)
            assert retry.processed_count == 0
            assert len(await env.store.list_activations(env.world)) == 2
            assert (await env.scheduler.peek_next(env.world)).due_at == WorldTime(11)
        finally:
            await env.database.close()

    asyncio.run(run())


def test_failure_before_commit_rolls_back_fired_and_activation(scheduler_environment, monkeypatch):
    async def run():
        env = await scheduler_environment.initialize()
        request = env.request(0)
        await env.scheduler.schedule_trigger(request)
        try:
            with monkeypatch.context() as patch:

                async def fail(session):
                    raise RuntimeError("crash_before_commit")

                patch.setattr(env.store, "_before_materialization_commit", fail)
                with pytest.raises(RuntimeError, match="crash_before_commit"):
                    await env.scheduler.drain_due(env.world, WorldTime(0), 1)
            assert (
                await env.scheduler.get_trigger(request.trigger_id)
            ).status is TriggerStatus.PENDING
            assert await env.store.list_activations(env.world) == ()
            assert (await env.scheduler.drain_due(env.world, WorldTime(0), 1)).processed_count == 1
            async with env.database.engine.connect() as connection:
                parameters = {
                    "world": env.world.value.hex,
                    "trigger": request.trigger_id.value.hex,
                }
                assert (
                    await connection.execute(
                        text(
                            "SELECT status FROM simulation_scheduled_triggers "
                            "WHERE world_id=:world AND trigger_id=:trigger"
                        ),
                        parameters,
                    )
                ).scalar_one() == "fired"
                assert (
                    await connection.execute(
                        text(
                            "SELECT count(*) FROM simulation_activations "
                            "WHERE world_id=:world AND source_trigger_id=:trigger"
                        ),
                        parameters,
                    )
                ).scalar_one() == 1
        finally:
            await env.database.close()

    asyncio.run(run())


def test_two_drainers_cannot_duplicate_activation(scheduler_environment):
    async def run():
        env = await scheduler_environment.initialize()
        second_database = Database(env.database.data_dir)
        await second_database.initialize()
        second_store = second_database.simulation_scheduler_store(env.registry)
        second = SimulationScheduler(second_store, env.clock, SchedulerWakeSignal())
        try:
            await env.scheduler.schedule_trigger(env.request(0))
            results = await asyncio.gather(
                env.scheduler.drain_due(env.world, WorldTime(0), 1),
                second.drain_due(env.world, WorldTime(0), 1),
            )
            assert sorted(result.processed_count for result in results) == [0, 1]
            assert len(await env.store.list_activations(env.world)) == 1
        finally:
            await second_database.close()
            await env.database.close()

    asyncio.run(run())


def test_cancel_materialize_race_has_one_consistent_terminal_state(scheduler_environment):
    async def run():
        env = await scheduler_environment.initialize()
        second_database = Database(env.database.data_dir)
        await second_database.initialize()
        second_store = second_database.simulation_scheduler_store(env.registry)
        second = SimulationScheduler(second_store, env.clock, SchedulerWakeSignal())
        request = env.request(0)
        try:
            await env.scheduler.schedule_trigger(request)
            outcomes = await asyncio.gather(
                env.scheduler.cancel_trigger(request.trigger_id),
                second.drain_due(env.world, WorldTime(0), 1),
                return_exceptions=True,
            )
            trigger = await env.scheduler.get_trigger(request.trigger_id)
            activations = await env.store.list_activations(env.world)
            if trigger.status is TriggerStatus.CANCELLED:
                assert activations == ()
            else:
                assert trigger.status is TriggerStatus.FIRED and len(activations) == 1
                assert any(isinstance(value, TriggerAlreadyFiredError) for value in outcomes)
        finally:
            await second_database.close()
            await env.database.close()

    asyncio.run(run())


def test_runtime_wakes_for_new_earlier_trigger_and_shuts_down(tmp_path):
    async def run():
        env = SchedulerEnvironment(tmp_path)
        env.clock = SystemWallClock()
        await env.initialize(state=ClockState.RUNNING)
        source = EffectiveWorldTimeSource(env.clock, SystemMonotonicClock())
        runtime = SimulationSchedulerRuntime(env.scheduler, source, env.wake, max_batch=8)
        later = env.request(5_000_000, marker="later")
        earlier = env.request(0, marker="earlier")
        try:
            await env.scheduler.schedule_trigger(later)
            await asyncio.sleep(0.02)
            await env.scheduler.schedule_trigger(earlier)
            activations = await wait_for_activation(env)
            assert [item.payload.data["marker"] for item in activations] == ["earlier"]
            assert (
                await env.scheduler.get_trigger(later.trigger_id)
            ).status is TriggerStatus.PENDING
            assert runtime.active_task_count == 1
        finally:
            await runtime.aclose()
            assert runtime.active_task_count == 0
            await env.database.close()

    asyncio.run(run())


def test_pause_and_resume_revision_changes_wake_and_recompute(tmp_path):
    async def run():
        env = SchedulerEnvironment(tmp_path)
        env.clock = SystemWallClock()
        await env.initialize(state=ClockState.RUNNING)
        runtime = SimulationSchedulerRuntime(
            env.scheduler,
            EffectiveWorldTimeSource(env.clock, SystemMonotonicClock()),
            env.wake,
        )
        try:
            await env.scheduler.schedule_trigger(env.request(250_000))
            await asyncio.sleep(0.03)
            now = env.clock.now_utc().isoformat(timespec="microseconds")
            async with env.database.engine.begin() as connection:
                await connection.execute(
                    text(
                        "UPDATE world_clocks SET state='paused', logical_time=0, "
                        "observed_wall_time_utc=:now, revision=1 WHERE world_id=:world"
                    ),
                    {"now": now, "world": env.world.value.hex},
                )
            runtime.clock_changed(env.world)
            await asyncio.sleep(0.3)
            assert await env.store.list_activations(env.world) == ()
            now = env.clock.now_utc().isoformat(timespec="microseconds")
            async with env.database.engine.begin() as connection:
                await connection.execute(
                    text(
                        "UPDATE world_clocks SET state='running', observed_wall_time_utc=:now, "
                        "revision=2 WHERE world_id=:world"
                    ),
                    {"now": now, "world": env.world.value.hex},
                )
            runtime.clock_changed(env.world)
            assert len(await wait_for_activation(env)) == 1
        finally:
            await runtime.aclose()
            await env.database.close()

    asyncio.run(run())


def test_scale_revision_change_interrupts_old_sleep(tmp_path):
    async def run():
        env = SchedulerEnvironment(tmp_path)
        env.clock = SystemWallClock()
        await env.initialize(state=ClockState.RUNNING)
        runtime = SimulationSchedulerRuntime(
            env.scheduler,
            EffectiveWorldTimeSource(env.clock, SystemMonotonicClock()),
            env.wake,
        )
        try:
            await env.scheduler.schedule_trigger(env.request(2_000_000))
            await asyncio.sleep(0.03)
            now = env.clock.now_utc().isoformat(timespec="microseconds")
            async with env.database.engine.begin() as connection:
                await connection.execute(
                    text(
                        "UPDATE world_clocks SET time_scale='100', "
                        "observed_wall_time_utc=:now, logical_time=0, revision=1 "
                        "WHERE world_id=:world"
                    ),
                    {"now": now, "world": env.world.value.hex},
                )
            runtime.clock_changed(env.world)
            assert len(await wait_for_activation(env, max_wait_seconds=0.5)) == 1
        finally:
            await runtime.aclose()
            await env.database.close()

    asyncio.run(run())


def test_diagnostics_are_payload_private(scheduler_environment):
    canary = "PRIVATE_TRIGGER_PAYLOAD_CANARY"
    stream = io.StringIO()
    sink = StructuredSchedulerDiagnosticSink(StructuredLogger(stream))
    sink.emit(
        SchedulerDiagnostic(
            "scheduler_batch_materialized",
            scheduler_environment.world,
            "running",
            trigger_kind="test.simulation_marker",
            due_at=WorldTime(7),
            queue_lag_microseconds=2,
            batch_size=8,
            activation_count=1,
        )
    )
    assert canary not in stream.getvalue()
    assert "payload" not in stream.getvalue()
    assert '"due_world_time": 7' in stream.getvalue()


def test_runtime_does_not_invoke_llm_or_mutate_world_knowledge_relationships(tmp_path):
    async def run():
        env = SchedulerEnvironment(tmp_path)
        await env.initialize()
        stream = io.StringIO()
        runtime = SimulationSchedulerRuntime(
            env.scheduler,
            EffectiveWorldTimeSource(env.clock, SystemMonotonicClock()),
            env.wake,
            diagnostics=StructuredSchedulerDiagnosticSink(StructuredLogger(stream)),
        )
        protected = ("world_events", "knowledge_assertions", "relationships", "llm_attempts")
        try:
            async with env.database.engine.connect() as connection:
                before = {
                    table: (
                        await connection.execute(text(f"SELECT count(*) FROM {table}"))
                    ).scalar_one()
                    for table in protected
                }
            await env.scheduler.schedule_trigger(
                env.request(0, marker="PRIVATE_TRIGGER_PAYLOAD_CANARY")
            )
            assert len(await wait_for_activation(env)) == 1
            async with env.database.engine.connect() as connection:
                after = {
                    table: (
                        await connection.execute(text(f"SELECT count(*) FROM {table}"))
                    ).scalar_one()
                    for table in protected
                }
            assert after == before
            assert "PRIVATE_TRIGGER_PAYLOAD_CANARY" not in stream.getvalue()
            assert "payload" not in stream.getvalue()
        finally:
            await runtime.aclose()
            await env.database.close()

    asyncio.run(run())


def test_due_query_is_indexed_and_runtime_is_world_bounded(scheduler_environment):
    async def run():
        env = await scheduler_environment.initialize()
        try:
            rows = [
                {
                    "world_id": env.world.value,
                    "trigger_id": uuid4(),
                    "due_at": WorldTime(1_000_000_000 + position),
                    "priority": 0,
                    "enqueue_position": position,
                    "kind": "test.simulation_marker",
                    "payload_version": 1,
                    "payload": {"marker": position},
                    "status": "pending",
                    "created_at_utc": env.clock.now_utc(),
                    "fired_at_utc": None,
                    "cancelled_at_utc": None,
                    "revision": 0,
                    "causation_request_id": None,
                    "correlation_id": None,
                    "activation_target_kind": "world",
                    "activation_target_id": env.world.value,
                    "activation_target_character_id": None,
                    "activation_kind": "world_orchestration",
                    "activation_version": 1,
                    "activation_coalescing_key": None,
                    "activation_attention": "none",
                }
                for position in range(1, 10_001)
            ]
            async with env.database.engine.begin() as connection:
                await connection.execute(insert(ScheduledSimulationTriggerRecord), rows)
            async with env.database.engine.connect() as connection:
                plan = (
                    await connection.execute(
                        text(
                            "EXPLAIN QUERY PLAN SELECT * FROM simulation_scheduled_triggers "
                            "WHERE world_id=:world AND status='pending' AND due_at<=:due "
                            "ORDER BY due_at, priority, enqueue_position LIMIT 10"
                        ),
                        {"world": env.world.value.hex, "due": 100},
                    )
                ).all()
            assert "ix_simulation_trigger_due" in " ".join(str(row) for row in plan)
            runtime = SimulationSchedulerRuntime(
                env.scheduler,
                EffectiveWorldTimeSource(env.clock, SystemMonotonicClock()),
                env.wake,
            )
            for _ in range(10_000):
                runtime.activate_world(env.world)
            assert runtime.active_task_count == 1
            assert len(await env.scheduler.list_due(env.world, WorldTime(2_000_000_000), 7)) == 7
            await runtime.aclose()
        finally:
            await env.database.close()

    asyncio.run(run())
