"""Authenticated transcript read for the selected local Player."""

from datetime import UTC
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from livingworld.application.chat_messages import ChatMessage, ChatMessageService
from livingworld.application.errors import EntityNotFoundError
from livingworld.domain.contracts import API_PROTOCOL
from livingworld.domain.identifiers import ConversationId, PlayerId, WorldId


def _view(message: ChatMessage) -> dict:
    return {
        "message_id": str(message.message_id.value),
        "turn_id": str(message.turn_id.value),
        "conversation_id": str(message.conversation_id.value),
        "position": message.position,
        "sender_kind": "player" if isinstance(message.sender_id, PlayerId) else "character",
        "sender_id": str(message.sender_id.value),
        "text": message.text,
        "created_at_utc": message.created_at_utc.astimezone(UTC).isoformat(),
    }


def chat_message_router(service: ChatMessageService, authorize) -> APIRouter:
    router = APIRouter(
        prefix=f"/api/v{API_PROTOCOL}/worlds/{{world_id}}/conversations",
        dependencies=[Depends(authorize)],
    )

    @router.get("/{conversation_id}/messages")
    async def list_messages(world_id: UUID, conversation_id: UUID) -> list[dict]:
        try:
            messages = await service.list_messages(
                ConversationId(WorldId(world_id), conversation_id)
            )
        except EntityNotFoundError as error:
            if str(error) == "selected_player_required":
                raise HTTPException(409, "selected_player_required") from None
            raise HTTPException(404, "conversation_not_found") from None
        return [_view(message) for message in messages]

    return router
