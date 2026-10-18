"""Authenticated product API for world selection and clock controls."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException

from livingworld.adapters.http import contracts as wire
from livingworld.adapters.http.contracts import (
    ClockScaleRequest,
    CreateWorldRequest,
    DeleteWorldRequest,
    WorldSettings,
)
from livingworld.application.errors import (
    EntityAlreadyExistsError,
    EntityNotFoundError,
    IdempotencyConflictError,
    WorldRuntimeUnavailableError,
)
from livingworld.application.world_settings import WorldSettings as WorldSettingsValue
from livingworld.application.world_settings import WorldSettingsService
from livingworld.domain.contracts import API_PROTOCOL, RequestId
from livingworld.domain.errors import DomainInvariantError
from livingworld.domain.identifiers import WorldId
from livingworld.domain.world import ClockState


def _response(item: WorldSettingsValue) -> WorldSettings:
    return {
        "world_id": str(item.world_id.value),
        "name": item.name,
        "world_time": str(item.world_time.microseconds),
        "clock_state": ClockState(item.clock_state),
        "time_scale": str(item.time_scale),
        "runtime_state": item.runtime_state,
    }


def world_router(
    service: WorldSettingsService,
    authorize: Callable[..., None],
    deletion=None,
    storage_observer=None,
) -> APIRouter:
    router = APIRouter(prefix=f"/api/v{API_PROTOCOL}", dependencies=[Depends(authorize)])

    @router.get("/worlds")
    async def list_worlds() -> list[WorldSettings]:
        return [_response(item) for item in await service.list_worlds()]

    @router.delete("/worlds/{world_id}", response_model=wire.DeleteWorldResult)
    async def delete_world(world_id: UUID, body: DeleteWorldRequest) -> dict:
        if not body.confirmed:
            raise HTTPException(422, "world_delete_confirmation_required")
        if deletion is None:
            raise HTTPException(503, "world_deletion_unavailable")
        try:
            result = await deletion.delete(WorldId(world_id), body.expected_name)
            if storage_observer:
                import asyncio

                await asyncio.to_thread(storage_observer)
            return result
        except EntityNotFoundError:
            raise HTTPException(404, "world_not_found") from None
        except ValueError as error:
            raise HTTPException(409, str(error)) from None

    @router.get("/worlds/{world_id}/deletion")
    async def deletion_status(world_id: UUID) -> dict:
        if deletion is None:
            raise HTTPException(503, "world_deletion_unavailable")
        return {"deleted": await deletion.store.deleted(WorldId(world_id))}

    @router.post("/worlds", status_code=201, response_model=wire.CreateWorldResult)
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
        if storage_observer:
            import asyncio

            await asyncio.to_thread(storage_observer)
        return {"world_id": str(world_id.value)}

    @router.post("/worlds/{world_id}/clock/pause", response_model=wire.PauseProductWorldResult)
    async def pause_world(world_id: UUID) -> dict[str, bool]:
        try:
            await service.pause(WorldId(world_id))
        except EntityNotFoundError:
            raise HTTPException(404, "world_not_found") from None
        except WorldRuntimeUnavailableError:
            raise HTTPException(503, "world_runtime_unavailable") from None
        return {"ok": True}

    @router.post("/worlds/{world_id}/clock/resume", response_model=wire.PauseProductWorldResult)
    async def resume_world(world_id: UUID) -> dict[str, bool]:
        try:
            await service.resume(WorldId(world_id))
        except EntityNotFoundError:
            raise HTTPException(404, "world_not_found") from None
        except WorldRuntimeUnavailableError:
            raise HTTPException(503, "world_runtime_unavailable") from None
        return {"ok": True}

    @router.post("/worlds/{world_id}/clock/scale", response_model=wire.PauseProductWorldResult)
    async def change_scale(world_id: UUID, body: ClockScaleRequest) -> dict[str, bool]:
        try:
            await service.change_scale(WorldId(world_id), body.scale)
        except EntityNotFoundError:
            raise HTTPException(404, "world_not_found") from None
        except WorldRuntimeUnavailableError:
            raise HTTPException(503, "world_runtime_unavailable") from None
        return {"ok": True}

    return router
