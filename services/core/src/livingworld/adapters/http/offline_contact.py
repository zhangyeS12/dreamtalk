"""Bound local recovery settings and delivered-message unread state."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from livingworld.application.errors import EntityNotFoundError
from livingworld.application.offline_contact import OfflineContactError
from livingworld.domain.identifiers import WorldId


class OfflineSettingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = Field(strict=True)
    hours: int = Field(default=6, strict=True, ge=1, le=168)
    consent_background_usage: bool = Field(default=False, strict=True)
    expected_revision: int = Field(strict=True, ge=0, le=2147483646)


def offline_contact_router(service, authorize):
    router = APIRouter(
        prefix="/api/v1/worlds/{world_id}/offline-contact", dependencies=[Depends(authorize)]
    )

    async def execute(operation):
        try:
            return await operation
        except EntityNotFoundError:
            raise HTTPException(404, "offline_resource_not_found") from None
        except OfflineContactError as error:
            raise HTTPException(409, str(error)) from None
        except Exception:
            raise HTTPException(500, "offline_request_failed") from None

    @router.get("")
    async def snapshot(world_id: UUID):
        return await execute(service.snapshot(WorldId(world_id)))

    @router.post("")
    async def configure(world_id: UUID, body: OfflineSettingRequest):
        return await execute(
            service.configure(
                WorldId(world_id),
                body.enabled,
                body.hours,
                body.consent_background_usage,
                body.expected_revision,
            )
        )

    @router.post("/messages/{message_id}/read")
    async def mark_read(world_id: UUID, message_id: UUID):
        await execute(service.mark_read(WorldId(world_id), message_id))
        return {"read": True}

    return router


class SessionVisibilityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    world_id: UUID | None = None
    visible: bool = Field(strict=True)
    sequence: int = Field(strict=True, ge=1, le=9223372036854775807)


def session_visibility_router(service, authorize):
    router = APIRouter(prefix="/api/v1", dependencies=[Depends(authorize)])

    @router.post("/session-visibility")
    async def visibility(body: SessionVisibilityRequest):
        try:
            await service.store.visibility(body.world_id, body.visible, body.sequence)
        except Exception:
            raise HTTPException(500, "visibility_update_failed") from None
        return {"updated": True}

    return router
