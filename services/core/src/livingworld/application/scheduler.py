"""Application operations for the durable, tickless simulation queue."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol

from livingworld.application.errors import UnsupportedTriggerError
from livingworld.application.fingerprints import canonical_json, id_input
from livingworld.application.ports import WallClock
from livingworld.application.simulation_clock import EffectiveWorldTimeSource, wall_delay_seconds
from livingworld.domain.contracts import RequestId
from livingworld.domain.errors import DomainInvariantError
from livingworld.domain.identifiers import CorrelationId, TriggerId, WorldId
from livingworld.domain.simulation import (
    ActivationAttention,
    ActivationKind,
    ActivationTarget,
    ScheduledSimulationTrigger,
    SimulationActivation,
    SimulationPayload,
    TriggerPriority,
    validate_activation_contract,
    validate_coalescing_key,
)
from livingworld.domain.values import WorldTime, require_type
from livingworld.domain.world import ClockState, World

PayloadValidator = Callable[[SimulationPayload], None]


class TriggerKindRegistry:
    """An explicit in-process allowlist; persisted payloads never name code."""

    def __init__(
        self,
        validators: Mapping[tuple[str, int], PayloadValidator] | None = None,
    ) -> None:
        self._validators = dict(validators or {})

    @property
    def supported(self) -> frozenset[tuple[str, int]]:
        return frozenset(self._validators)

    def validate(self, kind: str, version: int, payload: SimulationPayload) -> None:
        validator = self._validators.get((kind, version))
        if validator is None:
            raise UnsupportedTriggerError(f"unsupported_trigger:{kind}:v{version}")
        validator(payload)


@dataclass(frozen=True, slots=True, kw_only=True)
class ScheduleTrigger:
    request_id: RequestId
    trigger_id: TriggerId
    world_id: WorldId
    due_at: WorldTime
    priority: TriggerPriority = TriggerPriority.NORMAL
    kind: str
    payload_version: int
    payload: SimulationPayload
    correlation_id: CorrelationId | None = None
    activation_target: ActivationTarget | None = None
    activation_kind: ActivationKind = ActivationKind.WORLD_ORCHESTRATION
    activation_version: int = 1
    activation_coalescing_key: str | None = None
    activation_attention: ActivationAttention = ActivationAttention.NONE

    def __post_init__(self) -> None:
        require_type(self.request_id, RequestId, "request_id")
        require_type(self.trigger_id, TriggerId, "trigger_id")
        require_type(self.world_id, WorldId, "world_id")
        if self.trigger_id.world_id != self.world_id:
            raise DomainInvariantError("trigger belongs to a different world")
        require_type(self.due_at, WorldTime, "due_at")
        require_type(self.priority, TriggerPriority, "priority")
        require_type(self.payload, SimulationPayload, "payload")
        target = self.activation_target or ActivationTarget.world(self.world_id)
        require_type(target, ActivationTarget, "activation_target")
        if target.world_id != self.world_id:
            raise DomainInvariantError("activation target belongs to a different world")
        object.__setattr__(self, "activation_target", target)
        require_type(self.activation_kind, ActivationKind, "activation_kind")
        validate_activation_contract(self.activation_kind, self.activation_version)
        validate_coalescing_key(self.activation_coalescing_key)
        require_type(self.activation_attention, ActivationAttention, "activation_attention")
        if self.activation_attention is ActivationAttention.ACTIVE and target.character_id is None:
            raise DomainInvariantError("ACTIVE attention is valid only for Character targets")
        if self.correlation_id is not None:
            require_type(self.correlation_id, CorrelationId, "correlation_id")


@dataclass(frozen=True, slots=True)
class ScheduleResult:
    trigger: ScheduledSimulationTrigger
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class DrainResult:
    activations: tuple[SimulationActivation, ...]
    more_due: bool

    @property
    def processed_count(self) -> int:
        return len(self.activations)

    @property
    def last_due_at(self) -> WorldTime | None:
        return self.activations[-1].due_at if self.activations else None


class SimulationSchedulerStore(Protocol):
    async def schedule(
        self, request: ScheduleTrigger, fingerprint: str, created_at_utc
    ) -> ScheduleResult: ...
    async def cancel(
        self, trigger_id: TriggerId, cancelled_at_utc
    ) -> ScheduledSimulationTrigger: ...
    async def get(self, trigger_id: TriggerId) -> ScheduledSimulationTrigger | None: ...
    async def peek_next(self, world_id: WorldId) -> ScheduledSimulationTrigger | None: ...
    async def list_due(
        self, world_id: WorldId, through: WorldTime, max_items: int
    ) -> tuple[ScheduledSimulationTrigger, ...]: ...
    async def drain_due(
        self, world_id: WorldId, through: WorldTime, max_items: int, materialized_at_utc
    ) -> DrainResult: ...
    async def world(self, world_id: WorldId) -> World | None: ...


class SchedulerWakeSignal:
    """Process-local control signal. SQLite remains the queue authority."""

    def __init__(self) -> None:
        self._events: dict[WorldId, asyncio.Event] = {}
        self._activator: Callable[[WorldId], None] | None = None

    def bind_activator(self, activator: Callable[[WorldId], None]) -> None:
        self._activator = activator

    def event(self, world_id: WorldId) -> asyncio.Event:
        return self._events.setdefault(world_id, asyncio.Event())

    def wake(self, world_id: WorldId) -> None:
        if self._activator is not None:
            self._activator(world_id)
        self.event(world_id).set()


def schedule_fingerprint(request: ScheduleTrigger) -> str:
    value: dict[str, object] = {
        "fingerprint_version": 1,
        "operation": "ScheduleSimulationTrigger",
        "world_id": id_input(request.world_id),
        "trigger_id": id_input(request.trigger_id),
        "due_at": request.due_at.microseconds,
        "priority": int(request.priority),
        "kind": request.kind,
        "payload_version": request.payload_version,
        "payload": request.payload.data,
        "correlation_id": str(request.correlation_id.value) if request.correlation_id else None,
        "activation_target": {
            "kind": request.activation_target.kind.value,
            "character_id": (
                id_input(request.activation_target.character_id)
                if request.activation_target.character_id is not None
                else None
            ),
        },
        "activation_kind": request.activation_kind.value,
        "activation_version": request.activation_version,
        "activation_coalescing_key": request.activation_coalescing_key,
        "activation_attention": request.activation_attention.value,
    }
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


class SimulationScheduler:
    def __init__(
        self,
        store: SimulationSchedulerStore,
        clock: WallClock,
        wake_signal: SchedulerWakeSignal,
    ) -> None:
        self._store = store
        self._clock = clock
        self._wake_signal = wake_signal

    async def schedule_trigger(self, request: ScheduleTrigger) -> ScheduleResult:
        result = await self._store.schedule(
            request, schedule_fingerprint(request), self._clock.now_utc()
        )
        self._wake_signal.wake(request.world_id)
        return result

    async def cancel_trigger(self, trigger_id: TriggerId) -> ScheduledSimulationTrigger:
        trigger = await self._store.cancel(trigger_id, self._clock.now_utc())
        self._wake_signal.wake(trigger_id.world_id)
        return trigger

    async def get_trigger(self, trigger_id: TriggerId) -> ScheduledSimulationTrigger | None:
        return await self._store.get(trigger_id)

    async def peek_next(self, world_id: WorldId) -> ScheduledSimulationTrigger | None:
        return await self._store.peek_next(world_id)

    async def list_due(
        self, world_id: WorldId, through_world_time: WorldTime, max_items: int
    ) -> tuple[ScheduledSimulationTrigger, ...]:
        _positive_batch(max_items)
        return await self._store.list_due(world_id, through_world_time, max_items)

    async def materialize_due(
        self, world_id: WorldId, through_world_time: WorldTime, max_items: int
    ) -> DrainResult:
        _positive_batch(max_items)
        return await self._store.drain_due(
            world_id, through_world_time, max_items, self._clock.now_utc()
        )

    async def drain_due(
        self, world_id: WorldId, through_world_time: WorldTime, max_items: int
    ) -> DrainResult:
        return await self.materialize_due(world_id, through_world_time, max_items)

    async def world(self, world_id: WorldId) -> World | None:
        return await self._store.world(world_id)


def _positive_batch(max_items: int) -> None:
    if type(max_items) is not int or max_items <= 0:
        raise DomainInvariantError("max_items must be a positive integer")


@dataclass(frozen=True, slots=True)
class SchedulerDiagnostic:
    event: str
    world_id: WorldId
    scheduler_state: str
    trigger_kind: str | None = None
    due_at: WorldTime | None = None
    queue_lag_microseconds: int | None = None
    batch_size: int | None = None
    activation_count: int | None = None


class SchedulerDiagnosticSink(Protocol):
    def emit(self, diagnostic: SchedulerDiagnostic) -> None: ...


class NullSchedulerDiagnosticSink:
    def emit(self, diagnostic: SchedulerDiagnostic) -> None:
        pass


class SimulationSchedulerRuntime:
    """One interruptible tickless task per explicitly active world."""

    def __init__(
        self,
        scheduler: SimulationScheduler,
        time_source: EffectiveWorldTimeSource,
        wake_signal: SchedulerWakeSignal,
        *,
        max_batch: int = 128,
        diagnostics: SchedulerDiagnosticSink | None = None,
    ) -> None:
        _positive_batch(max_batch)
        self._scheduler = scheduler
        self._time_source = time_source
        self._wake_signal = wake_signal
        self._max_batch = max_batch
        self._diagnostics = diagnostics or NullSchedulerDiagnosticSink()
        self._tasks: dict[WorldId, asyncio.Task[None]] = {}
        self._closing = False
        wake_signal.bind_activator(self.activate_world)

    @property
    def active_task_count(self) -> int:
        return len(self._tasks)

    def activate_world(self, world_id: WorldId) -> None:
        if self._closing or world_id in self._tasks:
            return
        self._tasks[world_id] = asyncio.create_task(self._run_world(world_id))

    def clock_changed(self, world_id: WorldId) -> None:
        self._time_source.invalidate(world_id)
        self._wake_signal.wake(world_id)

    def clock_reanchored(self, world_id: WorldId) -> None:
        """Wake after the shared clock service has already installed the new base."""

        self._wake_signal.wake(world_id)

    async def aclose(self) -> None:
        self._closing = True
        for world_id in tuple(self._tasks):
            self._wake_signal.event(world_id).set()
        tasks = tuple(self._tasks.values())
        if tasks:
            await asyncio.gather(*tasks)
        self._tasks.clear()

    async def _run_world(self, world_id: WorldId) -> None:
        wake = self._wake_signal.event(world_id)
        try:
            while not self._closing:
                wake.clear()
                world = await self._scheduler.world(world_id)
                if world is None:
                    return
                now = self._time_source.read(world.clock)
                result = await self._scheduler.drain_due(world_id, now, self._max_batch)
                if result.processed_count:
                    last = result.activations[-1]
                    self._diagnostics.emit(
                        SchedulerDiagnostic(
                            "scheduler_batch_materialized",
                            world_id,
                            "running",
                            trigger_kind=last.kind,
                            due_at=last.due_at,
                            queue_lag_microseconds=max(
                                0, now.microseconds - last.due_at.microseconds
                            ),
                            batch_size=self._max_batch,
                            activation_count=result.processed_count,
                        )
                    )
                    if result.more_due:
                        await asyncio.sleep(0)
                        continue
                next_trigger = await self._scheduler.peek_next(world_id)
                if (
                    next_trigger is None
                    or world.clock.state is ClockState.PAUSED
                    or world.clock.time_scale == 0
                ):
                    await wake.wait()
                    continue
                delay = wall_delay_seconds(now, next_trigger.due_at, world.clock.time_scale)
                if delay is None:
                    await wake.wait()
                    continue
                try:
                    await asyncio.wait_for(wake.wait(), timeout=delay)
                except TimeoutError:
                    pass
        finally:
            self._tasks.pop(world_id, None)
