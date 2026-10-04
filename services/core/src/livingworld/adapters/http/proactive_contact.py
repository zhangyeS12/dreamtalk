"""Authenticated settings and read metadata; no public character location endpoint."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from livingworld.application.errors import EntityNotFoundError
from livingworld.application.proactive_contact import ProactiveContactError
from livingworld.domain.identifiers import WorldId


class SettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    # FastAPI validates an already-decoded dict; UUIDs arrive as JSON strings.
    # Keep booleans, intervals and revisions strict; parse only the UUID field.
    expected_player_id: UUID = Field(strict=False)
    enabled: bool
    interval_minutes: int = Field(ge=15, le=1440)
    consent_background_usage: bool = False
    expected_revision: int = Field(ge=0, le=2147483646)


class ReadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    position: int = Field(ge=1, le=9223372036854775807)


def proactive_contact_router(service, authorize, logger):
    router = APIRouter(prefix="/api/v1/worlds/{world_id}", dependencies=[Depends(authorize)])

    async def execute(operation):
        try:
            return await operation
        except EntityNotFoundError:
            raise HTTPException(404, "proactive_resource_not_found") from None
        except ProactiveContactError as error:
            raise HTTPException(409, str(error)) from None
        except Exception:
            logger.emit("proactive_contact", "proactive_request_failed", level="ERROR")
            raise HTTPException(503, "proactive_request_failed") from None

    @router.get("/proactive-contact")
    async def snapshot(world_id: UUID):
        return await execute(service.snapshot(WorldId(world_id)))

    @router.post("/proactive-contact")
    async def configure(world_id: UUID, body: SettingsRequest):
        return await execute(
            service.configure(
                WorldId(world_id),
                body.enabled,
                body.interval_minutes,
                body.consent_background_usage,
                body.expected_revision,
                body.expected_player_id,
            )
        )

    @router.get("/chat-unread")
    async def unread(world_id: UUID):
        return await execute(service.unread_snapshot(WorldId(world_id)))

    @router.post("/conversations/{conversation_id}/read")
    async def mark_read(world_id: UUID, conversation_id: UUID, body: ReadRequest):
        await execute(service.mark_read(WorldId(world_id), conversation_id, body.position))
        return {"read": True}

    return router
