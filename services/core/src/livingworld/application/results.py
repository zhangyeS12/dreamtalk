"""Typed, immutable results independent of ORM and transport."""

from dataclasses import dataclass

from livingworld.domain.actions import ActionRejectionReason, ActionResolutionStatus
from livingworld.domain.contracts import RequestId
from livingworld.domain.identifiers import (
    CharacterId,
    EventId,
    KnowledgeAssertionId,
    LocationId,
    MemoryId,
    ObservationId,
    PlayerId,
    PrincipalId,
    SceneId,
    WorldId,
)
from livingworld.domain.values import Revision


@dataclass(frozen=True, slots=True)
class RelationshipReference:
    source_id: PrincipalId
    target_id: PrincipalId


type EntityReference = (
    WorldId | LocationId | PlayerId | CharacterId | KnowledgeAssertionId | RelationshipReference
)


@dataclass(frozen=True, slots=True)
class CommandResult:
    request_id: RequestId
    command_type: str
    entity_reference: EntityReference
    resulting_revision: Revision
    replayed: bool = False
    observation_id: ObservationId | None = None


@dataclass(frozen=True, slots=True)
class ActionResult:
    request_id: RequestId
    status: ActionResolutionStatus
    reason: ActionRejectionReason | None
    event_ids: tuple[EventId, ...]
    resulting_revision: Revision | None
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class SceneResult:
    request_id: RequestId
    scene_id: SceneId
    resulting_revision: Revision
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class MemoryResult:
    request_id: RequestId
    memory_id: MemoryId
    replayed: bool = False
