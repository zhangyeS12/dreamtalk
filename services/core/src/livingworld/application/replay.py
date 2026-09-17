"""Pure versioned event fold and transactional one-world projection rebuild."""

from collections.abc import Callable, Mapping
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from livingworld.application.errors import (
    InvalidEventPayloadError,
    ReplayError,
    UnsupportedEventError,
)
from livingworld.application.fingerprints import canonical_json
from livingworld.application.ledger import CanonicalEvent
from livingworld.application.ports import ProjectionRebuildUnitOfWork
from livingworld.application.projections import ProjectionSnapshot
from livingworld.domain.errors import DomainInvariantError
from livingworld.domain.identifiers import (
    CharacterId,
    EventId,
    KnowledgeAssertionId,
    LocationId,
    ObservationId,
    PlayerId,
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
from livingworld.domain.relationships import Relationship, RelationshipMetrics
from livingworld.domain.values import Revision, WorldTime, require_type, utc_timestamp
from livingworld.domain.world import ClockState, Location, World, WorldClock


def _check(condition: bool, reason: str) -> None:
    if not condition:
        raise InvalidEventPayloadError(reason)


def _integer(value) -> int:
    _check(type(value) is int, "Expected integer")
    return value


def _uuid(value) -> UUID:
    _check(isinstance(value, str), "Identity must be UUID text")
    return UUID(value)


def _metrics(value: Mapping) -> RelationshipMetrics:
    return RelationshipMetrics(
        *(_integer(value[key]) for key in ("affinity", "trust", "familiarity"))
    )


class _EventFold:
    """State here comes only from earlier ledger events, never live projections."""

    def __init__(self, world_id: WorldId):
        self.world_id = world_id
        self.world: World | None = None
        self.locations: dict[LocationId, Location] = {}
        self.players: dict[PlayerId, Player] = {}
        self.presences: dict[PlayerId, PlayerPresence] = {}
        self.characters: dict[CharacterId, Character] = {}
        self.character_states: dict[CharacterId, CharacterState] = {}
        self.relationships: dict[
            tuple[CharacterId | PlayerId, CharacterId | PlayerId], Relationship
        ] = {}
        self.knowledge: dict[KnowledgeAssertionId, KnowledgeAssertion] = {}
        self.observations: dict[ObservationId, Observation] = {}
        self._acquired_observations = set()
        self._observation_causes = {}
        self._position = 0
        self._event_ids = set()
        self._handlers = {
            ("WorldCreated", 1): self._world_created,
            ("LocationCreated", 1): self._location_created,
            ("PlayerCreated", 1): self._player_created,
            ("PlayerPlaced", 1): self._player_placed,
            ("PlayerMoved", 1): self._player_moved,
            ("CharacterCreated", 1): self._character_created,
            ("CharacterPlaced", 1): self._character_placed,
            ("RelationshipChanged", 1): self._relationship_changed,
            ("WorldTruthAsserted", 1): self._truth_asserted,
            ("CharacterBeliefFormed", 1): self._character_belief_formed,
            ("ObservationRecorded", 1): self._observation_recorded,
            ("KnowledgeAcquired", 1): self._knowledge_acquired,
        }

    def apply(self, entry: CanonicalEvent) -> None:
        event = entry.event
        _check(event.world_id == self.world_id, "Ledger entry belongs to another world")
        _check(
            entry.ledger_position > self._position, "Ledger positions are not strictly increasing"
        )
        _check(event.event_id not in self._event_ids, "Duplicate canonical event identity")
        handler = self._handlers.get((event.event_type, event.payload_version))
        if handler is None:
            raise UnsupportedEventError(
                f"Unsupported event {event.event_type} v{event.payload_version} "
                f"at position {entry.ledger_position}"
            )
        try:
            _check(
                self.world is not None or event.event_type == "WorldCreated",
                "WorldCreated is required before other events",
            )
            if event.event_type == "WorldCreated":
                _check(entry.ledger_position == 1, "WorldCreated must have position 1")
            handler(event)
        except (
            KeyError,
            ValueError,
            TypeError,
            ArithmeticError,
            DomainInvariantError,
            InvalidEventPayloadError,
        ):
            raise InvalidEventPayloadError(
                f"Invalid {event.event_type} v{event.payload_version} payload "
                f"at position {entry.ledger_position}"
            ) from None
        self._position = entry.ledger_position
        self._event_ids.add(event.event_id)

    def _id(self, identity_type, value):
        return identity_type(self.world_id, _uuid(value))

    def _principal(self, value):
        _check(isinstance(value, Mapping), "Principal must be a typed identity")
        _check(WorldId(_uuid(value["world_id"])) == self.world_id, "Cross-world principal")
        identity_type = {"CharacterId": CharacterId, "PlayerId": PlayerId}[value["kind"]]
        return self._id(identity_type, value["id"])

    def _participant(self, identity) -> None:
        _check(
            identity in (self.characters if isinstance(identity, CharacterId) else self.players),
            "Missing principal",
        )

    def _new(self, collection, identity, entity) -> None:
        _check(identity not in collection, "Duplicate projection identity")
        collection[identity] = entity

    def _world_created(self, event):
        value = event.payload
        _check(
            self.world is None and _uuid(value["world_id"]) == self.world_id.value,
            "Invalid world creation",
        )
        _check(value["logical_time"] == event.occurred_at.microseconds, "World time mismatch")
        _check(
            _integer(value["world_revision"]) == _integer(value["clock_revision"]) == 0,
            "Invalid initial revision",
        )
        _check(isinstance(value["time_scale"], str), "Time scale must be exact decimal text")
        clock = WorldClock(
            self.world_id,
            WorldTime(_integer(value["logical_time"])),
            datetime.fromisoformat(value["observed_wall_time_utc"]),
            Decimal(value["time_scale"]),
            ClockState(value["clock_state"]),
            Revision(value["clock_revision"]),
        )
        _check(clock.observed_wall_time_utc == event.created_at, "Clock audit time mismatch")
        self.world = World(self.world_id, value["name"], clock, Revision(value["world_revision"]))

    def _location_created(self, event):
        value = event.payload
        _check(_integer(value["revision"]) == 0, "Invalid initial location revision")
        identity = self._id(LocationId, value["location_id"])
        self._new(
            self.locations,
            identity,
            Location(self.world_id, identity, value["name"], Revision(value["revision"])),
        )

    def _player_created(self, event):
        value = event.payload
        _check(_integer(value["revision"]) == 0, "Invalid initial player revision")
        identity = self._id(PlayerId, value["player_id"])
        self._new(
            self.players,
            identity,
            Player(self.world_id, identity, value["name"], Revision(value["revision"])),
        )

    def _player_placed(self, event):
        value = event.payload
        identity, location = (
            self._id(PlayerId, value["player_id"]),
            self._id(LocationId, value["location_id"]),
        )
        _check(identity in self.players and location in self.locations, "Missing player/location")
        _check(_integer(value["revision"]) == 0, "Invalid initial presence revision")
        presence = PlayerPresence(
            self.world_id,
            identity,
            location,
            PlayerActivity(value["activity"]),
            PlayerAvailability(value["availability"]),
            Revision(value["revision"]),
        )
        self._new(self.presences, identity, presence)

    def _player_moved(self, event):
        value = event.payload
        identity = self._id(PlayerId, value["player_id"])
        before = self.presences[identity]
        location = self._id(LocationId, value["to_location_id"])
        _check(
            location in self.locations
            and before.location_id == self._id(LocationId, value["from_location_id"]),
            "Player movement origin/destination mismatch",
        )
        after = before.at_location(location, expected_revision=before.revision)
        _check(
            after.activity is PlayerActivity(value["activity"])
            and after.availability is PlayerAvailability(value["availability"]),
            "Player movement state mismatch",
        )
        _check(after.revision.value == _integer(value["revision"]), "Player revision mismatch")
        self.presences[identity] = after

    def _character_created(self, event):
        value = event.payload
        _check(_integer(value["revision"]) == 0, "Invalid initial character revision")
        identity = self._id(CharacterId, value["character_id"])
        self._new(
            self.characters,
            identity,
            Character(self.world_id, identity, value["name"], Revision(value["revision"])),
        )

    def _character_placed(self, event):
        value = event.payload
        identity, location = (
            self._id(CharacterId, value["character_id"]),
            self._id(LocationId, value["location_id"]),
        )
        _check(
            identity in self.characters and location in self.locations, "Missing character/location"
        )
        before = self.character_states.get(identity)
        previous = (
            self._id(LocationId, value["before_location_id"])
            if value["before_location_id"] is not None
            else None
        )
        _check(
            previous == (before.location_id if before is not None else None),
            "Character origin mismatch",
        )
        revision = before.revision.advance(before.revision) if before is not None else Revision()
        _check(revision.value == _integer(value["revision"]), "Character revision mismatch")
        self.character_states[identity] = CharacterState(
            self.world_id, identity, location, revision
        )

    def _relationship_changed(self, event):
        value = event.payload
        source, target = self._principal(value["source"]), self._principal(value["target"])
        for principal, key in ((source, "source_character_id"), (target, "target_character_id")):
            self._participant(principal)
            expected = str(principal.value) if isinstance(principal, CharacterId) else None
            _check(value[key] == expected, "Relationship typed identity mismatch")
        before = self.relationships.get((source, target))
        _check(
            type(value["edge_existed"]) is bool and value["edge_existed"] == (before is not None),
            "Relationship existence mismatch",
        )
        initial = before or Relationship(self.world_id, source, target)
        _check(initial.metrics == _metrics(value["before"]), "Relationship before mismatch")
        delta = tuple(_integer(value["delta"][key]) for key in ("affinity", "trust", "familiarity"))
        after = initial.change(*delta, expected_revision=initial.revision)
        _check(
            after.metrics == _metrics(value["after"])
            and after.revision.value == _integer(value["revision"]),
            "Relationship after/revision mismatch",
        )
        self.relationships[source, target] = after

    def _assertion(self, event, *, self_provenance: bool = True) -> KnowledgeAssertion:
        value = event.payload
        confidence = value["confidence"]
        _check(
            confidence is None or isinstance(confidence, str),
            "Confidence must be exact decimal text",
        )
        assertion = KnowledgeAssertion(
            self._id(KnowledgeAssertionId, value["assertion_id"]),
            self.world_id,
            KnowledgeScope(value["scope"]),
            self._principal(value["owner"]) if value["owner"] is not None else None,
            value["subject"],
            value["predicate"],
            value["value"],
            value["epistemic_status"],
            Decimal(confidence) if confidence is not None else None,
            WorldTime(_integer(value["valid_from"])),
            WorldTime(_integer(value["valid_to"])) if value["valid_to"] is not None else None,
            self._id(EventId, value["provenance_event_id"])
            if value["provenance_event_id"] is not None
            else None,
            self._id(KnowledgeAssertionId, value["source_assertion_id"])
            if value["source_assertion_id"] is not None
            else None,
            Revision(_integer(value["revision"])),
        )
        _check(
            (not self_provenance or assertion.provenance_event_id == event.event_id)
            and assertion.revision.value == 0,
            "Assertion provenance/revision mismatch",
        )
        return assertion

    def _character_belief_formed(self, event):
        assertion = self._assertion(event, self_provenance=False)
        _check(
            assertion.scope is KnowledgeScope.CHARACTER_BELIEF,
            "Formation must create one character-owned belief",
        )
        self._participant(assertion.owner)
        if assertion.source_assertion_id is not None:
            _check(assertion.source_assertion_id in self.knowledge, "Missing belief source")
        if assertion.provenance_event_id is not None:
            _check(assertion.provenance_event_id in self._event_ids, "Missing belief provenance")
        # Neither proposition matching nor an Observation is required for internal formation.
        self._new(self.knowledge, assertion.assertion_id, assertion)

    def _truth_asserted(self, event):
        assertion = self._assertion(event)
        _check(
            assertion.scope is KnowledgeScope.TRUTH and assertion.source_assertion_id is None,
            "Invalid truth ownership/source",
        )
        self._new(self.knowledge, assertion.assertion_id, assertion)

    def _observation(self, event) -> Observation:
        value = event.payload
        receiver = self._principal(value["receiver"])
        self._participant(receiver)
        source = self._id(KnowledgeAssertionId, value["source_assertion_id"])
        _check(source in self.knowledge, "Missing observation source")
        observation = Observation(
            self.world_id,
            receiver,
            source,
            ObservationChannel(value["channel"]),
            WorldTime(_integer(value["observed_at"])),
            utc_timestamp(datetime.fromisoformat(value["created_at"]), "observation audit"),
            observation_id=self._id(ObservationId, value["observation_id"]),
        )
        _check(
            observation.observed_at == event.occurred_at
            and observation.created_at == event.created_at,
            "Observation time mismatch",
        )
        _check(
            observation.channel is not ObservationChannel.INFERRED,
            "Unsupported inferred acquisition",
        )
        return observation

    def _observation_recorded(self, event):
        observation = self._observation(event)
        self._new(self.observations, observation.observation_id, observation)
        self._observation_causes[observation.observation_id] = event.causation_id

    def _knowledge_acquired(self, event):
        observation = self._observation(event)
        _check(
            self.observations[observation.observation_id] == observation,
            "Acquisition observation mismatch",
        )
        _check(
            observation.observation_id not in self._acquired_observations,
            "Observation acquired twice",
        )
        _check(
            self._observation_causes[observation.observation_id] == event.causation_id,
            "Acquisition command mismatch",
        )
        assertion = self._assertion(event)
        _check(assertion.owner == observation.principal_id, "Acquisition owner mismatch")
        _check(
            assertion.scope
            is (
                KnowledgeScope.CHARACTER_BELIEF
                if isinstance(observation.principal_id, CharacterId)
                else KnowledgeScope.PLAYER_KNOWLEDGE
            ),
            "Acquisition scope mismatch",
        )
        source = self.knowledge[observation.target_id]
        _check(assertion.source_assertion_id == source.assertion_id, "Acquisition source mismatch")
        _check(
            (assertion.subject, assertion.predicate) == (source.subject, source.predicate)
            and canonical_json({"value": assertion.value})
            == canonical_json({"value": source.value}),
            "Acquisition proposition mismatch",
        )
        _check(
            assertion.valid_from == observation.observed_at and assertion.valid_to is None,
            "Acquisition validity mismatch",
        )
        self._new(self.knowledge, assertion.assertion_id, assertion)
        self._acquired_observations.add(observation.observation_id)

    def snapshot(self) -> ProjectionSnapshot:
        _check(self.world is not None, "Empty/incomplete world ledger")
        _check(set(self.players) == set(self.presences), "Player is missing physical presence")
        _check(
            set(self.observations) == self._acquired_observations,
            "Incomplete acquisition event pair",
        )
        return ProjectionSnapshot(
            self.world,
            tuple(self.locations.values()),
            tuple(self.players.values()),
            tuple(self.presences.values()),
            tuple(self.characters.values()),
            tuple(self.character_states.values()),
            tuple(self.relationships.values()),
            tuple(self.knowledge.values()),
            tuple(self.observations.values()),
        )


class ProjectionRebuilder:
    def __init__(self, uow_factory: Callable[[WorldId], ProjectionRebuildUnitOfWork]):
        self._uow_factory = uow_factory

    async def rebuild(self, world_id: WorldId) -> ProjectionSnapshot:
        require_type(world_id, WorldId, "world_id")
        async with self._uow_factory(world_id) as uow:
            entries = await uow.ledger.read()
            if not entries:
                raise ReplayError("World has no canonical event ledger")
            await uow.clear()
            fold = _EventFold(world_id)
            for entry in entries:
                fold.apply(entry)
            snapshot = fold.snapshot()
            await uow.replace(snapshot)
            await uow.validate()
            await uow.commit()
            return snapshot
