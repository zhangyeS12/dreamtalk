"""Owner-scoped journal and consented public-news controls."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from livingworld.application.errors import EntityNotFoundError
from livingworld.application.world_story import WorldStoryError
from livingworld.domain.identifiers import WorldId


class NewsSettingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = Field(strict=True)
    consent_background_usage: bool = Field(default=False, strict=True)
    expected_revision: int = Field(ge=0, le=2147483646, strict=True)
    replenish: bool = Field(default=False, strict=True)


class NewsMarkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: str = Field(pattern="^(pending|experienced|skipped)$")
    expected_revision: int = Field(ge=0, le=2147483646, strict=True)


class StoryCorrectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hidden: bool = Field(default=False, strict=True)
    correction: str | None = Field(default=None, max_length=500, strict=True)
    expected_revision: int = Field(ge=0, le=2147483646, strict=True)


def world_story_router(service, authorize):
    router = APIRouter(
        prefix="/api/v1/worlds/{world_id}/stories", dependencies=[Depends(authorize)]
    )

    async def execute(operation):
        try:
            return await operation
        except EntityNotFoundError:
            raise HTTPException(404, "world_not_found") from None
        except WorldStoryError as error:
            raise HTTPException(409, str(error)) from None
        except Exception:
            raise HTTPException(500, "news_request_failed") from None

    @router.get("")
    async def entries(world_id: UUID, before: str | None = None):
        if before is not None and len(before) > 100:
            raise HTTPException(400, "story_cursor_invalid")
        return await execute(service.entries(WorldId(world_id), before))

    @router.get("/settings")
    async def snapshot(world_id: UUID):
        return await execute(service.snapshot(WorldId(world_id)))

    @router.post("/settings")
    async def configure(world_id: UUID, body: NewsSettingRequest):
        return await execute(
            service.configure(
                WorldId(world_id),
                body.enabled,
                body.consent_background_usage,
                body.expected_revision,
                body.replenish,
            )
        )

    @router.post("/news/{entry_id}/mark")
    async def mark(world_id: UUID, entry_id: UUID, body: NewsMarkRequest):
        return await execute(
            service.mark(WorldId(world_id), entry_id, body.state, body.expected_revision)
        )

    @router.post("/chat/{entry_id}")
    async def correct(world_id: UUID, entry_id: UUID, body: StoryCorrectionRequest):
        return await execute(
            service.correct(
                WorldId(world_id), entry_id, body.hidden, body.correction, body.expected_revision
            )
        )

    return router
