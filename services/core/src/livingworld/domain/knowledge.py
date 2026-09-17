"""Permission ownership and explicit observations, without retrieval/propagation."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from livingworld.domain.errors import DomainInvariantError, InvalidKnowledgeOwnershipError
from livingworld.domain.identifiers import (
    CharacterId,
    EventId,
    KnowledgeAssertionId,
    ObservationId,
    PlayerId,
    PrincipalId,
    WorldId,
)
from livingworld.domain.values import (
    JsonValue,
    Revision,
    WorldTime,
    freeze_json,
    require_text,
    require_type,
    same_world,
    utc_timestamp,
)


class KnowledgeScope(StrEnum):
    TRUTH = "truth"
    CHARACTER_BELIEF = "character_belief"
    PLAYER_KNOWLEDGE = "player_knowledge"


class ObservationChannel(StrEnum):
    WITNESSED = "witnessed"
    TOLD = "told"
    MESSAGE = "message"
    NEWS = "news"
    DOCUMENT = "document"
    INFERRED = "inferred"


@dataclass(frozen=True, slots=True)
class KnowledgeAssertion:
    assertion_id: KnowledgeAssertionId
    world_id: WorldId
    scope: KnowledgeScope
    owner: PrincipalId | None
    subject: str
    predicate: str
    value: JsonValue
    epistemic_status: str
    confidence: Decimal | None
    valid_from: WorldTime
    valid_to: WorldTime | None = None
    provenance_event_id: EventId | None = None
    source_assertion_id: KnowledgeAssertionId | None = None
    revision: Revision = Revision()

    def __post_init__(self) -> None:
        require_type(self.assertion_id, KnowledgeAssertionId, "assertion_id")
        same_world(self.world_id, self.assertion_id)
        require_type(self.scope, KnowledgeScope, "scope")
        valid_owner = (
            (self.scope is KnowledgeScope.TRUTH and self.owner is None)
            or (
                self.scope is KnowledgeScope.CHARACTER_BELIEF
                and isinstance(self.owner, CharacterId)
            )
            or (self.scope is KnowledgeScope.PLAYER_KNOWLEDGE and isinstance(self.owner, PlayerId))
        )
        if not valid_owner:
            raise InvalidKnowledgeOwnershipError("Knowledge scope requires its exact owner type")
        if self.owner is not None:
            same_world(self.world_id, self.owner)
        require_text(self.subject, "subject")
        require_text(self.predicate, "predicate")
        require_text(self.epistemic_status, "epistemic_status")
        object.__setattr__(self, "value", freeze_json(self.value))
        if self.confidence is not None:
            require_type(self.confidence, Decimal, "confidence")
            if not self.confidence.is_finite() or not 0 <= self.confidence <= 1:
                raise DomainInvariantError("confidence must be finite and between zero and one")
        require_type(self.valid_from, WorldTime, "valid_from")
        if self.valid_to is not None:
            require_type(self.valid_to, WorldTime, "valid_to")
            if self.valid_to < self.valid_from:
                raise DomainInvariantError("valid_to must not precede valid_from")
        if self.provenance_event_id is not None:
            require_type(self.provenance_event_id, EventId, "provenance_event_id")
            same_world(self.world_id, self.provenance_event_id)
        if self.source_assertion_id is not None:
            require_type(self.source_assertion_id, KnowledgeAssertionId, "source_assertion_id")
            same_world(self.world_id, self.source_assertion_id)
        require_type(self.revision, Revision, "revision")


@dataclass(frozen=True, slots=True)
class Observation:
    world_id: WorldId
    principal_id: PrincipalId
    target_id: EventId | KnowledgeAssertionId
    channel: ObservationChannel
    observed_at: WorldTime
    created_at: datetime | None = None
    observation_id: ObservationId = field(kw_only=True)

    def __post_init__(self) -> None:
        require_type(self.observation_id, ObservationId, "observation_id")
        require_type(self.principal_id, (CharacterId, PlayerId), "principal_id")
        require_type(self.target_id, (EventId, KnowledgeAssertionId), "target_id")
        same_world(self.world_id, self.observation_id, self.principal_id, self.target_id)
        require_type(self.channel, ObservationChannel, "channel")
        require_type(self.observed_at, WorldTime, "observed_at")
        if self.created_at is not None:
            object.__setattr__(self, "created_at", utc_timestamp(self.created_at, "created_at"))
