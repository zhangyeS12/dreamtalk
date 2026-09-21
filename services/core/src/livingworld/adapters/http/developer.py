"""Authenticated developer inspector HTTP boundary."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from livingworld.application.developer_inspector import DeveloperInspectorService
from livingworld.domain.identifiers import CharacterId, LocationId, ObservationId, PlayerId, WorldId


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClockScaleRequest(StrictModel):
    scale: Decimal = Field(gt=0, le=1000)


class TriggerRequest(StrictModel):
    delay_microseconds: int = Field(default=1_000_000, ge=0, le=60_000_000)
    target_character_id: UUID


class MovePlayerRequest(StrictModel):
    player_id: UUID
    destination_id: UUID


class RecordMemoryRequest(StrictModel):
    owner_character_id: UUID
    observation_id: UUID
    content: str = Field(min_length=1, max_length=16_384)
    salience: int | None = Field(default=None, ge=0, le=100)


def developer_router(
    service: DeveloperInspectorService, authorize: Callable[..., None]
) -> APIRouter:
    router = APIRouter(prefix="/developer", dependencies=[Depends(authorize)])

    def world(value: UUID) -> WorldId:
        return WorldId(value)

    @router.get("/worlds")
    async def worlds() -> list[dict[str, object]]:
        return await service.list_worlds()

    @router.post("/demo-world")
    async def create_demo_world() -> dict[str, str]:
        return {"world_id": str((await service.create_demo_world()).value)}

    @router.get("/worlds/{world_id}/snapshot")
    async def snapshot(world_id: UUID, owner_character_id: UUID | None = None) -> dict[str, object]:
        identity = world(world_id)
        owner = CharacterId(identity, owner_character_id) if owner_character_id else None
        try:
            return await service.snapshot(identity, owner)
        except ValueError as error:
            raise HTTPException(404, str(error)) from None

    @router.post("/worlds/{world_id}/clock/pause")
    async def pause(world_id: UUID) -> dict[str, bool]:
        await service.pause(world(world_id))
        return {"ok": True}

    @router.post("/worlds/{world_id}/clock/resume")
    async def resume(world_id: UUID) -> dict[str, bool]:
        await service.resume(world(world_id))
        return {"ok": True}

    @router.post("/worlds/{world_id}/clock/scale")
    async def scale(world_id: UUID, body: ClockScaleRequest) -> dict[str, bool]:
        await service.change_scale(world(world_id), body.scale)
        return {"ok": True}

    @router.post("/worlds/{world_id}/triggers")
    async def trigger(world_id: UUID, body: TriggerRequest) -> dict[str, str]:
        identity = world(world_id)
        result = await service.schedule_trigger(
            identity,
            body.delay_microseconds,
            CharacterId(identity, body.target_character_id),
        )
        return {"trigger_id": str(result.value)}

    @router.post("/worlds/{world_id}/move-player")
    async def move(world_id: UUID, body: MovePlayerRequest) -> dict[str, bool]:
        identity = world(world_id)
        await service.move_player(
            identity,
            PlayerId(identity, body.player_id),
            LocationId(identity, body.destination_id),
        )
        return {"ok": True}

    @router.post("/worlds/{world_id}/memories")
    async def memory(world_id: UUID, body: RecordMemoryRequest) -> dict[str, str]:
        identity = world(world_id)
        result = await service.record_memory(
            identity,
            CharacterId(identity, body.owner_character_id),
            ObservationId(identity, body.observation_id),
            body.content,
            body.salience,
        )
        return {"memory_id": str(result.value)}

    return router
