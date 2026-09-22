"""Authenticated product API for world selection and clock controls."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from livingworld.application.errors import (
    EntityAlreadyExistsError,
    EntityNotFoundError,
    IdempotencyConflictError,
    WorldRuntimeUnavailableError,
)
from livingworld.application.world_settings import WorldSettings, WorldSettingsService
from livingworld.domain.contracts import API_PROTOCOL, RequestId
from livingworld.domain.errors import DomainInvariantError
from livingworld.domain.identifiers import WorldId


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateWorldRequest(StrictModel):
    name: str = Field(min_length=1, max_length=120)


class ClockScaleRequest(StrictModel):
    scale: Decimal = Field(gt=0, le=1000)


def _response(item: WorldSettings) -> dict[str, str]:
    return {
        "world_id": str(item.world_id.value),
        "name": item.name,
        "world_time": str(item.world_time.microseconds),
        "clock_state": item.clock_state,
        "time_scale": str(item.time_scale),
        "runtime_state": item.runtime_state,
    }


def world_router(service: WorldSettingsService, authorize: Callable[..., None]) -> APIRouter:
    router = APIRouter(prefix=f"/api/v{API_PROTOCOL}", dependencies=[Depends(authorize)])

    @router.get("/worlds")
    async def list_worlds() -> list[dict[str, str]]:
        return [_response(item) for item in await service.list_worlds()]

    @router.post("/worlds", status_code=201)
    async def create_world(
        body: CreateWorldRequest,
        x_request_id: Annotated[str | None, Header()] = None,
    ) -> dict[str, str]:
        try:
            request_id = RequestId.parse(x_request_id or "")
        except ValueError:
            raise HTTPException(400, "valid_request_id_required") from None
        try:
            world_id = await service.create_world(request_id, body.name)
        except (IdempotencyConflictError, EntityAlreadyExistsError):
            raise HTTPException(409, "world_creation_conflict") from None
        except DomainInvariantError:
            raise HTTPException(422, "invalid_world_name") from None
        return {"world_id": str(world_id.value)}

    @router.post("/worlds/{world_id}/clock/pause")
    async def pause_world(world_id: UUID) -> dict[str, bool]:
        try:
            await service.pause(WorldId(world_id))
        except EntityNotFoundError:
            raise HTTPException(404, "world_not_found") from None
        except WorldRuntimeUnavailableError:
            raise HTTPException(503, "world_runtime_unavailable") from None
        return {"ok": True}

    @router.post("/worlds/{world_id}/clock/resume")
    async def resume_world(world_id: UUID) -> dict[str, bool]:
        try:
            await service.resume(WorldId(world_id))
        except EntityNotFoundError:
            raise HTTPException(404, "world_not_found") from None
        except WorldRuntimeUnavailableError:
            raise HTTPException(503, "world_runtime_unavailable") from None
        return {"ok": True}

    @router.post("/worlds/{world_id}/clock/scale")
    async def change_scale(world_id: UUID, body: ClockScaleRequest) -> dict[str, bool]:
        try:
            await service.change_scale(WorldId(world_id), body.scale)
        except EntityNotFoundError:
            raise HTTPException(404, "world_not_found") from None
        except WorldRuntimeUnavailableError:
            raise HTTPException(503, "world_runtime_unavailable") from None
        return {"ok": True}

    return router
