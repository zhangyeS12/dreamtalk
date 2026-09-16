"""Immutable canonical event values; construction is not a Kernel/storage commit."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from livingworld.domain.contracts import RequestId
from livingworld.domain.errors import DomainInvariantError
from livingworld.domain.identifiers import CorrelationId, EventId, WorldId
from livingworld.domain.values import (
    JsonValue,
    WorldTime,
    freeze_json,
    require_text,
    require_type,
    same_world,
    utc_timestamp,
)


@dataclass(frozen=True, slots=True)
class WorldEvent:
    event_id: EventId
    world_id: WorldId
    event_type: str
    occurred_at: WorldTime
    payload: Mapping[str, JsonValue]
    payload_version: int
    created_at: datetime
    causation_id: EventId | RequestId | None = None
    correlation_id: CorrelationId | None = None
    idempotency_key: str | None = None

    def __post_init__(self) -> None:
        require_type(self.event_id, EventId, "event_id")
        same_world(self.world_id, self.event_id)
        require_text(self.event_type, "event_type")
        require_type(self.occurred_at, WorldTime, "occurred_at")
        if type(self.payload_version) is not int or self.payload_version < 1:
            raise DomainInvariantError("payload_version requires a positive integer")
        require_type(self.payload, Mapping, "payload")
        object.__setattr__(self, "payload", freeze_json(self.payload))
        object.__setattr__(self, "created_at", utc_timestamp(self.created_at, "created_at"))
        if self.causation_id is not None:
            require_type(self.causation_id, (EventId, RequestId), "causation_id")
            if isinstance(self.causation_id, EventId):
                same_world(self.world_id, self.causation_id)
            else:
                require_type(self.causation_id.value, UUID, "causation request_id")
        if self.correlation_id is not None:
            require_type(self.correlation_id, CorrelationId, "correlation_id")
        if self.idempotency_key is not None:
            require_text(self.idempotency_key, "idempotency_key")
