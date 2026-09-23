"""Authenticated local-Player chat directory; no message generation here."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from livingworld.application.chat_conversations import ChatConversation, ChatConversationService
from livingworld.application.errors import EntityNotFoundError
from livingworld.domain.contracts import API_PROTOCOL
from livingworld.domain.identifiers import WorldId


def _view(conversation: ChatConversation) -> dict:
    return {
        "conversation_id": str(conversation.conversation_id.value),
        "player_id": str(conversation.player_id.value),
        "character_id": str(conversation.character_id.value),
        "root_import_id": str(conversation.root_import_id),
        "character_name": conversation.character_name,
        "kind": "direct",
    }


def chat_conversation_router(service: ChatConversationService, authorize) -> APIRouter:
    router = APIRouter(
        prefix=f"/api/v{API_PROTOCOL}/worlds/{{world_id}}/conversations",
        dependencies=[Depends(authorize)],
    )

    @router.get("")
    async def list_conversations(world_id: UUID) -> list[dict]:
        return [_view(item) for item in await service.list_for_world(WorldId(world_id))]

    @router.post("/direct/{import_id}")
    async def open_direct(world_id: UUID, import_id: UUID) -> dict:
        try:
            return _view(await service.open_direct(WorldId(world_id), import_id))
        except EntityNotFoundError as error:
            if str(error) == "selected_player_required":
                raise HTTPException(409, "selected_player_required") from None
            raise HTTPException(404, "contact_not_found") from None

    return router
