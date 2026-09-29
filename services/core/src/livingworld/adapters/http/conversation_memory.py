"""Authenticated manual summary drafting, review and immutable acceptance."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from livingworld.application.conversation_memory import ConversationMemoryError
from livingworld.application.errors import EntityNotFoundError
from livingworld.domain.identifiers import ConversationId, WorldId


class GenerateMemoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_revision: int = Field(strict=True, ge=0, le=2147483646)
    mode: Literal["summarize", "correct"] = "summarize"


class PreviewMemoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    draft_id: UUID
    content: str = Field(min_length=1, max_length=8192)


class CommitMemoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    draft_id: UUID
    reviewed_hash: str = Field(pattern="^[0-9a-f]{64}$")


def conversation_memory_router(service, authorize):
    router = APIRouter(
        prefix="/api/v1/worlds/{world_id}/conversations/{conversation_id}/memory",
        dependencies=[Depends(authorize)],
    )

    def identity(world_id, conversation_id):
        return ConversationId(WorldId(world_id), conversation_id)

    async def execute(operation):
        try:
            return await operation
        except EntityNotFoundError:
            raise HTTPException(404, "conversation_not_found") from None
        except ConversationMemoryError as error:
            raise HTTPException(409, str(error)) from None
        except Exception:
            raise HTTPException(500, "memory_request_failed") from None

    @router.get("")
    async def snapshot(world_id: UUID, conversation_id: UUID):
        return await execute(service.snapshot(identity(world_id, conversation_id)))

    @router.post("/drafts")
    async def generate(
        world_id: UUID,
        conversation_id: UUID,
        body: GenerateMemoryRequest,
        x_request_id: Annotated[UUID, Header()],
    ):
        return await execute(
            service.generate(
                identity(world_id, conversation_id), x_request_id, body.base_revision, body.mode
            )
        )

    @router.post("/preview")
    async def preview(world_id: UUID, conversation_id: UUID, body: PreviewMemoryRequest):
        return await execute(
            service.preview(identity(world_id, conversation_id), body.draft_id, body.content)
        )

    @router.post("/commit")
    async def commit(world_id: UUID, conversation_id: UUID, body: CommitMemoryRequest):
        return await execute(
            service.commit(identity(world_id, conversation_id), body.draft_id, body.reviewed_hash)
        )

    @router.get("/revisions/{revision}")
    async def revision(world_id: UUID, conversation_id: UUID, revision: int):
        if not 1 <= revision <= 2147483647:
            raise HTTPException(422, "memory_revision_invalid")
        return await execute(service.revision(identity(world_id, conversation_id), revision))

    @router.get("/drafts/{draft_id}/sources")
    async def sources(world_id: UUID, conversation_id: UUID, draft_id: UUID):
        return await execute(service.sources(identity(world_id, conversation_id), draft_id))

    return router
