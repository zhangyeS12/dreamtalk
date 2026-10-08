"""Pure versioned event fold and transactional one-world projection rebuild."""

from collections.abc import Callable, Mapping
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid5

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
        self._routine_starts = {}
        self._routine_ends = set()
        self._encounter_times = {}
        self._encounter_candidates = set()
        self._shared_starts = {}
        self._shared_ends = set()
        self._handlers = {
            ("WorldCreated", 1): self._world_created,
            ("LocationCreated", 1): self._location_created,
            ("LocationUpdated", 1): self._location_updated,
            ("PlayerCreated", 1): self._player_created,
            ("PlayerPlaced", 1): self._player_placed,
            ("PlayerMoved", 1): self._player_moved,
            ("PlayerAvailabilityChanged", 1): self._player_availability_changed,
            ("CharacterCreated", 1): self._character_created,
            ("CharacterPlaced", 1): self._character_placed,
            ("CharacterLocationConfigured", 1): self._character_location_configured,
            ("CharactersMet", 1): self._characters_met,
            ("SharedActivityStarted", 1): self._shared_activity_started,
            ("SharedActivityEnded", 1): self._shared_activity_terminal,
            ("SharedActivityInterrupted", 1): self._shared_activity_terminal,
            ("CharacterRoutineStarted", 1): self._character_routine_started,
            ("CharacterRoutineEnded", 1): self._character_routine_ended,
            ("CharacterRoutineInterrupted", 1): self._character_routine_ended,
            ("PublicWorldEventPublished", 1): self._public_world_event_published,
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

    def _public_world_event_published(self, event):
        value = event.payload
        _check(
            self.world is not None
            and set(value) == {"entry_id", "batch_id", "player_id", "title", "body", "time_text"},
            "Invalid public announcement",
        )
        _uuid(value["entry_id"])
        _uuid(value["batch_id"])
        _check(self._id(PlayerId, value["player_id"]) in self.players, "Missing audience")
        _check(
            isinstance(value["title"], str) and 1 <= len(value["title"]) <= 80, "Invalid headline"
        )
        _check(
            isinstance(value["body"], str) and 5 <= len(value["body"]) <= 500,
            "Invalid announcement text",
        )
        _check(
            value["time_text"] is None
            or isinstance(value["time_text"], str)
            and len(value["time_text"]) <= 100
            and value["time_text"] in value["body"],
            "Invalid reported time",
        )
        # Publication does not mutate physical state, beliefs, or experience.

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

    def _character_location_configured(self, event):
        value = event.payload
        identity = self._id(CharacterId, value["character_id"])
        location = self._id(LocationId, value["initial_location_id"])
        _check(
            identity in self.character_states and location in self.locations,
            "Missing configured character/location",
        )
        _check(
            self.character_states[identity].revision.value == _integer(value["revision"]),
            "Configured character revision mismatch",
        )

    def _location_updated(self, event):
        value = event.payload
        identity = self._id(LocationId, value["location_id"])
        before = self.locations[identity]
        _check(
            before.revision.value + 1 == _integer(value["revision"]), "Location revision mismatch"
        )
        _check(before.name == value["before_name"], "Location name mismatch")
        self.locations[identity] = Location(
            self.world_id, identity, value["name"], Revision(value["revision"])
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

    def _player_availability_changed(self, event):
        value = event.payload
        identity = self._id(PlayerId, value["player_id"])
        before = self.presences[identity]
        _check(
            before.availability.value == value["before_availability"],
            "Player availability origin mismatch",
        )
        after = before.with_availability(
            PlayerAvailability(value["availability"]), expected_revision=before.revision
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

    def _characters_met(self, event):
        value = event.payload
        _check(
            set(value)
            == {
                "first_character_id",
                "second_character_id",
                "location_id",
                "first_routine_id",
                "second_routine_id",
                "first_revision",
                "second_revision",
                "candidate_id",
                "purpose",
                "encounter_due_at",
                "encounter_end_at",
            },
            "Invalid encounter payload",
        )
        due, end = _integer(value["encounter_due_at"]), _integer(value["encounter_end_at"])
        _check(
            due < end <= due + 300_000_000 and due <= event.occurred_at.microseconds < end,
            "Invalid encounter window",
        )
        first = self._id(CharacterId, value["first_character_id"])
        second = self._id(CharacterId, value["second_character_id"])
        location = self._id(LocationId, value["location_id"])
        _check(
            first.value.int < second.value.int and value["purpose"] == "brief_greeting",
            "Invalid encounter pair/purpose",
        )
        pair = (first, second)
        previous = self._encounter_times.get(pair)
        _check(
            previous is None or event.occurred_at.microseconds - previous >= 21_600_000_000,
            "Encounter pair cooldown",
        )
        for owner, routine_key, revision_key in (
            (first, "first_routine_id", "first_revision"),
            (second, "second_routine_id", "second_revision"),
        ):
            routine = UUID(value[routine_key])
            _check(
                routine in self._routine_starts and routine not in self._routine_ends,
                "Encounter needs active routine",
            )
            _, actor, activity, target, end, start = self._routine_starts[routine]
            presence = self.character_states.get(owner)
            _check(
                actor == owner
                and activity in {"rest", "leisure"}
                and target == value["location_id"]
                and start <= event.occurred_at
                and event.occurred_at.microseconds < end
                and presence is not None
                and presence.location_id == location
                and presence.revision.value == _integer(value[revision_key]),
                "Encounter presence/activity mismatch",
            )
        candidate = UUID(value["candidate_id"])
        _check(candidate not in self._encounter_candidates, "Duplicate encounter candidate")
        self._encounter_candidates.add(candidate)
        self._encounter_times[pair] = event.occurred_at.microseconds

    def _shared_presence(self, value, occurred):
        first = self._id(CharacterId, value["first_character_id"])
        second = self._id(CharacterId, value["second_character_id"])
        place = self._id(LocationId, value["location_id"])
        _check(
            first.value.int < second.value.int and place in self.locations,
            "Invalid shared pair/place",
        )
        _check(value["activity"] in {"shared_rest", "shared_leisure"}, "Invalid shared activity")
        activity = "rest" if value["activity"] == "shared_rest" else "leisure"
        for owner, routine_key, revision_key in (
            (first, "first_routine_id", "first_revision"),
            (second, "second_routine_id", "second_revision"),
        ):
            routine_id = _uuid(value[routine_key])
            _check(
                routine_id in self._routine_starts and routine_id not in self._routine_ends,
                "Shared activity requires active routines",
            )
            _, actor, kind, target, end, start = self._routine_starts[routine_id]
            presence = self.character_states.get(owner)
            _check(
                actor == owner
                and kind == activity
                and target == value["location_id"]
                and start <= occurred
                and value["started_at"] < end
                and value["planned_end"] <= end
                and presence is not None
                and presence.location_id == place
                and presence.revision.value == _integer(value[revision_key]),
                "Shared presence/activity mismatch",
            )
        return first, second

    def _shared_activity_started(self, event):
        value = event.payload
        _check(
            set(value)
            == {
                "candidate_id",
                "first_character_id",
                "second_character_id",
                "location_id",
                "first_routine_id",
                "second_routine_id",
                "first_revision",
                "second_revision",
                "activity",
                "started_at",
                "planned_end",
            },
            "Invalid shared start fields",
        )
        began, end = _integer(value["started_at"]), _integer(value["planned_end"])
        _check(
            began == event.occurred_at.microseconds and 900_000_000 <= end - began <= 1_800_000_000,
            "Invalid shared interval",
        )
        pair = self._shared_presence(value, event.occurred_at)
        _check(
            pair in self._encounter_times and began - self._encounter_times[pair] >= 21_600_000_000,
            "Shared activity needs prior meeting and cooldown",
        )
        candidate = _uuid(value["candidate_id"])
        _check(
            candidate not in self._shared_starts
            and event.event_id.value
            == uuid5(uuid5(candidate, "kernel-shared-start"), "shared-activity"),
            "Invalid shared start identity",
        )
        self._shared_starts[candidate] = (event.event_id, dict(value))
        self._encounter_times[pair] = began

    def _shared_activity_terminal(self, event):
        value = event.payload
        candidate = _uuid(value["candidate_id"])
        _check(
            candidate in self._shared_starts and candidate not in self._shared_ends,
            "Shared terminal requires unique start",
        )
        start, original = self._shared_starts[candidate]
        _check(
            set(value) == set(original) | {"start_event_id", "reason"}
            and all(value[key] == original[key] for key in original),
            "Shared terminal metadata mismatch",
        )
        _check(
            self._id(EventId, value["start_event_id"]) == start
            and event.event_id.value
            == uuid5(uuid5(candidate, "kernel-shared-terminal"), "shared-activity"),
            "Shared terminal source mismatch",
        )
        _check(
            event.occurred_at.microseconds >= original["started_at"],
            "Shared terminal predates start",
        )
        if event.event_type == "SharedActivityEnded":
            _check(
                value["reason"] == "interval_elapsed"
                and original["planned_end"]
                <= event.occurred_at.microseconds
                <= original["planned_end"] + 300_000_000,
                "Invalid shared completion",
            )
            self._shared_presence(value, event.occurred_at)
        else:
            _check(
                value["reason"]
                in {
                    "presence_changed",
                    "activity_changed",
                    "consent_or_plan_changed",
                    "continuity_unconfirmed",
                },
                "Invalid shared interruption",
            )
        self._shared_ends.add(candidate)

    def _character_routine_started(self, event):
        from livingworld.domain.actions import RoutineActivity

        value = event.payload
        RoutineActivity(value["activity"])
        identity = self._id(CharacterId, value["character_id"])
        _check(identity in self.character_states, "Routine requires placed character")
        _check(
            _integer(value["planned_until"]) > event.occurred_at.microseconds,
            "Invalid routine window",
        )
        candidate = UUID(value["candidate_id"])
        _check(candidate not in self._routine_starts, "Duplicate routine candidate")
        self._character_placed(event)
        self._routine_starts[candidate] = (
            event.event_id,
            identity,
            value["activity"],
            value["location_id"],
            value["planned_until"],
            event.occurred_at,
        )

    def _character_routine_ended(self, event):
        value = event.payload
        candidate = UUID(value["candidate_id"])
        _check(
            candidate in self._routine_starts and candidate not in self._routine_ends,
            "Routine termination requires one unterminated start",
        )
        start, owner, activity, location, planned, began = self._routine_starts[candidate]
        _check(self._id(EventId, value["start_event_id"]) == start, "Routine source mismatch")
        _check(
            self._id(CharacterId, value["character_id"]) == owner
            and value["activity"] == activity
            and value["location_id"] == location
            and _integer(value["planned_until"]) == planned,
            "Routine termination metadata mismatch",
        )
        presence = self.character_states[owner]
        _check(
            self._id(LocationId, value["current_location_id"]) == presence.location_id
            and _integer(value["revision"]) == presence.revision.value,
            "Routine termination presence mismatch",
        )
        _check(event.occurred_at >= began, "Routine termination predates start")
        expected = (
            "interval_elapsed"
            if event.event_type == "CharacterRoutineEnded"
            else "presence_changed"
        )
        _check(value["reason"] == expected, "Invalid routine termination reason")
        if expected == "interval_elapsed":
            _check(event.occurred_at.microseconds >= planned, "Routine interval has not elapsed")
        # Termination frees operational occupancy but never moves the actor, advances
        # placement revision or proves any work/result was accomplished.
        self._routine_ends.add(candidate)

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
