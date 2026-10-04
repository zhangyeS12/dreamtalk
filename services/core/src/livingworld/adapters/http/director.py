"""Safe operational status; never expose future plans or private character state."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from livingworld.application.director import DirectorError
from livingworld.application.errors import EntityNotFoundError
from livingworld.domain.identifiers import WorldId


class DirectorSettingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = Field(strict=True)
    consent_background_usage: bool = Field(default=False, strict=True)
    expected_revision: int = Field(ge=0, le=2147483646, strict=True)
    retry: bool = Field(default=False, strict=True)


class EncounterSettingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = Field(strict=True)
    consent_background_usage: bool = Field(default=False, strict=True)
    expected_revision: int = Field(ge=0, le=2147483646, strict=True)


def director_router(service, authorize):
    router = APIRouter(
        prefix="/api/v1/worlds/{world_id}/director", dependencies=[Depends(authorize)]
    )

    async def execute(operation):
        try:
            return await operation
        except EntityNotFoundError:
            raise HTTPException(404, "world_not_found") from None
        except DirectorError as error:
            raise HTTPException(409, str(error)) from None
        except Exception:
            raise HTTPException(500, "director_request_failed") from None

    @router.get("")
    async def snapshot(world_id: UUID):
        return await execute(service.snapshot(WorldId(world_id)))

    @router.post("")
    async def configure(world_id: UUID, body: DirectorSettingRequest):
        return await execute(
            service.configure(
                WorldId(world_id),
                body.enabled,
                body.consent_background_usage,
                body.expected_revision,
                body.retry,
            )
        )

    @router.post("/encounters")
    async def configure_encounters(world_id: UUID, body: EncounterSettingRequest):
        return await execute(
            service.configure_encounters(
                WorldId(world_id),
                body.enabled,
                body.consent_background_usage,
                body.expected_revision,
            )
        )

    @router.post("/shared-activities")
    async def configure_shared_activities(world_id: UUID, body: EncounterSettingRequest):
        return await execute(
            service.configure_shared_activities(
                WorldId(world_id),
                body.enabled,
                body.consent_background_usage,
                body.expected_revision,
            )
        )

    return router
