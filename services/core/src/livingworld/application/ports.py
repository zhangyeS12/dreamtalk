"""Focused application capabilities implemented by infrastructure."""

from datetime import datetime
from typing import Protocol, Self

from livingworld.application.ledger import CanonicalEvent
from livingworld.application.projections import ProjectionSnapshot
from livingworld.application.results import ActionResult, CommandResult, SceneResult
from livingworld.domain.commands import CommandReceipt
from livingworld.domain.contracts import RequestId
from livingworld.domain.events import WorldEvent
from livingworld.domain.identifiers import (
    ActivationId,
    CharacterId,
    EventId,
    KnowledgeAssertionId,
    LocationId,
    PlayerId,
    PrincipalId,
    SceneId,
    WorldId,
)
from livingworld.domain.knowledge import KnowledgeAssertion, Observation
from livingworld.domain.participants import Character, CharacterState, Player, PlayerPresence
from livingworld.domain.relationships import Relationship
from livingworld.domain.scenes import Scene, SceneParticipant
from livingworld.domain.simulation import (
    ActivationCandidate,
    ActivationCausePage,
    ActivationRequest,
    ActivationRequestResult,
)
from livingworld.domain.values import Revision, WorldTime
from livingworld.domain.world import Location, World, WorldClock


class WallClock(Protocol):
    def now_utc(self) -> datetime: ...


class WorldTimeSource(Protocol):
    def read(self, clock: WorldClock) -> WorldTime: ...


class TemporalMutationBarrier(Protocol):
    async def assert_mutation_allowed(self, world_id: WorldId) -> None: ...


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
    async def at_location(self, location_id: LocationId) -> tuple[PlayerId, ...]: ...


class CharacterRepository(Protocol):
    async def get(self, character_id: CharacterId) -> Character | None: ...
    async def state(self, character_id: CharacterId) -> CharacterState | None: ...
    async def add(self, character: Character) -> None: ...
    async def put_state(
        self, state: CharacterState, expected_revision: Revision | None
    ) -> None: ...
    async def at_location(self, location_id: LocationId) -> tuple[CharacterId, ...]: ...


class SceneRepository(Protocol):
    async def get(self, scene_id: SceneId) -> Scene | None: ...
    async def add(self, scene: Scene, participants: tuple[SceneParticipant, ...]) -> None: ...
    async def replace(self, scene: Scene, expected_revision: Revision) -> None: ...
    async def active_participants(self, scene_id: SceneId) -> tuple[SceneParticipant, ...]: ...
    async def active_for_principal(self, principal_id: PrincipalId) -> SceneParticipant | None: ...
    async def active_characters_bounded(
        self, scene_id: SceneId, limit: int
    ) -> tuple[tuple[CharacterId, ...], bool]: ...
    async def add_participant(self, participant: SceneParticipant) -> None: ...
    async def leave_participant(self, participant: SceneParticipant) -> None: ...
    async def leave_all(self, scene_id: SceneId, left_at: WorldTime) -> None: ...
    async def leave_active_for_principal(
        self, principal_id: PrincipalId, left_at: WorldTime
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
    async def has_event_access(self, character_id: CharacterId, event_id: EventId) -> bool: ...


class ActivationRepository(Protocol):
    async def request(
        self, request: ActivationRequest, fingerprint: str, materialized_at_utc: datetime
    ) -> ActivationRequestResult: ...
    async def list_due_candidates(
        self, world_id: WorldId, through: WorldTime, max_items: int
    ) -> tuple[ActivationCandidate, ...]: ...
    async def causes(
        self, activation_id: ActivationId, limit: int, offset: int = 0
    ) -> ActivationCausePage: ...


class CommandReceiptRepository(Protocol):
    async def existing(self, request_id: RequestId, fingerprint: str) -> CommandResult | None: ...
    async def add(
        self, receipt: CommandReceipt, fingerprint: str, result: CommandResult
    ) -> None: ...
    async def existing_action(
        self, request_id: RequestId, fingerprint: str
    ) -> ActionResult | None: ...
    async def add_action(
        self, receipt: CommandReceipt, fingerprint: str, result: ActionResult
    ) -> None: ...
    async def existing_scene(
        self, request_id: RequestId, fingerprint: str
    ) -> SceneResult | None: ...
    async def add_scene(
        self, receipt: CommandReceipt, fingerprint: str, result: SceneResult
    ) -> None: ...


class UnitOfWork(Protocol):
    worlds: WorldRepository
    locations: LocationRepository
    players: PlayerRepository
    characters: CharacterRepository
    relationships: RelationshipRepository
    scenes: SceneRepository
    knowledge: KnowledgeMutationRepository
    observations: ObservationAppender
    activations: ActivationRepository
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
