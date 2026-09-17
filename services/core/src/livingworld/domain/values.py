"""Small validated values shared by domain models, without storage behavior."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from math import isfinite
from types import MappingProxyType

from livingworld.domain.errors import (
    ConcurrencyConflictError,
    CrossWorldReferenceError,
    DomainInvariantError,
)
from livingworld.domain.identifiers import (
    CharacterId,
    EventId,
    KnowledgeAssertionId,
    LocationId,
    ObservationId,
    PlayerId,
    WorldId,
)

type ScopedId = LocationId | PlayerId | CharacterId | EventId | KnowledgeAssertionId | ObservationId
type JsonValue = None | bool | int | float | str | tuple[JsonValue, ...] | Mapping[str, JsonValue]


@dataclass(frozen=True, slots=True, order=True)
class WorldTime:
    """Integer microseconds from a world's logical epoch, independent of UTC.

    A coordinate can precede the epoch. It carries no event, world or branch identity.
    No calendar, conversion, advancement or catch-up operation is defined here.
    """

    microseconds: int

    def __post_init__(self) -> None:
        if type(self.microseconds) is not int:
            raise DomainInvariantError("WorldTime requires integer microseconds")


@dataclass(frozen=True, slots=True, order=True)
class Revision:
    value: int = 0

    def __post_init__(self) -> None:
        if type(self.value) is not int or self.value < 0:
            raise DomainInvariantError("Revision requires a nonnegative integer")

    def advance(self, expected: "Revision") -> "Revision":
        require_type(expected, Revision, "expected_revision")
        if expected != self:
            raise ConcurrencyConflictError("Expected revision does not match current revision")
        return Revision(self.value + 1)


def require_type(value: object, expected: type | tuple[type, ...], field: str) -> None:
    if not isinstance(value, expected):
        raise DomainInvariantError(f"Invalid type for {field}")


def require_text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise DomainInvariantError(f"{field} must be nonempty text")


def same_world(world_id: WorldId, *references: ScopedId) -> None:
    require_type(world_id, WorldId, "world_id")
    for reference in references:
        require_type(
            reference,
            (LocationId, PlayerId, CharacterId, EventId, KnowledgeAssertionId, ObservationId),
            "world-scoped reference",
        )
        if reference.world_id != world_id:
            raise CrossWorldReferenceError("Reference belongs to a different World")


def utc_timestamp(value: datetime, field: str) -> datetime:
    require_type(value, datetime, field)
    if value.tzinfo is None or value.utcoffset() is None:
        raise DomainInvariantError(f"{field} requires a timezone-aware datetime")
    return value.astimezone(UTC)


def freeze_json(value: object) -> JsonValue:
    """Own a defensive immutable copy of a finite JSON value, including nested data."""

    active: set[int] = set()

    def freeze(item: object) -> JsonValue:
        if item is None or type(item) in (bool, int, str):
            return item
        if type(item) is float:
            if not isfinite(item):
                raise DomainInvariantError("JSON numbers must be finite")
            return item
        if not isinstance(item, (Mapping, list, tuple)):
            raise DomainInvariantError("Value must contain only JSON-compatible data")
        if id(item) in active:
            raise DomainInvariantError("JSON data must not contain cycles")
        active.add(id(item))
        try:
            if isinstance(item, Mapping):
                if any(not isinstance(key, str) for key in item):
                    raise DomainInvariantError("JSON object keys must be strings")
                return MappingProxyType({key: freeze(child) for key, child in item.items()})
            return tuple(freeze(child) for child in item)
        finally:
            active.remove(id(item))

    return freeze(value)
