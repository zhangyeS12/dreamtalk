"""A future idempotency receipt contract; no handler, store or duplicate execution."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from livingworld.domain.contracts import RequestId
from livingworld.domain.errors import DomainInvariantError
from livingworld.domain.identifiers import EventId, KnowledgeAssertionId, WorldId
from livingworld.domain.values import (
    Revision,
    require_text,
    require_type,
    same_world,
    utc_timestamp,
)


@dataclass(frozen=True, slots=True)
class CommandReceipt:
    request_id: RequestId
    world_id: WorldId
    command_type: str
    status: str
    created_at: datetime
    completed_at: datetime | None = None
    result_reference: EventId | KnowledgeAssertionId | None = None
    revision: Revision = Revision()

    def __post_init__(self) -> None:
        require_type(self.request_id, RequestId, "request_id")
        require_type(self.request_id.value, UUID, "request_id value")
        same_world(self.world_id)
        require_text(self.command_type, "command_type")
        require_text(self.status, "status")
        require_type(self.revision, Revision, "revision")
        created_at = utc_timestamp(self.created_at, "created_at")
        object.__setattr__(self, "created_at", created_at)
        if self.completed_at is not None:
            completed_at = utc_timestamp(self.completed_at, "completed_at")
            if completed_at < created_at:
                raise DomainInvariantError("completed_at must not precede created_at")
            object.__setattr__(self, "completed_at", completed_at)
        if self.result_reference is not None:
            require_type(self.result_reference, (EventId, KnowledgeAssertionId), "result_reference")
            same_world(self.world_id, self.result_reference)
