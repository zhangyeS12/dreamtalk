"""Manage only the current player's sourced, character-scoped chat memories."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from livingworld.application.errors import EntityNotFoundError
from livingworld.application.long_chat_memory import LongMemoryError
from livingworld.domain.identifiers import CharacterId, ConversationId, WorldId


class CaptureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = Field(strict=True)
    expected_revision: int = Field(strict=True, ge=0, le=2147483646)


class MarkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    active: bool = Field(strict=True)
    pinned: bool = Field(strict=True)
    expected_revision: int = Field(strict=True, ge=0, le=2147483646)


def long_chat_memory_router(service, authorize):
    router = APIRouter(
        prefix="/api/v1/worlds/{world_id}/conversations/{conversation_id}/long-memory/{character_id}",
        dependencies=[Depends(authorize)],
    )

    def ids(world, conversation, character):
        world = WorldId(world)
        return ConversationId(world, conversation), CharacterId(world, character)

    async def execute(operation):
        try:
            return await operation
        except EntityNotFoundError:
            raise HTTPException(404, "long_memory_not_found") from None
        except LongMemoryError as error:
            code = str(error)
            raise HTTPException(
                409,
                code
                if code in {"long_memory_changed", "long_memory_cursor_invalid"}
                else "long_memory_invalid",
            ) from None
        except Exception:
            raise HTTPException(500, "long_memory_request_failed") from None

    @router.get("")
    async def snapshot(
        world_id: UUID,
        conversation_id: UUID,
        character_id: UUID,
        before: str | None = Query(default=None, max_length=100),
        query: str = Query(default="", max_length=200),
    ):
        return await execute(
            service.snapshot(*ids(world_id, conversation_id, character_id), before, query)
        )

    @router.post("/settings")
    async def configure(
        world_id: UUID, conversation_id: UUID, character_id: UUID, body: CaptureRequest
    ):
        await execute(
            service.configure(
                *ids(world_id, conversation_id, character_id), body.enabled, body.expected_revision
            )
        )
        return await execute(service.snapshot(*ids(world_id, conversation_id, character_id)))

    @router.post("/{entry_id}")
    async def mark(
        world_id: UUID, conversation_id: UUID, character_id: UUID, entry_id: UUID, body: MarkRequest
    ):
        await execute(
            service.mark(
                *ids(world_id, conversation_id, character_id),
                entry_id,
                body.active,
                body.pinned,
                body.expected_revision,
            )
        )
        return await execute(service.snapshot(*ids(world_id, conversation_id, character_id)))

    return router
