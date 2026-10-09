"""World clock reconciliation and bounded temporal catch-up orchestration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from livingworld.application.errors import (
    EntityNotFoundError,
    WorldCatchingUpError,
    WorldRuntimeUnavailableError,
)
from livingworld.application.ports import WallClock
from livingworld.application.scheduler import SimulationScheduler, SimulationSchedulerRuntime
from livingworld.application.simulation_clock import EffectiveWorldTimeSource, MonotonicClock
from livingworld.domain.identifiers import WorldId
from livingworld.domain.values import Revision, WorldTime, utc_timestamp
from livingworld.domain.world import ClockState, WorldClock


class ClockAnomaly(StrEnum):
    WALL_CLOCK_REGRESSION = "wall_clock_regression"


class WorldRuntimeState(StrEnum):
    STARTING = "starting"
    CATCHING_UP = "catching_up"
    READY = "ready"
    PAUSED = "paused"
    DEGRADED = "degraded"
    STOPPING = "stopping"


class WorldClockStore(Protocol):
    async def list(self) -> tuple[WorldClock, ...]: ...
    async def get(self, world_id: WorldId) -> WorldClock | None: ...
    async def replace(self, clock: WorldClock, expected_revision: Revision) -> WorldClock: ...


@dataclass(frozen=True, slots=True)
class ClockReconciliation:
    clock: WorldClock
    from_world_time: WorldTime
    target_world_time: WorldTime
    offline_elapsed_microseconds: int
    anomalies: tuple[ClockAnomaly, ...]


@dataclass(frozen=True, slots=True)
class CatchUpReport:
    world_id: WorldId
    from_world_time: WorldTime
    target_world_time: WorldTime
    offline_elapsed_microseconds: int
    batches: int
    triggers_materialized: int
    distinct_activations: int
    anomalies: tuple[ClockAnomaly, ...]
    more_due: bool
    completed: bool
    runtime_nanoseconds: int


class CatchUpDiagnosticSink(Protocol):
    def emit(self, report: CatchUpReport) -> None: ...
    def failed(self, world_id: WorldId, state: WorldRuntimeState) -> None: ...


class NullCatchUpDiagnosticSink:
    def emit(self, report: CatchUpReport) -> None:
        pass

    def failed(self, world_id: WorldId, state: WorldRuntimeState) -> None:
        pass


def _elapsed_microseconds(later: datetime, earlier: datetime) -> int:
    delta = later - earlier
    return delta.days * 86_400_000_000 + delta.seconds * 1_000_000 + delta.microseconds


class WorldClockService:
    """Sole authority for effective time and durable WorldClock re-anchoring."""

    def __init__(
        self,
        store: WorldClockStore,
        utc_clock: WallClock,
        time_source: EffectiveWorldTimeSource,
        *,
        on_clock_changed=None,
    ) -> None:
        self._store = store
        self._utc_clock = utc_clock
        self._time_source = time_source
        self._on_clock_changed = on_clock_changed

    async def list_clocks(self) -> tuple[WorldClock, ...]:
        return await self._store.list()

    def current_time(self, clock: WorldClock) -> WorldTime:
        return self._time_source.read(clock)

    def read(self, clock: WorldClock) -> WorldTime:
        return self.current_time(clock)

    async def reconcile_startup(self, world_id: WorldId) -> ClockReconciliation:
        clock = await self._required(world_id)
        observed = utc_timestamp(self._utc_clock.now_utc(), "startup UTC observation")
        elapsed = _elapsed_microseconds(observed, clock.observed_wall_time_utc)
        anomalies = (ClockAnomaly.WALL_CLOCK_REGRESSION,) if elapsed < 0 else ()
        positive_elapsed = max(0, elapsed)
        target = (
            clock.effective_time(observed)
            if clock.state is ClockState.RUNNING
            else clock.logical_time
        )
        safe_wall_anchor = max(clock.observed_wall_time_utc, observed)
        reconciled = replace(
            clock,
            logical_time=target,
            observed_wall_time_utc=safe_wall_anchor,
            revision=Revision(clock.revision.value + 1),
        )
        persisted = await self._store.replace(reconciled, clock.revision)
        self._time_source.establish(persisted, target)
        return ClockReconciliation(
            persisted,
            clock.logical_time,
            target,
            positive_elapsed,
            anomalies,
        )

    async def checkpoint(self, world_id: WorldId) -> WorldClock:
        clock = await self._required(world_id)
        logical_time = self._time_source.read(clock)
        observed = utc_timestamp(self._utc_clock.now_utc(), "checkpoint UTC observation")
        return await self._reanchor(
            clock,
            logical_time=logical_time,
            observed_wall_time_utc=max(clock.observed_wall_time_utc, observed),
            state=clock.state,
            time_scale=clock.time_scale,
        )

    async def pause(self, world_id: WorldId) -> WorldClock:
        return await self._mutate(world_id, state=ClockState.PAUSED)

    async def resume(self, world_id: WorldId) -> WorldClock:
        return await self._mutate(world_id, state=ClockState.RUNNING)

    async def change_scale(self, world_id: WorldId, time_scale: Decimal) -> WorldClock:
        return await self._mutate(world_id, time_scale=time_scale)

    async def _mutate(
        self,
        world_id: WorldId,
        *,
        state: ClockState | None = None,
        time_scale: Decimal | None = None,
    ) -> WorldClock:
        clock = await self._required(world_id)
        logical_time = self._time_source.read(clock)
        observed = utc_timestamp(self._utc_clock.now_utc(), "clock mutation UTC observation")
        return await self._reanchor(
            clock,
            logical_time=logical_time,
            observed_wall_time_utc=max(clock.observed_wall_time_utc, observed),
            state=state if state is not None else clock.state,
            time_scale=time_scale if time_scale is not None else clock.time_scale,
        )

    async def _reanchor(
        self,
        clock: WorldClock,
        *,
        logical_time: WorldTime,
        observed_wall_time_utc: datetime,
        state: ClockState,
        time_scale: Decimal,
    ) -> WorldClock:
        updated = replace(
            clock,
            logical_time=logical_time,
            observed_wall_time_utc=observed_wall_time_utc,
            time_scale=time_scale,
            state=state,
            revision=Revision(clock.revision.value + 1),
        )
        persisted = await self._store.replace(updated, clock.revision)
        self._time_source.establish(persisted, logical_time)
        self._notify(clock.world_id)
        return persisted

    async def _required(self, world_id: WorldId) -> WorldClock:
        clock = await self._store.get(world_id)
        if clock is None:
            raise EntityNotFoundError("WorldClock does not exist")
        return clock

    def _notify(self, world_id: WorldId) -> None:
        if self._on_clock_changed is not None:
            self._on_clock_changed(world_id)


class WorldSimulationRuntime:
    """Reconcile each world once, drain a fixed target, then enter tickless realtime."""

    def __init__(
        self,
        clock_service: WorldClockService,
        scheduler: SimulationScheduler,
        scheduler_runtime: SimulationSchedulerRuntime,
        time_source: EffectiveWorldTimeSource,
        monotonic_clock: MonotonicClock,
        *,
        max_batch: int = 128,
        diagnostics: CatchUpDiagnosticSink | None = None,
    ) -> None:
        if type(max_batch) is not int or max_batch <= 0:
            raise ValueError("max_batch must be a positive integer")
        self._clock_service = clock_service
        self._scheduler = scheduler
        self._scheduler_runtime = scheduler_runtime
        self._time_source = time_source
        self._monotonic_clock = monotonic_clock
        self._max_batch = max_batch
        self._diagnostics = diagnostics or NullCatchUpDiagnosticSink()
        self._states: dict[WorldId, WorldRuntimeState] = {}
        self._reports: dict[WorldId, CatchUpReport] = {}
        self._deletion_previous: dict[WorldId, WorldRuntimeState | None] = {}
        self._closing = False
        self._registration_lock = asyncio.Lock()

    def state(self, world_id: WorldId) -> WorldRuntimeState | None:
        return self._states.get(world_id)

    async def suspend_for_deletion(self, world_id: WorldId) -> None:
        async with self._registration_lock:
            self._deletion_previous[world_id] = self._states.get(world_id)
            self._states[world_id] = WorldRuntimeState.STOPPING
            await self._scheduler_runtime.stop_world(world_id)

    def deletion_finished(self, world_id: WorldId, *, deleted: bool) -> None:
        previous = self._deletion_previous.pop(world_id, None)
        if deleted or previous is None:
            self._states.pop(world_id, None)
            self._reports.pop(world_id, None)
        else:
            self._states[world_id] = previous
        self._time_source.invalidate(world_id)
        if not deleted:
            self._scheduler_runtime.restore_world(world_id)

    def report(self, world_id: WorldId) -> CatchUpReport | None:
        return self._reports.get(world_id)

    async def pause(self, world_id: WorldId) -> WorldClock:
        """Pause one ready World through the canonical clock authority."""
        await self.assert_mutation_allowed(world_id)
        clock = await self._clock_service.pause(world_id)
        self._states[world_id] = WorldRuntimeState.PAUSED
        return clock

    async def resume(self, world_id: WorldId) -> WorldClock:
        """Resume one paused World through the canonical clock authority."""
        await self.assert_mutation_allowed(world_id)
        clock = await self._clock_service.resume(world_id)
        self._states[world_id] = WorldRuntimeState.READY
        return clock

    async def change_scale(self, world_id: WorldId, time_scale: Decimal) -> WorldClock:
        await self.assert_mutation_allowed(world_id)
        return await self._clock_service.change_scale(world_id, time_scale)

    async def start_all(self) -> tuple[CatchUpReport, ...]:
        # Sequential ownership is intentionally bounded. One broken world is isolated
        # and cannot falsify another world's state.
        reports: list[CatchUpReport] = []
        for clock in await self._clock_service.list_clocks():
            report = await self.register_world(clock.world_id)
            if report is not None:
                reports.append(report)
        return tuple(reports)

    async def register_world(self, world_id: WorldId) -> CatchUpReport | None:
        """Start one committed World, representing ordinary failures as DEGRADED."""

        async with self._registration_lock:
            if self._states.get(world_id) in {
                WorldRuntimeState.READY,
                WorldRuntimeState.PAUSED,
            }:
                return self._reports.get(world_id)
            if self._closing:
                self._states[world_id] = WorldRuntimeState.DEGRADED
                self._diagnostics.failed(world_id, WorldRuntimeState.DEGRADED)
                return None
            try:
                return await self.start_world(world_id)
            except Exception:
                self._states[world_id] = WorldRuntimeState.DEGRADED
                self._diagnostics.failed(world_id, WorldRuntimeState.DEGRADED)
                return None

    async def start_world(self, world_id: WorldId) -> CatchUpReport:
        if self._closing:
            raise WorldRuntimeUnavailableError("world_runtime_stopping")
        self._states[world_id] = WorldRuntimeState.STARTING
        started_ns = self._monotonic_clock.now_ns()
        reconciliation = await self._clock_service.reconcile_startup(world_id)
        self._states[world_id] = WorldRuntimeState.CATCHING_UP
        batches = 0
        processed = 0
        activation_ids = set()
        more_due = False
        while not self._closing:
            result = await self._scheduler.drain_due(
                world_id, reconciliation.target_world_time, self._max_batch
            )
            batches += 1
            processed += result.processed_count
            activation_ids.update(item.activation_id for item in result.activations)
            if result.more_due:
                more_due = True
                await asyncio.sleep(0)
                continue
            # Authoritative re-query closes over triggers committed during a prior batch.
            remaining = await self._scheduler.list_due(
                world_id, reconciliation.target_world_time, 1
            )
            if remaining:
                more_due = True
                await asyncio.sleep(0)
                continue
            more_due = False
            break
        completed = not self._closing and not more_due
        report = CatchUpReport(
            world_id=world_id,
            from_world_time=reconciliation.from_world_time,
            target_world_time=reconciliation.target_world_time,
            offline_elapsed_microseconds=reconciliation.offline_elapsed_microseconds,
            batches=batches,
            triggers_materialized=processed,
            distinct_activations=len(activation_ids),
            anomalies=reconciliation.anomalies,
            more_due=more_due,
            completed=completed,
            runtime_nanoseconds=max(0, self._monotonic_clock.now_ns() - started_ns),
        )
        self._reports[world_id] = report
        self._diagnostics.emit(report)
        if completed:
            # Realtime starts from the fixed catch-up target, not from elapsed catch-up wall time.
            self._time_source.establish(reconciliation.clock, reconciliation.target_world_time)
            final_state = (
                WorldRuntimeState.PAUSED
                if reconciliation.clock.state is ClockState.PAUSED
                else WorldRuntimeState.READY
            )
            self._states[world_id] = final_state
            self._scheduler_runtime.activate_world(world_id)
        return report

    async def assert_mutation_allowed(self, world_id: WorldId) -> None:
        state = self._states.get(world_id)
        if state is WorldRuntimeState.CATCHING_UP:
            raise WorldCatchingUpError("WORLD_CATCHING_UP")
        if state in {
            WorldRuntimeState.STARTING,
            WorldRuntimeState.DEGRADED,
            WorldRuntimeState.STOPPING,
        }:
            raise WorldRuntimeUnavailableError(f"world_runtime_{state.value}")

    async def aclose(self) -> None:
        self._closing = True
        checkpoint_states = dict(self._states)
        for world_id in tuple(self._states):
            self._states[world_id] = WorldRuntimeState.STOPPING
        await self._scheduler_runtime.aclose()
        failures: list[BaseException] = []
        for world_id, previous in checkpoint_states.items():
            if previous not in {WorldRuntimeState.READY, WorldRuntimeState.PAUSED}:
                continue
            try:
                await self._clock_service.checkpoint(world_id)
            except BaseException as error:
                failures.append(error)
                self._diagnostics.failed(world_id, WorldRuntimeState.DEGRADED)
        if failures:
            raise ExceptionGroup("world_clock_checkpoint_failed", failures)
