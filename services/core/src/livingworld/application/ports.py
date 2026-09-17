"""Focused application capabilities implemented by infrastructure."""

from datetime import datetime
from typing import Protocol, Self

from livingworld.application.ledger import CanonicalEvent
from livingworld.application.projections import ProjectionSnapshot
from livingworld.application.results import CommandResult
from livingworld.domain.commands import CommandReceipt
from livingworld.domain.contracts import RequestId
from livingworld.domain.events import WorldEvent
from livingworld.domain.identifiers import (
    CharacterId,
    EventId,
    KnowledgeAssertionId,
    LocationId,
    PlayerId,
    PrincipalId,
    WorldId,
)
from livingworld.domain.knowledge import KnowledgeAssertion, Observation
from livingworld.domain.participants import Character, CharacterState, Player, PlayerPresence
from livingworld.domain.relationships import Relationship
from livingworld.domain.values import Revision
from livingworld.domain.world import Location, World


class WallClock(Protocol):
    def now_utc(self) -> datetime: ...


class WorldRepository(Protocol):
    async def get(self, world_id: WorldId) -> World | None: ...
    async def add(self, world: World) -> None: ...


class LocationRepository(Protocol):
    async def get(self, location_id: LocationId) -> Location | None: ...
    async def add(self, location: Location) -> None: ...


class PlayerRepository(Protocol):
    async def get(self, player_id: PlayerId) -> Player | None: ...
    async def presence(self, player_id: PlayerId) -> PlayerPresence | None: ...
    async def add(self, player: Player, presence: PlayerPresence) -> None: ...
    async def replace_presence(
        self, presence: PlayerPresence, expected_revision: Revision
    ) -> None: ...


class CharacterRepository(Protocol):
    async def get(self, character_id: CharacterId) -> Character | None: ...
    async def state(self, character_id: CharacterId) -> CharacterState | None: ...
    async def add(self, character: Character) -> None: ...
    async def put_state(
        self, state: CharacterState, expected_revision: Revision | None
    ) -> None: ...


class RelationshipRepository(Protocol):
    async def get(self, source: PrincipalId, target: PrincipalId) -> Relationship | None: ...
    async def put(self, relationship: Relationship, expected_revision: Revision | None) -> None: ...


class EventAppender(Protocol):
    async def append(self, event: WorldEvent) -> None: ...


class EventReferenceReader(Protocol):
    """Trusted exact-reference validation; no global ledger/knowledge query capability."""

    async def exists(self, event_id: EventId) -> bool: ...


class WorldTruthReader(Protocol):
    """Bound world, truth only; trusted world layer capability."""

    async def get(self, assertion_id: KnowledgeAssertionId) -> KnowledgeAssertion | None: ...
    async def list(self) -> tuple[KnowledgeAssertion, ...]: ...


class CharacterKnowledgeReader(Protocol):
    """Bound character, own beliefs only; no source traversal."""

    async def get(self, assertion_id: KnowledgeAssertionId) -> KnowledgeAssertion | None: ...
    async def list(self) -> tuple[KnowledgeAssertion, ...]: ...


class PlayerKnowledgeReader(Protocol):
    """Bound player, own knowledge only."""

    async def get(self, assertion_id: KnowledgeAssertionId) -> KnowledgeAssertion | None: ...
    async def list(self) -> tuple[KnowledgeAssertion, ...]: ...


class KnowledgeMutationRepository(Protocol):
    """Internal exact-source capability, only supplied to authoritative commands."""

    async def get(self, assertion_id: KnowledgeAssertionId) -> KnowledgeAssertion | None: ...
    async def add(self, assertion: KnowledgeAssertion) -> None: ...


class ObservationAppender(Protocol):
    async def add(self, observation: Observation) -> None: ...


class CommandReceiptRepository(Protocol):
    async def existing(self, request_id: RequestId, fingerprint: str) -> CommandResult | None: ...
    async def add(
        self, receipt: CommandReceipt, fingerprint: str, result: CommandResult
    ) -> None: ...


class UnitOfWork(Protocol):
    worlds: WorldRepository
    locations: LocationRepository
    players: PlayerRepository
    characters: CharacterRepository
    relationships: RelationshipRepository
    knowledge: KnowledgeMutationRepository
    observations: ObservationAppender
    events: EventAppender
    event_references: EventReferenceReader
    receipts: CommandReceiptRepository

    async def __aenter__(self) -> Self: ...
    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None: ...
    async def commit(self) -> None: ...


class CanonicalEventReader(Protocol):
    """Bound world; infrastructure returns strictly ordered immutable ledger entries."""

    async def read(self) -> tuple[CanonicalEvent, ...]: ...


class ProjectionRebuildUnitOfWork(Protocol):
    """One world's rebuild, with no event or receipt mutation capability."""

    ledger: CanonicalEventReader

    async def __aenter__(self) -> Self: ...
    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None: ...
    async def clear(self) -> None: ...
    async def replace(self, snapshot: ProjectionSnapshot) -> None: ...
    async def validate(self) -> None: ...
    async def commit(self) -> None: ...
