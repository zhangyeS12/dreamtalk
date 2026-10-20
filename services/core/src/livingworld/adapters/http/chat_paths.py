from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from livingworld.adapters.http.wire_contracts.chat_paths import (
    ChatPathPreview,
    ChatPathResult,
    ChatPathSnapshot,
)
from livingworld.application.chat_paths import (
    ChatPathError,
    ChatPathService,
    PathConfirm,
    PathDraft,
)
from livingworld.application.errors import (
    ChatTurnUnavailableError,
    EntityNotFoundError,
    IdempotencyConflictError,
)
from livingworld.domain.contracts import API_PROTOCOL


def chat_path_router(service: ChatPathService, authorize) -> APIRouter:
    router = APIRouter(
        prefix=f"/api/v{API_PROTOCOL}/worlds/{{world_id}}/conversations/{{conversation_id}}/paths",
        dependencies=[Depends(authorize)],
    )

    async def execute(operation):
        try:
            return await operation
        except EntityNotFoundError:
            raise HTTPException(404, detail="chat_path_not_found") from None
        except (ChatPathError, ChatTurnUnavailableError, IdempotencyConflictError) as error:
            raise HTTPException(409, detail=str(error)) from None

    @router.get("", response_model=ChatPathSnapshot)
    async def snapshot(world_id: UUID, conversation_id: UUID, before: UUID | None = None):
        return await execute(service.snapshot(world_id, conversation_id, before))

    @router.post("/preview", response_model=ChatPathPreview)
    async def preview(world_id: UUID, conversation_id: UUID, body: PathDraft):
        return await execute(service.preview(world_id, conversation_id, body))

    @router.post("/commit", response_model=ChatPathResult)
    async def commit(world_id: UUID, conversation_id: UUID, body: PathConfirm):
        return await execute(service.commit(world_id, conversation_id, body))

    return router
