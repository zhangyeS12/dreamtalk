"""Immutable model settings selected by the actual world, never UI selection."""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from uuid import UUID

from livingworld.domain.identifiers import WorldId


@dataclass(frozen=True, slots=True)
class WorldModelValue[T]:
    default: T
    worlds: Mapping[WorldId, T]

    def __post_init__(self):
        object.__setattr__(self, "worlds", MappingProxyType(dict(self.worlds)))

    def for_world(self, world: WorldId | UUID | None) -> T:
        identity = WorldId(world) if isinstance(world, UUID) else world
        return self.worlds.get(identity, self.default)


def model_for_world[T](value: T | WorldModelValue[T], world: WorldId | UUID | None) -> T:
    return value.for_world(world) if isinstance(value, WorldModelValue) else value


def any_model_available(value) -> bool:
    values = (
        (value.default, *value.worlds.values()) if isinstance(value, WorldModelValue) else (value,)
    )
    return any(configured is not None and configured[4]() for configured in values)
