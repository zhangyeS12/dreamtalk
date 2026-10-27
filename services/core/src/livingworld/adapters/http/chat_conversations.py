"""Authenticated local-Player chat directory; no message generation here."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict

from livingworld.adapters.http import contracts as wire
from livingworld.adapters.http.contracts import (
    ChatConversation,
    CreateGroupRequest,
    GroupChatConversation,
)
from livingworld.application.chat_conversations import (
    ChatConversation as ChatConversationValue,
)
from livingworld.application.chat_conversations import (
    ChatConversationService,
)
from livingworld.application.chat_conversations import (
    GroupChatConversation as GroupChatConversationValue,
)
from livingworld.application.errors import (
    ChatTurnUnavailableError,
    EntityNotFoundError,
    IdempotencyConflictError,
)
from livingworld.domain.contracts import API_PROTOCOL, RequestId
from livingworld.domain.identifiers import WorldId


class PinRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    pinned: bool


def _view(conversation: ChatConversationValue) -> ChatConversation:
    return {
        "conversation_id": str(conversation.conversation_id.value),
        "player_id": str(conversation.player_id.value),
        "character_id": str(conversation.character_id.value),
        "root_import_id": str(conversation.root_import_id),
        "character_name": conversation.character_name,
        "kind": "direct",
        "pinned": conversation.pinned,
        "read_only": conversation.read_only,
    }


def _group_view(group: GroupChatConversationValue) -> GroupChatConversation:
    return {
        "conversation_id": str(group.conversation_id.value),
        "player_id": str(group.player_id.value),
        "kind": "group",
        "pinned": group.pinned,
        "read_only": group.read_only,
        "participants": [
            {
                "character_id": str(item.character_id.value),
                "root_import_id": str(item.root_import_id),
                "character_name": item.character_name,
            }
            for item in group.participants
        ],
    }


def chat_conversation_router(service: ChatConversationService, authorize) -> APIRouter:
    router = APIRouter(
        prefix=f"/api/v{API_PROTOCOL}/worlds/{{world_id}}/conversations",
        dependencies=[Depends(authorize)],
    )

    @router.get("")
    async def list_conversations(world_id: UUID) -> list[ChatConversation]:
        return [_view(item) for item in await service.list_for_world(WorldId(world_id))]

    @router.get("/groups")
    async def list_groups(world_id: UUID) -> list[GroupChatConversation]:
        groups = await service.list_groups_for_world(WorldId(world_id))
        return [_group_view(item) for item in groups]

    @router.post("/groups")
    async def create_group(
        world_id: UUID,
        body: CreateGroupRequest,
        x_request_id: Annotated[str | None, Header()] = None,
    ) -> GroupChatConversation:
        try:
            request_id = RequestId.parse(x_request_id or "")
        except ValueError:
            raise HTTPException(400, "valid_request_id_required") from None
        try:
            return _group_view(
                await service.create_group(WorldId(world_id), request_id, tuple(body.import_ids))
            )
        except EntityNotFoundError as error:
            if str(error) == "selected_player_required":
                raise HTTPException(409, "selected_player_required") from None
            raise HTTPException(404, "contact_not_found") from None
        except IdempotencyConflictError:
            raise HTTPException(409, "group_request_conflict") from None
        except ValueError:
            raise HTTPException(422, "group_members_invalid") from None

    @router.delete("/groups/{conversation_id}", response_model=wire.DissolveGroupResult)
    async def dissolve_group(world_id: UUID, conversation_id: UUID) -> dict:
        try:
            await service.dissolve_group(WorldId(world_id), conversation_id)
            return {"dissolved": True}
        except EntityNotFoundError as error:
            raise HTTPException(404, str(error)) from None
        except ChatTurnUnavailableError as error:
            raise HTTPException(409, str(error)) from None

    @router.patch("/{conversation_id}/pin")
    async def set_pin(world_id: UUID, conversation_id: UUID, body: PinRequest) -> dict:
        try:
            await service.set_pinned(WorldId(world_id), conversation_id, body.pinned)
        except EntityNotFoundError as error:
            if str(error) == "selected_player_required":
                raise HTTPException(409, "selected_player_required") from None
            raise HTTPException(404, "conversation_not_found") from None
        return {"pinned": body.pinned}

    @router.post("/direct/{import_id}")
    async def open_direct(world_id: UUID, import_id: UUID) -> ChatConversation:
        try:
            return _view(await service.open_direct(WorldId(world_id), import_id))
        except EntityNotFoundError as error:
            if str(error) == "selected_player_required":
                raise HTTPException(409, "selected_player_required") from None
            raise HTTPException(404, "contact_not_found") from None

    return router
