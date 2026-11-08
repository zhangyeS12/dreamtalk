"""Private immutable Character memory with explicit observation provenance."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from livingworld.domain.errors import DomainInvariantError, UnsupportedMemoryKindError
from livingworld.domain.identifiers import CharacterId, MemoryId, ObservationId, WorldId
from livingworld.domain.values import (
    WorldTime,
    require_text,
    require_type,
    same_world,
    utc_timestamp,
)

MAX_EPISODIC_MEMORY_CONTENT_BYTES = 16 * 1024
MAX_EPISODIC_MEMORY_SOURCES = 256
MIN_MEMORY_SALIENCE = 0
MAX_MEMORY_SALIENCE = 100


class MemoryKind(StrEnum):
    EPISODIC = "episodic"
    REFLECTION = "reflection"
    CONSOLIDATED = "consolidated"


class MemoryContentFormat(StrEnum):
    PLAIN_TEXT = "plain_text"


class MemoryProvenanceKind(StrEnum):
    OBSERVATION_EVIDENCE = "observation_evidence"


@dataclass(frozen=True, slots=True, order=True)
class MemorySalience:
    value: int

    def __post_init__(self) -> None:
        if (
            type(self.value) is not int
            or not MIN_MEMORY_SALIENCE <= self.value <= MAX_MEMORY_SALIENCE
        ):
            raise DomainInvariantError("Memory salience must be an integer from 0 through 100")


@dataclass(frozen=True, slots=True)
class EpisodicMemory:
    memory_id: MemoryId
    world_id: WorldId
    owner_character_id: CharacterId
    content: str
    experienced_from: WorldTime
    experienced_to: WorldTime
    formed_at: WorldTime
    created_at_utc: datetime
    source_observation_ids: tuple[ObservationId, ...]
    salience: MemorySalience | None = None
    kind: MemoryKind = MemoryKind.EPISODIC
    kind_version: int = 1
    content_format: MemoryContentFormat = MemoryContentFormat.PLAIN_TEXT
    content_version: int = 1
    provenance_kind: MemoryProvenanceKind = MemoryProvenanceKind.OBSERVATION_EVIDENCE
    provenance_version: int = 1

    def __post_init__(self) -> None:
        require_type(self.memory_id, MemoryId, "memory_id")
        require_type(self.owner_character_id, CharacterId, "owner_character_id")
        same_world(self.world_id, self.memory_id, self.owner_character_id)
        require_type(self.kind, MemoryKind, "memory kind")
        if self.kind is not MemoryKind.EPISODIC or self.kind_version != 1:
            raise UnsupportedMemoryKindError("Unsupported memory kind/version")
        require_type(self.content_format, MemoryContentFormat, "memory content format")
        if self.content_format is not MemoryContentFormat.PLAIN_TEXT or self.content_version != 1:
            raise UnsupportedMemoryKindError("Unsupported memory content format/version")
        require_type(self.provenance_kind, MemoryProvenanceKind, "memory provenance kind")
        if (
            self.provenance_kind is not MemoryProvenanceKind.OBSERVATION_EVIDENCE
            or self.provenance_version != 1
        ):
            raise UnsupportedMemoryKindError("Unsupported memory provenance kind/version")
        require_text(self.content, "memory content")
        if len(self.content.encode("utf-8")) > MAX_EPISODIC_MEMORY_CONTENT_BYTES:
            raise DomainInvariantError("Memory content exceeds the UTF-8 size limit")
        require_type(self.experienced_from, WorldTime, "experienced_from")
        require_type(self.experienced_to, WorldTime, "experienced_to")
        require_type(self.formed_at, WorldTime, "formed_at")
        if self.experienced_to < self.experienced_from:
            raise DomainInvariantError("Memory experience range is reversed")
        if self.formed_at < self.experienced_to:
            raise DomainInvariantError("Memory cannot form before its source experience")
        object.__setattr__(
            self, "created_at_utc", utc_timestamp(self.created_at_utc, "created_at_utc")
        )
        sources = tuple(self.source_observation_ids)
        if not sources:
            raise DomainInvariantError("EpisodicMemory requires Observation evidence")
        if len(sources) > MAX_EPISODIC_MEMORY_SOURCES:
            raise DomainInvariantError("EpisodicMemory has too many Observation sources")
        if len(set(sources)) != len(sources):
            raise DomainInvariantError("EpisodicMemory Observation sources must be unique")
        for source in sources:
            require_type(source, ObservationId, "source_observation_id")
            same_world(self.world_id, source)
        object.__setattr__(self, "source_observation_ids", sources)
        if self.salience is not None:
            require_type(self.salience, MemorySalience, "salience")


@dataclass(frozen=True, slots=True)
class MemoryCursor:
    experienced_to: WorldTime
    formed_at: WorldTime
    memory_id: MemoryId

    def __post_init__(self) -> None:
        require_type(self.experienced_to, WorldTime, "cursor experienced_to")
        require_type(self.formed_at, WorldTime, "cursor formed_at")
        require_type(self.memory_id, MemoryId, "cursor memory_id")


@dataclass(frozen=True, slots=True)
class MemoryPage:
    items: tuple[EpisodicMemory, ...]
    next_cursor: MemoryCursor | None

    def __post_init__(self) -> None:
        if not isinstance(self.items, tuple) or not all(
            isinstance(item, EpisodicMemory) for item in self.items
        ):
            raise DomainInvariantError("MemoryPage items must be EpisodicMemory values")
        if self.next_cursor is not None:
            require_type(self.next_cursor, MemoryCursor, "next_cursor")


@dataclass(frozen=True, slots=True)
class MemoryEvidence:
    observation_id: ObservationId
    observed_at: WorldTime
    source_order: int

    def __post_init__(self) -> None:
        require_type(self.observation_id, ObservationId, "observation_id")
        require_type(self.observed_at, WorldTime, "observed_at")
        if type(self.source_order) is not int or self.source_order < 0:
            raise DomainInvariantError("Memory evidence order must be a nonnegative integer")
