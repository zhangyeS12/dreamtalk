from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from livingworld.application.simulation_clock import EffectiveWorldTimeSource, wall_delay_seconds
from livingworld.domain.errors import DomainInvariantError
from livingworld.domain.identifiers import WorldId
from livingworld.domain.simulation import SimulationPayload
from livingworld.domain.values import WorldTime
from livingworld.domain.world import ClockState, WorldClock


class MutableWallClock:
    def __init__(self, value):
        self.value = value

    def now_utc(self):
        return self.value


class MutableMonotonicClock:
    def __init__(self, value=0):
        self.value = value

    def now_ns(self):
        return self.value


def clock(*, state=ClockState.RUNNING, scale=Decimal("1")):
    world = WorldId(uuid4())
    anchor = datetime(2026, 9, 19, 12, tzinfo=UTC)
    return WorldClock(world, WorldTime(10), anchor, scale, state), anchor


def test_effective_world_time_is_exact_and_side_effect_free():
    value, anchor = clock(scale=Decimal("1.234567890123456789"))
    before = value
    elapsed = 1_000_001
    result = value.effective_time(anchor + timedelta(microseconds=elapsed))
    expected = int(Decimal(elapsed) * value.time_scale)
    assert result == WorldTime(10 + expected)
    assert value == before


def test_paused_and_zero_scale_clock_remain_at_anchor():
    paused, anchor = clock(state=ClockState.PAUSED, scale=Decimal("999"))
    zero, zero_anchor = clock(scale=Decimal("0"))
    assert paused.effective_time(anchor + timedelta(days=99)) == WorldTime(10)
    assert zero.effective_time(zero_anchor + timedelta(days=99)) == WorldTime(10)


def test_monotonic_guard_ignores_wall_clock_rollback_after_initial_anchor():
    value, anchor = clock(scale=Decimal("2"))
    wall = MutableWallClock(anchor + timedelta(seconds=10))
    monotonic = MutableMonotonicClock(1_000_000_000)
    source = EffectiveWorldTimeSource(wall, monotonic)
    assert source.read(value) == WorldTime(20_000_010)
    wall.value = anchor - timedelta(days=1)
    monotonic.value += 2_000_000_000
    assert source.read(value) == WorldTime(24_000_010)


def test_wall_delay_is_only_an_approximation_and_zero_scale_waits_for_signal():
    assert wall_delay_seconds(WorldTime(10), WorldTime(2_000_010), Decimal("2")) == 1.0
    assert wall_delay_seconds(WorldTime(10), WorldTime(20), Decimal("0")) is None


def test_payload_is_json_safe_immutable_and_bounded():
    source = {"nested": ["value"]}
    payload = SimulationPayload(source)
    source["nested"].append("changed")
    assert payload.data["nested"] == ("value",)
    with pytest.raises(DomainInvariantError, match="bounded"):
        SimulationPayload({"value": "x" * 17_000})
    with pytest.raises(DomainInvariantError):
        SimulationPayload({"bad": object()})
