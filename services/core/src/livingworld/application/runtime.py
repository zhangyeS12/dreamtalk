import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal, cast

from livingworld.domain.contracts import RequestId
from livingworld.domain.identifiers import WorldId

type LLMRuntimeStatus = Literal["ready", "partially_configured", "unconfigured", "degraded"]

_LLM_STATUS_VALUES = frozenset({"ready", "partially_configured", "unconfigured", "degraded"})


@dataclass
class RuntimeStatus:
    core_version: str
    generation: str
    ready: bool = False
    llm_health: Callable[[], str] = lambda: "unconfigured"
    world_llm_health: Callable[[WorldId], str] | None = None

    def llm_status_for_world(self, world: WorldId) -> LLMRuntimeStatus:
        if self.world_llm_health is None:
            return self.llm_status
        try:
            value = self.world_llm_health(world)
            return cast(LLMRuntimeStatus, value) if value in _LLM_STATUS_VALUES else "degraded"
        except Exception:
            return "degraded"

    @property
    def llm_status(self) -> LLMRuntimeStatus:
        try:
            value = self.llm_health()
            return (
                cast(LLMRuntimeStatus, value)
                if type(value) is str and value in _LLM_STATUS_VALUES
                else "degraded"
            )
        except Exception:
            return "degraded"


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
