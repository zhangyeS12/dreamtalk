"""Typed, immutable results independent of ORM and transport."""

from dataclasses import dataclass

from livingworld.domain.contracts import RequestId
from livingworld.domain.identifiers import (
    CharacterId,
    KnowledgeAssertionId,
    LocationId,
    ObservationId,
    PlayerId,
    PrincipalId,
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
