"""Exact WorldTime derivation from one process-local monotonic base."""

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
    signature: tuple[object, ...]
    runtime_base: WorldTime
    monotonic_base_ns: int
    last_effective: WorldTime


class EffectiveWorldTimeSource:
    """UTC establishes a revision anchor; monotonic elapsed time advances it in-process."""

    def __init__(self, wall_clock: WallClock, monotonic_clock: MonotonicClock) -> None:
        self._wall_clock = wall_clock
        self._monotonic_clock = monotonic_clock
        self._readings: dict[WorldId, _Reading] = {}

    def read(self, clock: WorldClock) -> WorldTime:
        sample_ns = self._monotonic_clock.now_ns()
        previous = self._readings.get(clock.world_id)
        signature = self._signature(clock)
        if previous is None or previous.signature != signature:
            effective = clock.effective_time(self._wall_clock.now_utc())
            self._readings[clock.world_id] = _Reading(signature, effective, sample_ns, effective)
            return effective
        elif clock.state is ClockState.PAUSED or clock.time_scale == 0:
            effective = previous.runtime_base
        else:
            # Always derive from the original base. Repeated reads therefore do not
            # discard fractional microseconds and cannot accumulate rounding drift.
            elapsed_ns = max(0, sample_ns - previous.monotonic_base_ns)
            scaled_microseconds = (
                Decimal(elapsed_ns) * clock.time_scale / Decimal(1_000)
            ).to_integral_value(rounding=ROUND_FLOOR)
            effective = WorldTime(previous.runtime_base.microseconds + int(scaled_microseconds))
            if effective < previous.last_effective:
                effective = previous.last_effective
        previous.last_effective = effective
        return effective

    def establish(self, clock: WorldClock, at: WorldTime | None = None) -> None:
        """Install an explicit in-process base without consulting mutable wall UTC."""

        effective = at if at is not None else clock.logical_time
        self._readings[clock.world_id] = _Reading(
            self._signature(clock),
            effective,
            self._monotonic_clock.now_ns(),
            effective,
        )

    def invalidate(self, world_id: WorldId) -> None:
        self._readings.pop(world_id, None)

    @staticmethod
    def _signature(clock: WorldClock) -> tuple[object, ...]:
        return (
            clock.revision.value,
            clock.logical_time,
            clock.observed_wall_time_utc,
            clock.time_scale,
            clock.state,
        )


def wall_delay_seconds(now: WorldTime, due_at: WorldTime, scale: Decimal) -> float | None:
    """Return an approximate sleep duration; callers must re-read after waking."""

    if scale <= 0:
        return None
    remaining = max(0, due_at.microseconds - now.microseconds)
    seconds = Decimal(remaining) / scale / Decimal(1_000_000)
    return float(seconds)
