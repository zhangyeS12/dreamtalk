"""Authenticated transcript read for the selected local Player."""

from datetime import UTC
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from livingworld.application.chat_messages import (
    ChatMessage,
    ChatMessageService,
    DirectTurnView,
    GroupTurnView,
    PlayerSend,
)
from livingworld.application.chat_reply import (
    ChatReplyBudgetError,
    ChatReplyGenerationError,
    ChatReplyIntegrityError,
    ChatReplyUnavailableError,
    ChatReplyValidationError,
    DirectChatReplyService,
)
from livingworld.application.errors import (
    ChatTurnUnavailableError,
    EntityNotFoundError,
    IdempotencyConflictError,
)
from livingworld.application.group_chat_reply import GroupChatReplyService
from livingworld.domain.contracts import API_PROTOCOL, RequestId
from livingworld.domain.identifiers import ChatTurnId, ConversationId, PlayerId, WorldId


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


def _turn_view(turn: DirectTurnView) -> dict:
    return {
        "turn_id": str(turn.sent.turn_id.value),
        "state": turn.state,
        "token_ceiling": turn.sent.token_ceiling,
        "player_message": _view(turn.sent.message),
        "reply": _view(turn.reply) if turn.reply is not None else None,
    }


def _group_turn_view(turn: GroupTurnView) -> dict:
    return {
        "turn_id": str(turn.sent.turn_id.value),
        "state": turn.state,
        "token_ceiling": turn.sent.token_ceiling,
        "player_message": _view(turn.sent.message),
        "replies": [_view(reply) for reply in turn.replies],
    }


def _reply_availability(service) -> dict:
    return {
        "available": service is not None and service.available,
        "input_token_reservation": service.input_token_reservation if service is not None else None,
        "max_output_tokens": service.max_output_tokens if service is not None else None,
    }


def _budget_failure_code(error: ChatReplyBudgetError) -> str:
    # Only fixed safe labels cross HTTP; never stringify an unknown provider error.
    return {
        "turn_token_limit_exceeded": "chat_turn_token_limit_exceeded",
        "turn_input_bound_unavailable": "chat_input_bound_unavailable",
    }.get(str(error), "chat_token_limit_unverifiable")


