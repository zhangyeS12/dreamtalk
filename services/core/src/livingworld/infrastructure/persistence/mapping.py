"""Explicit conversion between framework-free domain values and ORM records."""

from uuid import UUID

from livingworld.domain.commands import CommandReceipt
from livingworld.domain.contracts import RequestId
from livingworld.domain.events import WorldEvent
from livingworld.domain.identifiers import (
    CharacterId,
    CorrelationId,
    EventId,
    KnowledgeAssertionId,
    LocationId,
    PlayerId,
    PrincipalId,
    WorldId,
)
from livingworld.domain.knowledge import (
    KnowledgeAssertion,
    KnowledgeScope,
    Observation,
    ObservationChannel,
)
from livingworld.domain.participants import (
    Character,
    CharacterState,
    Player,
    PlayerActivity,
    PlayerAvailability,
    PlayerPresence,
)
from livingworld.domain.relationships import Relationship
from livingworld.domain.values import Revision
from livingworld.domain.world import ClockState, Location, LocationConnection, World, WorldClock
from livingworld.infrastructure.persistence.errors import PersistenceDataError
from livingworld.infrastructure.persistence.models import (
    Base,
    CharacterRecord,
    CharacterStateRecord,
    CommandReceiptRecord,
    KnowledgeAssertionRecord,
    LocationConnectionRecord,
    LocationRecord,
    ObservationRecord,
    PlayerPresenceRecord,
    PlayerRecord,
    RelationshipRecord,
    WorldClockRecord,
    WorldEventRecord,
    WorldRecord,
)

type DomainObject = (
    World
    | WorldClock
    | Location
    | LocationConnection
    | Player
    | PlayerPresence
    | Character
    | CharacterState
    | Relationship
    | WorldEvent
    | KnowledgeAssertion
    | Observation
    | CommandReceipt
)


def _principal_parts(principal: PrincipalId) -> tuple[str, UUID, UUID | None, UUID | None]:
    if isinstance(principal, CharacterId):
        return "character", principal.value, principal.value, None
    if isinstance(principal, PlayerId):
        return "player", principal.value, None, principal.value
    raise PersistenceDataError("principal_id_type_unsupported")


def _principal(world: WorldId, kind: str, value: UUID) -> PrincipalId:
    if kind == "character":
        return CharacterId(world, value)
    if kind == "player":
        return PlayerId(world, value)
    raise PersistenceDataError("stored_principal_kind_invalid")


def _target_parts(
    target: EventId | KnowledgeAssertionId,
) -> tuple[str, UUID, UUID | None, UUID | None]:
    if isinstance(target, EventId):
        return "event", target.value, target.value, None
    if isinstance(target, KnowledgeAssertionId):
        return "assertion", target.value, None, target.value
    raise PersistenceDataError("target_id_type_unsupported")


def _target(world: WorldId, kind: str, value: UUID) -> EventId | KnowledgeAssertionId:
    if kind == "event":
        return EventId(world, value)
    if kind == "assertion":
        return KnowledgeAssertionId(world, value)
    raise PersistenceDataError("stored_target_kind_invalid")


