"""World identity, a dual-time clock snapshot and minimum physical topology."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from livingworld.domain.errors import CrossWorldReferenceError, DomainInvariantError
from livingworld.domain.identifiers import LocationId, WorldId
from livingworld.domain.values import (
    Revision,
    WorldTime,
    require_text,
    require_type,
    same_world,
    utc_timestamp,
)


class ClockState(StrEnum):
    RUNNING = "running"
    PAUSED = "paused"


@dataclass(frozen=True, slots=True)
class WorldClock:
    world_id: WorldId
    logical_time: WorldTime
    observed_wall_time_utc: datetime
    time_scale: Decimal
    state: ClockState
    revision: Revision = Revision()

    def __post_init__(self) -> None:
        same_world(self.world_id)
        require_type(self.logical_time, WorldTime, "logical_time")
        require_type(self.time_scale, Decimal, "time_scale")
        if not self.time_scale.is_finite() or self.time_scale < 0:
            raise DomainInvariantError("time_scale must be finite and nonnegative")
        require_type(self.state, ClockState, "clock state")
        require_type(self.revision, Revision, "revision")
        object.__setattr__(
            self,
            "observed_wall_time_utc",
            utc_timestamp(self.observed_wall_time_utc, "observed_wall_time_utc"),
        )


@dataclass(frozen=True, slots=True)
class World:
    world_id: WorldId
    name: str
    clock: WorldClock
    revision: Revision = Revision()

    def __post_init__(self) -> None:
        same_world(self.world_id)
        require_text(self.name, "name")
        require_type(self.clock, WorldClock, "clock")
        if self.clock.world_id != self.world_id:
            raise CrossWorldReferenceError("WorldClock belongs to a different World")
        require_type(self.revision, Revision, "revision")


@dataclass(frozen=True, slots=True)
class Location:
    world_id: WorldId
    location_id: LocationId
    name: str
    revision: Revision = Revision()

    def __post_init__(self) -> None:
        require_type(self.location_id, LocationId, "location_id")
        same_world(self.world_id, self.location_id)
        require_text(self.name, "name")
        require_type(self.revision, Revision, "revision")


@dataclass(frozen=True, slots=True)
class LocationConnection:
    """An ordered topology link; defines no travel permission, duration or simulation."""

    world_id: WorldId
    source_id: LocationId
    target_id: LocationId
    revision: Revision = Revision()

    def __post_init__(self) -> None:
        require_type(self.source_id, LocationId, "source_id")
        require_type(self.target_id, LocationId, "target_id")
        same_world(self.world_id, self.source_id, self.target_id)
        require_type(self.revision, Revision, "revision")
