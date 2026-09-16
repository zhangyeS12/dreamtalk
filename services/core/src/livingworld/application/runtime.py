import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field

from livingworld.domain.contracts import RequestId


@dataclass
class RuntimeStatus:
    core_version: str
    generation: str
    ready: bool = False


@dataclass
class ShutdownRequests:
    """Infrastructure-only idempotent mutation boundary, scoped to this generation.

    Shutdown is intrinsically idempotent. This is not a durable general-purpose
    mutation cache and does not define future world-event deduplication semantics.
    """

    event: asyncio.Event = field(default_factory=asyncio.Event)
    requested: bool = False
    on_request: Callable[[], None] = lambda: None

    def request(self, request_id: RequestId) -> dict[str, bool | str]:
        if not self.requested:
            self.requested = True
            self.on_request()
            self.event.set()
        return {"accepted": True, "request_id": str(request_id)}
