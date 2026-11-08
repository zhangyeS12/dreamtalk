"""Concrete identities; world-scoped references carry their isolation boundary."""

from dataclasses import dataclass
from uuid import UUID

from livingworld.domain.errors import DomainInvariantError


def _uuid(value: UUID) -> None:
    if not isinstance(value, UUID):
        raise DomainInvariantError("Identity value must be a UUID")


def _scoped(world_id: "WorldId", value: UUID) -> None:
    if not isinstance(world_id, WorldId):
        raise DomainInvariantError("Identity must belong to a WorldId")
    _uuid(value)


@dataclass(frozen=True, slots=True)
class WorldId:
    value: UUID

    def __post_init__(self) -> None:
        _uuid(self.value)


@dataclass(frozen=True, slots=True)
class LocationId:
    world_id: WorldId
    value: UUID

    def __post_init__(self) -> None:
        _scoped(self.world_id, self.value)


@dataclass(frozen=True, slots=True)
class PlayerId:
    world_id: WorldId
    value: UUID

    def __post_init__(self) -> None:
        _scoped(self.world_id, self.value)


@dataclass(frozen=True, slots=True)
class CharacterId:
    world_id: WorldId
    value: UUID

    def __post_init__(self) -> None:
        _scoped(self.world_id, self.value)


@dataclass(frozen=True, slots=True)
class EventId:
    world_id: WorldId
    value: UUID

    def __post_init__(self) -> None:
        _scoped(self.world_id, self.value)


@dataclass(frozen=True, slots=True)
class KnowledgeAssertionId:
    world_id: WorldId
    value: UUID

    def __post_init__(self) -> None:
        _scoped(self.world_id, self.value)


@dataclass(frozen=True, slots=True)
class ObservationId:
    world_id: WorldId
    value: UUID

    def __post_init__(self) -> None:
        _scoped(self.world_id, self.value)


@dataclass(frozen=True, slots=True)
class MemoryId:
    world_id: WorldId
    value: UUID

    def __post_init__(self) -> None:
        _scoped(self.world_id, self.value)


@dataclass(frozen=True, slots=True)
class ConversationId:
    world_id: WorldId
    value: UUID

    def __post_init__(self) -> None:
        _scoped(self.world_id, self.value)


@dataclass(frozen=True, slots=True)
class ChatTurnId:
    world_id: WorldId
    value: UUID

    def __post_init__(self) -> None:
        _scoped(self.world_id, self.value)


@dataclass(frozen=True, slots=True)
class MessageId:
    world_id: WorldId
    value: UUID

    def __post_init__(self) -> None:
        _scoped(self.world_id, self.value)


@dataclass(frozen=True, slots=True)
class SceneId:
    world_id: WorldId
    value: UUID

    def __post_init__(self) -> None:
        _scoped(self.world_id, self.value)


@dataclass(frozen=True, slots=True)
class SceneParticipantId:
    world_id: WorldId
    value: UUID

    def __post_init__(self) -> None:
        _scoped(self.world_id, self.value)


@dataclass(frozen=True, slots=True)
class TriggerId:
    world_id: WorldId
    value: UUID

    def __post_init__(self) -> None:
        _scoped(self.world_id, self.value)


@dataclass(frozen=True, slots=True)
class ActivationId:
    world_id: WorldId
    value: UUID

    def __post_init__(self) -> None:
        _scoped(self.world_id, self.value)


@dataclass(frozen=True, slots=True)
class CorrelationId:
    """Groups related work; it is neither a world coordinate nor an event identity."""

    value: UUID

    def __post_init__(self) -> None:
        _uuid(self.value)


type PrincipalId = PlayerId | CharacterId
