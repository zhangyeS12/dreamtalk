"""Exact WorldTime derivation with a process-local monotonic safety guard."""

from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal
from time import monotonic_ns
from typing import Protocol

from livingworld.application.ports import WallClock
from livingworld.domain.identifiers import WorldId
from livingworld.domain.values import WorldTime
from livingworld.domain.world import ClockState, WorldClock


class MonotonicClock(Protocol):
    def now_ns(self) -> int: ...


class SystemMonotonicClock:
    def now_ns(self) -> int:
        return monotonic_ns()


@dataclass(slots=True)
class _Reading:
    revision: int
    persisted_anchor: WorldTime
    effective: WorldTime
    monotonic_ns: int


class EffectiveWorldTimeSource:
    """UTC establishes a revision anchor; monotonic elapsed time advances it in-process."""

    def __init__(self, wall_clock: WallClock, monotonic_clock: MonotonicClock) -> None:
        self._wall_clock = wall_clock
        self._monotonic_clock = monotonic_clock
        self._readings: dict[WorldId, _Reading] = {}

    def read(self, clock: WorldClock) -> WorldTime:
        sample_ns = self._monotonic_clock.now_ns()
        previous = self._readings.get(clock.world_id)
        if (
            previous is None
            or previous.revision != clock.revision.value
            or previous.persisted_anchor != clock.logical_time
        ):
            effective = clock.effective_time(self._wall_clock.now_utc())
        elif clock.state is ClockState.PAUSED or clock.time_scale == 0:
            effective = clock.logical_time
        else:
            elapsed_ns = max(0, sample_ns - previous.monotonic_ns)
            scaled_microseconds = (
                Decimal(elapsed_ns) * clock.time_scale / Decimal(1_000)
            ).to_integral_value(rounding=ROUND_FLOOR)
            effective = WorldTime(previous.effective.microseconds + int(scaled_microseconds))
            if effective < previous.effective:
                effective = previous.effective
        self._readings[clock.world_id] = _Reading(
            clock.revision.value, clock.logical_time, effective, sample_ns
        )
        return effective

    def invalidate(self, world_id: WorldId) -> None:
        self._readings.pop(world_id, None)


def wall_delay_seconds(now: WorldTime, due_at: WorldTime, scale: Decimal) -> float | None:
    """Return an approximate sleep duration; callers must re-read after waking."""

    if scale <= 0:
        return None
    remaining = max(0, due_at.microseconds - now.microseconds)
    seconds = Decimal(remaining) / scale / Decimal(1_000_000)
    return float(seconds)