def to_record(entity: DomainObject) -> Base:
    """Map one domain value to a newly owned ORM record without reflection."""

    if isinstance(entity, World):
        return WorldRecord(
            world_id=entity.world_id.value,
            name=entity.name,
            revision=entity.revision.value,
            clock=to_record(entity.clock),
        )
    if isinstance(entity, WorldClock):
        return WorldClockRecord(
            world_id=entity.world_id.value,
            logical_time=entity.logical_time,
            observed_wall_time_utc=entity.observed_wall_time_utc,
            time_scale=entity.time_scale,
            state=entity.state.value,
            revision=entity.revision.value,
        )
    if isinstance(entity, Location):
        return LocationRecord(
            world_id=entity.world_id.value,
            location_id=entity.location_id.value,
            name=entity.name,
            revision=entity.revision.value,
        )
    if isinstance(entity, LocationConnection):
        return LocationConnectionRecord(
            world_id=entity.world_id.value,
            source_id=entity.source_id.value,
            target_id=entity.target_id.value,
            revision=entity.revision.value,
        )
    if isinstance(entity, Player):
        return PlayerRecord(
            world_id=entity.world_id.value,
            player_id=entity.player_id.value,
            name=entity.name,
            revision=entity.revision.value,
        )
    if isinstance(entity, PlayerPresence):
        return PlayerPresenceRecord(
            world_id=entity.world_id.value,
            player_id=entity.player_id.value,
            location_id=entity.location_id.value,
            activity=entity.activity.value,
            availability=entity.availability.value,
            revision=entity.revision.value,
        )
    if isinstance(entity, Character):
        return CharacterRecord(
            world_id=entity.world_id.value,
            character_id=entity.character_id.value,
            name=entity.name,
            revision=entity.revision.value,
        )
    if isinstance(entity, CharacterState):
        return CharacterStateRecord(
            world_id=entity.world_id.value,
            character_id=entity.character_id.value,
            location_id=entity.location_id.value,
            revision=entity.revision.value,
        )
    if isinstance(entity, Relationship):
        source_kind, source_id, source_character, source_player = _principal_parts(entity.source_id)
        target_kind, target_id, target_character, target_player = _principal_parts(entity.target_id)
        return RelationshipRecord(
            world_id=entity.world_id.value,
            source_kind=source_kind,
            source_id=source_id,
            target_kind=target_kind,
            target_id=target_id,
            source_character_id=source_character,
            source_player_id=source_player,
            target_character_id=target_character,
            target_player_id=target_player,
            revision=entity.revision.value,
        )
    if isinstance(entity, WorldEvent):
        cause_event = (
            entity.causation_id.value if isinstance(entity.causation_id, EventId) else None
        )
        cause_request = (
            entity.causation_id.value if isinstance(entity.causation_id, RequestId) else None
        )
        return WorldEventRecord(
            world_id=entity.world_id.value,
            event_id=entity.event_id.value,
            event_type=entity.event_type,
            occurred_at=entity.occurred_at,
            payload=entity.payload,
            payload_version=entity.payload_version,
            causation_event_id=cause_event,
            causation_request_id=cause_request,
            correlation_id=entity.correlation_id.value if entity.correlation_id else None,
            idempotency_key=entity.idempotency_key,
            created_at=entity.created_at,
        )
    if isinstance(entity, KnowledgeAssertion):
        owner_character = entity.owner.value if isinstance(entity.owner, CharacterId) else None
        owner_player = entity.owner.value if isinstance(entity.owner, PlayerId) else None
        return KnowledgeAssertionRecord(
            world_id=entity.world_id.value,
            assertion_id=entity.assertion_id.value,
            scope=entity.scope.value,
            owner_character_id=owner_character,
            owner_player_id=owner_player,
            subject=entity.subject,
            predicate=entity.predicate,
            value=entity.value,
            epistemic_status=entity.epistemic_status,
            confidence=entity.confidence,
            valid_from=entity.valid_from,
            valid_to=entity.valid_to,
            provenance_event_id=(
                entity.provenance_event_id.value if entity.provenance_event_id else None
            ),
            source_assertion_id=(
                entity.source_assertion_id.value if entity.source_assertion_id else None
            ),
            revision=entity.revision.value,
        )
    if isinstance(entity, Observation):
        principal_kind, principal_id, principal_character, principal_player = _principal_parts(
            entity.principal_id
        )
        target_kind, target_id, target_event, target_assertion = _target_parts(entity.target_id)
        return ObservationRecord(
            world_id=entity.world_id.value,
            principal_kind=principal_kind,
            principal_id=principal_id,
            target_kind=target_kind,
            target_id=target_id,
            channel=entity.channel.value,
            observed_at=entity.observed_at,
            principal_character_id=principal_character,
            principal_player_id=principal_player,
            target_event_id=target_event,
            target_assertion_id=target_assertion,
            created_at=entity.created_at,
        )
    if isinstance(entity, CommandReceipt):
        if entity.result_reference is None:
            result_kind = result_id = result_event = result_assertion = None
        else:
            result_kind, result_id, result_event, result_assertion = _target_parts(
                entity.result_reference
            )
        return CommandReceiptRecord(
            world_id=entity.world_id.value,
            request_id=entity.request_id.value,
            command_type=entity.command_type,
            status=entity.status,
            created_at=entity.created_at,
            completed_at=entity.completed_at,
            result_kind=result_kind,
            result_id=result_id,
            result_event_id=result_event,
            result_assertion_id=result_assertion,
            revision=entity.revision.value,
        )
    raise TypeError(f"No persistence mapping for {type(entity).__name__}")


