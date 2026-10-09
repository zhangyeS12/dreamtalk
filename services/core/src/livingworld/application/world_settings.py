"""Authenticated local-user world management over the canonical runtime paths."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import uuid5

from livingworld.application.command_handler import CommandHandler
from livingworld.application.commands import CreateWorld
from livingworld.application.errors import IdempotencyConflictError
from livingworld.application.simulation_runtime import WorldClockService, WorldSimulationRuntime
from livingworld.domain.contracts import RequestId
from livingworld.domain.identifiers import WorldId
from livingworld.domain.values import WorldTime


@dataclass(frozen=True, slots=True)
class WorldListing:
    world_id: WorldId
    name: str


@dataclass(frozen=True, slots=True)
class WorldSettings:
    world_id: WorldId
    name: str
    world_time: WorldTime
    clock_state: str
    time_scale: Decimal
    runtime_state: str


class WorldDirectory(Protocol):
    async def list_worlds(self) -> tuple[WorldListing, ...]: ...
    async def deleted(self, world_id: WorldId) -> bool: ...


class WorldSettingsService:
    def __init__(
        self,
        directory: WorldDirectory,
        commands: CommandHandler,
        clocks: WorldClockService,
        runtime: WorldSimulationRuntime,
    ) -> None:
        self._directory = directory
        self._execute_command = commands.execute
        self._clocks = clocks
        self._runtime = runtime

    async def list_worlds(self) -> tuple[WorldSettings, ...]:
        listings = await self._directory.list_worlds()
        clocks = {clock.world_id: clock for clock in await self._clocks.list_clocks()}
        result = []
        for listing in listings:
            clock = clocks.get(listing.world_id)
            if clock is None:
                raise RuntimeError("world_clock_missing")
            runtime_state = self._runtime.state(listing.world_id)
            result.append(
                WorldSettings(
                    listing.world_id,
                    listing.name,
                    self._clocks.current_time(clock),
                    clock.state.value,
                    clock.time_scale,
                    runtime_state.value if runtime_state is not None else "unmanaged",
                )
            )
        return tuple(result)

    async def create_world(self, request_id: RequestId, name: str) -> WorldId:
        # Stable at the HTTP command boundary, so a repeated request keeps the
        # same command identity and receives the committed receipt.
        world_id = WorldId(uuid5(request_id.value, "livingworld:create-world:v1"))
        if await self._directory.deleted(world_id):
            raise IdempotencyConflictError("world_deleted")
        await self._execute_command(
            CreateWorld(request_id=request_id, world_id=world_id, name=name)
        )
        return world_id

    async def pause(self, world_id: WorldId) -> None:
        await self._runtime.pause(world_id)

    async def resume(self, world_id: WorldId) -> None:
        await self._runtime.resume(world_id)

    async def change_scale(self, world_id: WorldId, scale: Decimal) -> None:
        await self._runtime.change_scale(world_id, scale)
