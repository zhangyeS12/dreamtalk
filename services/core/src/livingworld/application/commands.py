"""Resolved semantic inputs for the authoritative command pipeline."""

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from livingworld.domain.contracts import RequestId
from livingworld.domain.errors import DomainInvariantError
from livingworld.domain.identifiers import (
    CharacterId,
    EventId,
    KnowledgeAssertionId,
    LocationId,
    PlayerId,
    PrincipalId,
    WorldId,
)
from livingworld.domain.knowledge import ObservationChannel
from livingworld.domain.participants import PlayerActivity, PlayerAvailability
from livingworld.domain.values import (
    JsonValue,
    Revision,
    WorldTime,
    freeze_json,
    require_text,
    require_type,
    same_world,
)
from livingworld.domain.world import ClockState


@dataclass(frozen=True, slots=True, kw_only=True)
class Command:
    request_id: RequestId
    world_id: WorldId

    def __post_init__(self) -> None:
        require_type(self.request_id, RequestId, "request_id")
        require_type(self.request_id.value, UUID, "request_id value")
        require_type(self.world_id, WorldId, "world_id")
        if isinstance(self, (CreateWorld, CreateLocation, CreatePlayer, CreateCharacter)):
            require_text(self.name, "name")
        match self:
            case CreateWorld():
                require_type(self.initial_time, WorldTime, "initial_time")
                require_type(self.time_scale, Decimal, "time_scale")
                require_type(self.clock_state, ClockState, "clock_state")
            case CreateLocation():
                require_type(self.location_id, LocationId, "location_id")
                require_type(self.list_locally, bool, "list_locally")
                same_world(self.world_id, self.location_id)
            case CreatePlayer():
                require_type(self.player_id, PlayerId, "player_id")
                require_type(self.initial_location_id, LocationId, "initial_location_id")
                same_world(self.world_id, self.player_id, self.initial_location_id)
                require_type(self.activity_state, PlayerActivity, "activity_state")
                require_type(self.availability_state, PlayerAvailability, "availability_state")
            case MovePlayer():
                require_type(
                    self.expected_presence_revision, Revision, "expected_presence_revision"
                )
                require_type(self.player_id, PlayerId, "player_id")
                require_type(self.destination_id, LocationId, "destination_id")
                same_world(self.world_id, self.player_id, self.destination_id)
            case SetPlayerAvailability():
                require_type(
                    self.expected_presence_revision, Revision, "expected_presence_revision"
                )
                require_type(self.player_id, PlayerId, "player_id")
                require_type(self.availability_state, PlayerAvailability, "availability_state")
                same_world(self.world_id, self.player_id)
            case CreateCharacter():
                require_type(self.character_id, CharacterId, "character_id")
                same_world(self.world_id, self.character_id)
            case PlaceCharacter():
                _optional_revision(self.expected_state_revision)
                require_type(self.character_id, CharacterId, "character_id")
                require_type(self.location_id, LocationId, "location_id")
                same_world(self.world_id, self.character_id, self.location_id)
            case ChangeRelationship():
                _optional_revision(self.expected_relationship_revision)
                require_type(self.source_id, (CharacterId, PlayerId), "source_id")
                require_type(self.target_id, (CharacterId, PlayerId), "target_id")
                same_world(self.world_id, self.source_id, self.target_id)
                if any(
                    type(value) is not int
                    for value in (self.affinity_delta, self.trust_delta, self.familiarity_delta)
                ):
                    raise DomainInvariantError("Relationship deltas require integers")
            case AssertWorldTruth() | FormCharacterBelief():
                require_type(self.assertion_id, KnowledgeAssertionId, "assertion_id")
                same_world(self.world_id, self.assertion_id)
                require_text(self.subject, "subject")
                require_text(self.predicate, "predicate")
                object.__setattr__(self, "value", freeze_json(self.value))
                if self.valid_from is not None:
                    require_type(self.valid_from, WorldTime, "valid_from")
                if self.valid_to is not None:
                    require_type(self.valid_to, WorldTime, "valid_to")
                _epistemic_metadata(self.epistemic_status, self.confidence)
                if isinstance(self, FormCharacterBelief):
                    require_type(self.character_id, CharacterId, "character_id")
                    require_type(self.valid_from, WorldTime, "valid_from")
                    same_world(self.world_id, self.character_id)
                    for identity, kind in (
                        (self.source_assertion_id, KnowledgeAssertionId),
                        (self.provenance_event_id, EventId),
                    ):
                        if identity is not None:
                            require_type(identity, kind, "belief reference")
                            same_world(self.world_id, identity)
            case AcquireKnowledge():
                require_type(self.assertion_id, KnowledgeAssertionId, "assertion_id")
                require_type(self.source_assertion_id, KnowledgeAssertionId, "source_assertion_id")
                require_type(self.receiver_id, (CharacterId, PlayerId), "receiver_id")
                same_world(
                    self.world_id, self.assertion_id, self.source_assertion_id, self.receiver_id
                )
                require_type(self.channel, ObservationChannel, "channel")
                if self.epistemic_status is None:
                    object.__setattr__(
                        self,
                        "epistemic_status",
                        "observed" if self.channel is ObservationChannel.WITNESSED else "reported",
                    )
                _epistemic_metadata(self.epistemic_status, self.confidence)


