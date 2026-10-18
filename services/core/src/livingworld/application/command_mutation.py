"""A mutation plan inside the coordinator-owned unit of work."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

from livingworld.application.errors import EntityNotFoundError
from livingworld.application.ports import UnitOfWork
from livingworld.application.results import EntityReference
from livingworld.domain.identifiers import LocationId, ObservationId
from livingworld.domain.values import Revision, WorldTime, same_world
from livingworld.domain.world import Location, World


@dataclass(frozen=True)
class MutationContext:
    uow: UnitOfWork
    world: World
    now: datetime
    logical_time: WorldTime

    async def location(self, identity: LocationId) -> Location:
        same_world(self.world.world_id, identity)
        location = await self.uow.locations.get(identity)
        if location is None:
            raise EntityNotFoundError("Location does not exist")
        return location


@dataclass(frozen=True)
class CommandMutation:
    events: list[tuple[str, dict]]
    reference: EntityReference
    revision: Revision
    apply: Callable[[], Awaitable[None]]
    observation_id: ObservationId | None = None
