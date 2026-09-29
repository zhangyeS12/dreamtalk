"""Typed action proposals and deterministic resolution contracts."""

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from livingworld.domain.errors import DomainInvariantError
from livingworld.domain.identifiers import (
    ActivationId,
    CharacterId,
    CorrelationId,
    EventId,
    LocationId,
    PlayerId,
    PrincipalId,
    SceneId,
    WorldId,
)
from livingworld.domain.values import Revision, require_type, same_world


class ActionKind(StrEnum):
    MOVE_PLAYER = "move_player"
    CHARACTER_ROUTINE = "character_routine"


class ProposerKind(StrEnum):
    PLAYER_INPUT = "player_input"
    CHARACTER_RUNTIME = "character_runtime"
    SYSTEM = "system"
    DIRECTOR = "director"


@dataclass(frozen=True, slots=True)
class ActionProposer:
    kind: ProposerKind
    principal_id: PrincipalId | None = None

    def __post_init__(self) -> None:
        require_type(self.kind, ProposerKind, "proposer kind")
        expected = {
            ProposerKind.PLAYER_INPUT: PlayerId,
            ProposerKind.CHARACTER_RUNTIME: CharacterId,
            ProposerKind.SYSTEM: type(None),
            ProposerKind.DIRECTOR: type(None),
        }[self.kind]
        if not isinstance(self.principal_id, expected):
            raise DomainInvariantError("Proposer kind requires its exact principal identity")


@dataclass(frozen=True, slots=True)
class MovePlayerPayload:
    destination_id: LocationId
    expected_presence_revision: Revision

    def __post_init__(self) -> None:
        require_type(self.destination_id, LocationId, "destination_id")
        require_type(self.expected_presence_revision, Revision, "expected_presence_revision")


class RoutineActivity(StrEnum):
    REST = "rest"
    WORK = "work"
    LEISURE = "leisure"


@dataclass(frozen=True, slots=True)
class CharacterRoutinePayload:
    destination_id: LocationId
    expected_presence_revision: Revision
    activity: RoutineActivity
    candidate_id: UUID

    def __post_init__(self):
        require_type(self.destination_id, LocationId, "destination_id")
        require_type(self.expected_presence_revision, Revision, "expected_presence_revision")
        require_type(self.activity, RoutineActivity, "routine activity")
        require_type(self.candidate_id, UUID, "candidate_id")


type ActionPayload = MovePlayerPayload | CharacterRoutinePayload


@dataclass(frozen=True, slots=True)
class ActionProposal:
    world_id: WorldId
    kind: ActionKind
    schema_version: int
    proposer: ActionProposer
    actor_id: PrincipalId | None
    payload: ActionPayload
    scene_id: SceneId | None = None
    source_activation_id: ActivationId | None = None
    causation_id: EventId | None = None
    correlation_id: CorrelationId | None = None

    def __post_init__(self) -> None:
        require_type(self.kind, ActionKind, "action kind")
        if type(self.schema_version) is not int or self.schema_version < 1:
            raise DomainInvariantError("Action schema_version requires a positive integer")
        require_type(self.proposer, ActionProposer, "proposer")
        if not isinstance(self.payload, (MovePlayerPayload, CharacterRoutinePayload)):
            raise DomainInvariantError("Unsupported action payload")
        if self.actor_id is not None:
            same_world(self.world_id, self.actor_id)
        same_world(self.world_id, self.payload.destination_id)
        for identity in (self.scene_id, self.source_activation_id, self.causation_id):
            if identity is not None:
                same_world(self.world_id, identity)
        if self.proposer.principal_id is not None:
            same_world(self.world_id, self.proposer.principal_id)


class ActionResolutionStatus(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class ActionRejectionReason(StrEnum):
    UNAUTHORIZED_ACTOR = "unauthorized_actor"
    INVALID_SCENE = "invalid_scene"
    NOT_PRESENT = "not_present"
    PRECONDITION_FAILED = "precondition_failed"
    INVALID_DESTINATION = "invalid_destination"
    CONFLICT = "conflict"
    UNSUPPORTED_ACTION = "unsupported_action"
    WAKE_FANOUT_TOO_LARGE = "wake_fanout_too_large"


class AudienceSelectorKind(StrEnum):
    NONE = "none"
    ACTOR_ONLY = "actor_only"
    SCENE_PARTICIPANTS = "scene_participants"
    LOCATION_PRESENT = "location_present"
    EXPLICIT_PRINCIPALS = "explicit_principals"


@dataclass(frozen=True, slots=True)
class AudienceSelector:
    kind: AudienceSelectorKind
    scene_id: SceneId | None = None
    location_id: LocationId | None = None
    principals: tuple[PrincipalId, ...] = ()

    def __post_init__(self) -> None:
        require_type(self.kind, AudienceSelectorKind, "audience selector kind")
        if self.kind is AudienceSelectorKind.SCENE_PARTICIPANTS and self.scene_id is None:
            raise DomainInvariantError("SCENE_PARTICIPANTS requires SceneId")
        if self.kind is AudienceSelectorKind.LOCATION_PRESENT and self.location_id is None:
            raise DomainInvariantError("LOCATION_PRESENT requires LocationId")
        if self.kind is AudienceSelectorKind.EXPLICIT_PRINCIPALS and not self.principals:
            raise DomainInvariantError("EXPLICIT_PRINCIPALS requires at least one principal")


@dataclass(frozen=True, slots=True)
class PerceptionAudience:
    selectors: tuple[AudienceSelector, ...]

    def __post_init__(self) -> None:
        if not self.selectors:
            raise DomainInvariantError("PerceptionAudience requires an explicit selector")
        for selector in self.selectors:
            require_type(selector, AudienceSelector, "audience selector")