def _optional_revision(value: Revision | None) -> None:
    if value is not None:
        require_type(value, Revision, "expected_revision")


def _epistemic_metadata(status: str, confidence: Decimal | None) -> None:
    require_text(status, "epistemic_status")
    if confidence is not None:
        require_type(confidence, Decimal, "confidence")
        if not confidence.is_finite() or not 0 <= confidence <= 1:
            raise DomainInvariantError("confidence must be finite and between zero and one")


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateWorld(Command):
    name: str
    initial_time: WorldTime = WorldTime(0)
    time_scale: Decimal = Decimal(1)
    clock_state: ClockState = ClockState.RUNNING


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateLocation(Command):
    location_id: LocationId
    name: str
    list_locally: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class CreatePlayer(Command):
    player_id: PlayerId
    name: str
    initial_location_id: LocationId
    activity_state: PlayerActivity = PlayerActivity.ACTIVE
    availability_state: PlayerAvailability = PlayerAvailability.AVAILABLE


@dataclass(frozen=True, slots=True, kw_only=True)
class MovePlayer(Command):
    player_id: PlayerId
    destination_id: LocationId
    expected_presence_revision: Revision


@dataclass(frozen=True, slots=True, kw_only=True)
class SetPlayerAvailability(Command):
    player_id: PlayerId
    availability_state: PlayerAvailability
    expected_presence_revision: Revision


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateCharacter(Command):
    character_id: CharacterId
    name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class PlaceCharacter(Command):
    character_id: CharacterId
    location_id: LocationId
    expected_state_revision: Revision | None


@dataclass(frozen=True, slots=True, kw_only=True)
class ChangeRelationship(Command):
    source_id: PrincipalId
    target_id: PrincipalId
    expected_relationship_revision: Revision | None
    affinity_delta: int = 0
    trust_delta: int = 0
    familiarity_delta: int = 0


@dataclass(frozen=True, slots=True, kw_only=True)
class AssertWorldTruth(Command):
    """Trusted internal creation; no public/player truth-write capability."""

    assertion_id: KnowledgeAssertionId
    subject: str
    predicate: str
    value: JsonValue
    epistemic_status: str = "asserted"
    confidence: Decimal | None = None
    valid_from: WorldTime | None = None
    valid_to: WorldTime | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class FormCharacterBelief(Command):
    """Internal subjective assertion creation; neither truth nor channel exposure."""

    assertion_id: KnowledgeAssertionId
    character_id: CharacterId
    subject: str
    predicate: str
    value: JsonValue
    epistemic_status: str
    valid_from: WorldTime
    confidence: Decimal | None = None
    valid_to: WorldTime | None = None
    source_assertion_id: KnowledgeAssertionId | None = None
    provenance_event_id: EventId | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class AcquireKnowledge(Command):
    """Trusted evidence-channel execution, not a principal self-grant API."""

    assertion_id: KnowledgeAssertionId
    receiver_id: PrincipalId
    source_assertion_id: KnowledgeAssertionId
    channel: ObservationChannel
    epistemic_status: str | None = None
    confidence: Decimal | None = None


type WorldCommand = (
    CreateWorld
    | CreateLocation
    | CreatePlayer
    | MovePlayer
    | SetPlayerAvailability
    | CreateCharacter
    | PlaceCharacter
    | ChangeRelationship
    | AssertWorldTruth
    | FormCharacterBelief
    | AcquireKnowledge
)