def to_domain(record: Base) -> DomainObject:
    """Map one loaded ORM record to a newly validated domain value."""

    world = WorldId(record.world_id)
    if isinstance(record, WorldRecord):
        return World(world, record.name, to_domain(record.clock), Revision(record.revision))
    if isinstance(record, WorldClockRecord):
        return WorldClock(
            world,
            record.logical_time,
            record.observed_wall_time_utc,
            record.time_scale,
            ClockState(record.state),
            Revision(record.revision),
        )
    if isinstance(record, LocationRecord):
        return Location(
            world, LocationId(world, record.location_id), record.name, Revision(record.revision)
        )
    if isinstance(record, LocationConnectionRecord):
        return LocationConnection(
            world,
            LocationId(world, record.source_id),
            LocationId(world, record.target_id),
            Revision(record.revision),
        )
    if isinstance(record, PlayerRecord):
        return Player(
            world, PlayerId(world, record.player_id), record.name, Revision(record.revision)
        )
    if isinstance(record, PlayerPresenceRecord):
        return PlayerPresence(
            world,
            PlayerId(world, record.player_id),
            LocationId(world, record.location_id),
            PlayerActivity(record.activity),
            PlayerAvailability(record.availability),
            Revision(record.revision),
        )
    if isinstance(record, CharacterRecord):
        return Character(
            world, CharacterId(world, record.character_id), record.name, Revision(record.revision)
        )
    if isinstance(record, CharacterStateRecord):
        return CharacterState(
            world,
            CharacterId(world, record.character_id),
            LocationId(world, record.location_id),
            Revision(record.revision),
        )
    if isinstance(record, RelationshipRecord):
        return Relationship(
            world,
            _principal(world, record.source_kind, record.source_id),
            _principal(world, record.target_kind, record.target_id),
            Revision(record.revision),
        )
    if isinstance(record, WorldEventRecord):
        if record.causation_event_id is not None:
            cause = EventId(world, record.causation_event_id)
        elif record.causation_request_id is not None:
            cause = RequestId(record.causation_request_id)
        else:
            cause = None
        return WorldEvent(
            EventId(world, record.event_id),
            world,
            record.event_type,
            record.occurred_at,
            record.payload,
            record.payload_version,
            record.created_at,
            cause,
            CorrelationId(record.correlation_id) if record.correlation_id else None,
            record.idempotency_key,
        )
    if isinstance(record, KnowledgeAssertionRecord):
        if record.owner_character_id is not None:
            owner = CharacterId(world, record.owner_character_id)
        elif record.owner_player_id is not None:
            owner = PlayerId(world, record.owner_player_id)
        else:
            owner = None
        return KnowledgeAssertion(
            KnowledgeAssertionId(world, record.assertion_id),
            world,
            KnowledgeScope(record.scope),
            owner,
            record.subject,
            record.predicate,
            record.value,
            record.epistemic_status,
            record.confidence,
            record.valid_from,
            record.valid_to,
            EventId(world, record.provenance_event_id) if record.provenance_event_id else None,
            KnowledgeAssertionId(world, record.source_assertion_id)
            if record.source_assertion_id
            else None,
            Revision(record.revision),
        )
    if isinstance(record, ObservationRecord):
        return Observation(
            world,
            _principal(world, record.principal_kind, record.principal_id),
            _target(world, record.target_kind, record.target_id),
            ObservationChannel(record.channel),
            record.observed_at,
            record.created_at,
        )
    if isinstance(record, CommandReceiptRecord):
        result = (
            None
            if record.result_kind is None
            else _target(world, record.result_kind, record.result_id)
        )
        return CommandReceipt(
            RequestId(record.request_id),
            world,
            record.command_type,
            record.status,
            record.created_at,
            record.completed_at,
            result,
            Revision(record.revision),
        )
    raise TypeError(f"No domain mapping for {type(record).__name__}")
