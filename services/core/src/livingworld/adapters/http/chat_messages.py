"""Authenticated transcript read for the selected local Player."""

from datetime import UTC
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from livingworld.application.chat_messages import ChatMessage, ChatMessageService, PlayerSend
from livingworld.application.errors import EntityNotFoundError, IdempotencyConflictError
from livingworld.domain.contracts import API_PROTOCOL, RequestId
from livingworld.domain.identifiers import ConversationId, PlayerId, WorldId


class PlayerMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=65536)
    token_ceiling: int = Field(strict=True, ge=1, le=9223372036854775807)


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

    @router.post("/{conversation_id}/messages", status_code=202)
    async def send_player_message(
        world_id: UUID,
        conversation_id: UUID,
        body: PlayerMessageRequest,
        x_request_id: Annotated[str | None, Header()] = None,
    ) -> dict:
        try:
            request_id = RequestId.parse(x_request_id or "")
        except ValueError:
            raise HTTPException(400, "valid_request_id_required") from None
        try:
            sent: PlayerSend = await service.send_player(
                request_id,
                ConversationId(WorldId(world_id), conversation_id),
                body.text,
                body.token_ceiling,
            )
        except EntityNotFoundError as error:
            if str(error) == "selected_player_required":
                raise HTTPException(409, "selected_player_required") from None
            raise HTTPException(404, "conversation_not_found") from None
        except IdempotencyConflictError:
            raise HTTPException(409, "chat_request_conflict") from None
        except ValueError:
            raise HTTPException(422, "chat_message_invalid") from None
        return {
            "turn_id": str(sent.turn_id.value),
            "token_ceiling": sent.token_ceiling,
            "status": sent.status,
            "message": _view(sent.message),
        }

    return router