def chat_message_router(
    service: ChatMessageService,
    authorize,
    reply_service: DirectChatReplyService | None = None,
    group_reply_service: GroupChatReplyService | None = None,
) -> APIRouter:
    router = APIRouter(
        prefix=f"/api/v{API_PROTOCOL}/worlds/{{world_id}}/conversations",
        dependencies=[Depends(authorize)],
    )

    @router.get("/reply-availability")
    async def reply_availability() -> dict:
        return _reply_availability(reply_service)

    @router.get("/group-reply-availability")
    async def group_reply_availability() -> dict:
        return _reply_availability(group_reply_service)

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

    @router.get("/{conversation_id}/messages/page")
    async def page_messages(
        world_id: UUID,
        conversation_id: UUID,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        before_position: Annotated[int | None, Query(ge=1)] = None,
    ) -> dict:
        try:
            page = await service.page_messages(
                ConversationId(WorldId(world_id), conversation_id), limit, before_position
            )
        except EntityNotFoundError as error:
            if str(error) == "selected_player_required":
                raise HTTPException(409, "selected_player_required") from None
            raise HTTPException(404, "conversation_not_found") from None
        return {
            "items": [_view(message) for message in page.messages],
            "next_before_position": page.next_before_position,
        }

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
        except ChatTurnUnavailableError:
            raise HTTPException(409, "group_turn_unavailable") from None
        except ValueError:
            raise HTTPException(422, "chat_message_invalid") from None
        return {
            "turn_id": str(sent.turn_id.value),
            "token_ceiling": sent.token_ceiling,
            "status": sent.status,
            "message": _view(sent.message),
        }

    @router.post("/{conversation_id}/group-messages", status_code=202)
    async def send_group_message(
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
            sent = await service.send_group_player(
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
        except ChatTurnUnavailableError:
            raise HTTPException(409, "group_turn_unavailable") from None
        except ValueError:
            raise HTTPException(422, "chat_message_invalid") from None
        return {
            "turn_id": str(sent.turn_id.value),
            "token_ceiling": sent.token_ceiling,
            "status": sent.status,
            "message": _view(sent.message),
        }

    @router.get("/{conversation_id}/group-turns/{turn_id}")
    async def get_group_turn(world_id: UUID, conversation_id: UUID, turn_id: UUID) -> dict:
        try:
            turn = await service.group_turn(
                ConversationId(WorldId(world_id), conversation_id),
                ChatTurnId(WorldId(world_id), turn_id),
            )
        except EntityNotFoundError:
            raise HTTPException(404, "chat_turn_not_found") from None
        except ChatTurnUnavailableError:
            raise HTTPException(409, "group_turn_required") from None
        return _group_turn_view(turn)

    @router.post("/{conversation_id}/group-turns/{turn_id}/reply")
    async def generate_group_reply(world_id: UUID, conversation_id: UUID, turn_id: UUID) -> dict:
        if group_reply_service is None:
            raise HTTPException(503, "chat_model_unavailable")
        conversation = ConversationId(WorldId(world_id), conversation_id)
        try:
            current = await service.group_turn(
                conversation, ChatTurnId(conversation.world_id, turn_id)
            )
            if current.state == "completed":
                return _group_turn_view(current)
            if current.state == "claimed":
                raise HTTPException(409, "chat_turn_already_claimed")
            return _group_turn_view(await group_reply_service.reply(current.sent))
        except EntityNotFoundError:
            raise HTTPException(404, "chat_turn_not_found") from None
        except ChatTurnUnavailableError:
            raise HTTPException(409, "chat_turn_already_claimed") from None
        except ChatReplyBudgetError as error:
            raise HTTPException(422, _budget_failure_code(error)) from None
        except ChatReplyUnavailableError:
            raise HTTPException(503, "chat_model_unavailable") from None
        except ChatReplyIntegrityError:
            raise HTTPException(503, "chat_accounting_unavailable") from None
        except ChatReplyValidationError:
            raise HTTPException(502, "chat_reply_invalid") from None
        except ChatReplyGenerationError:
            raise HTTPException(502, "chat_generation_failed") from None

    @router.get("/{conversation_id}/turns/{turn_id}")
    async def get_turn(world_id: UUID, conversation_id: UUID, turn_id: UUID) -> dict:
        try:
            turn = await service.direct_turn(
                ConversationId(WorldId(world_id), conversation_id),
                ChatTurnId(WorldId(world_id), turn_id),
            )
        except EntityNotFoundError:
            raise HTTPException(404, "chat_turn_not_found") from None
        except ChatTurnUnavailableError:
            raise HTTPException(409, "direct_turn_required") from None
        return _turn_view(turn)

    @router.post("/{conversation_id}/turns/{turn_id}/reply")
    async def generate_reply(world_id: UUID, conversation_id: UUID, turn_id: UUID) -> dict:
        if reply_service is None:
            raise HTTPException(503, "chat_model_unavailable")
        conversation = ConversationId(WorldId(world_id), conversation_id)
        try:
            current = await service.direct_turn(
                conversation, ChatTurnId(conversation.world_id, turn_id)
            )
            if current.state == "completed":
                return _turn_view(current)
            if current.state == "claimed":
                raise HTTPException(409, "chat_turn_already_claimed")
            await reply_service.reply(current.sent)
            return _turn_view(await service.direct_turn(conversation, current.sent.turn_id))
        except EntityNotFoundError:
            raise HTTPException(404, "chat_turn_not_found") from None
        except ChatTurnUnavailableError:
            raise HTTPException(409, "chat_turn_already_claimed") from None
        except ChatReplyBudgetError as error:
            raise HTTPException(422, _budget_failure_code(error)) from None
        except ChatReplyUnavailableError:
            raise HTTPException(503, "chat_model_unavailable") from None
        except ChatReplyIntegrityError:
            raise HTTPException(503, "chat_accounting_unavailable") from None
        except ChatReplyValidationError:
            raise HTTPException(502, "chat_reply_invalid") from None
        except ChatReplyGenerationError:
            raise HTTPException(502, "chat_generation_failed") from None

    return router
