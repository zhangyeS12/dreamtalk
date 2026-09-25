"""Authenticated local-Player chat directory; no message generation here."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from livingworld.application.chat_conversations import (
    ChatConversation,
    ChatConversationService,
    GroupChatConversation,
)
from livingworld.application.errors import EntityNotFoundError, IdempotencyConflictError
from livingworld.domain.contracts import API_PROTOCOL, RequestId
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


class CreateGroupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    import_ids: list[UUID] = Field(min_length=2)


def _group_view(group: GroupChatConversation) -> dict:
    return {
        "conversation_id": str(group.conversation_id.value),
        "player_id": str(group.player_id.value),
        "kind": "group",
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
    async def list_conversations(world_id: UUID) -> list[dict]:
        return [_view(item) for item in await service.list_for_world(WorldId(world_id))]

    @router.get("/groups")
    async def list_groups(world_id: UUID) -> list[dict]:
        groups = await service.list_groups_for_world(WorldId(world_id))
        return [_group_view(item) for item in groups]

    @router.post("/groups")
    async def create_group(
        world_id: UUID,
        body: CreateGroupRequest,
        x_request_id: Annotated[str | None, Header()] = None,
    ) -> dict:
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

    @router.post("/direct/{import_id}")
    async def open_direct(world_id: UUID, import_id: UUID) -> dict:
        try:
            return _view(await service.open_direct(WorldId(world_id), import_id))
        except EntityNotFoundError as error:
            if str(error) == "selected_player_required":
                raise HTTPException(409, "selected_player_required") from None
            raise HTTPException(404, "contact_not_found") from None

    return router
