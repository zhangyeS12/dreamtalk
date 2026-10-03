"""Authenticated transcript read for the selected local Player."""

import asyncio
import json
from contextlib import suppress
from datetime import UTC
from typing import Annotated
from uuid import UUID

from anyio import CancelScope
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import StreamingResponse

from livingworld.application.chat_messages import (
    ChatMessage,
    ChatMessageService,
    DirectTurnView,
    GroupTurnView,
    PlayerSend,
)
from livingworld.application.chat_recall import EarlierChatRecall
from livingworld.application.chat_reply import (
    ChatProgress,
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


class ReplyRecoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_attempt_id: UUID
    token_ceiling: int = Field(strict=True, ge=1, le=9223372036854775807)


class ChatHistorySearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=256)
    before_position: int | None = Field(default=None, strict=True, ge=1, le=9223372036854775807)


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
        "story_sent_at_utc": message.story_sent_at_utc.astimezone(UTC).isoformat()
        if message.story_sent_at_utc is not None
        else None,
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


class ChatStreamResponse(StreamingResponse):
    """Starlette owns disconnect detection; explicitly close the producer too."""

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            # ASGI 2.4 send failures need explicit closure as well. Shield cleanup
            # from the disconnect scope so governed execution can settle once.
            with CancelScope(shield=True):
                await self.body_iterator.aclose()


def _validation_failure_code(error: ChatReplyValidationError) -> str:
    code = str(error)
    return (
        code
        if code
        in {
            "group_selection_invalid",
            "group_selection_output_limit",
            "chat_reply_output_limit",
            "chat_reply_empty",
            "chat_reply_format_invalid",
        }
        else "chat_reply_invalid"
    )


def _stream_failure(error: Exception) -> tuple[int, str]:
    if isinstance(error, ChatReplyBudgetError):
        return 422, _budget_failure_code(error)
    if isinstance(error, ChatReplyUnavailableError):
        return 503, "chat_model_unavailable"
    if isinstance(error, ChatReplyIntegrityError):
        return 503, "chat_accounting_unavailable"
    if isinstance(error, ChatTurnUnavailableError):
        return 409, "chat_turn_already_claimed"
    if isinstance(error, EntityNotFoundError):
        return 404, "chat_turn_not_found"
    if isinstance(error, ChatReplyValidationError):
        return 502, _validation_failure_code(error)
    return 502, "chat_generation_failed"


def _stream_response(current, reply_service) -> ChatStreamResponse:
    async def events():
        # Backpressure bounds transient data; neither a durable queue nor replay.
        queue: asyncio.Queue[dict | None] = asyncio.Queue(maxsize=8)
        turn_id = str(current.sent.turn_id.value)

        async def progress(event: ChatProgress):
            frame = {"turn_id": turn_id, "kind": event.kind}
            if event.kind in {"replying", "delta"} and event.speaker is not None:
                frame["speaker_id"] = str(event.speaker.value)
            if event.kind == "delta":
                frame["text"] = event.text
            elif event.kind == "message" and event.message is not None:
                frame["message"] = _view(event.message)
            await queue.put(frame)

        async def produce():
            try:
                if current.state == "completed":
                    messages = (
                        current.replies
                        if isinstance(current, GroupTurnView)
                        else (current.reply,)
                        if current.reply is not None
                        else ()
                    )
                    for message in messages:
                        await progress(ChatProgress("message", message=message))
                else:
                    await reply_service.reply(current.sent, progress=progress)
                await queue.put({"turn_id": turn_id, "kind": "completed"})
            except Exception as error:
                status, code = _stream_failure(error)
                await queue.put(
                    {"turn_id": turn_id, "kind": "error", "status": status, "code": code}
                )
            await queue.put(None)

        task = asyncio.create_task(produce())
        try:
            yield "data: " + json.dumps({"turn_id": turn_id, "kind": "preparing"}) + "\n\n"
            while True:
                try:
                    async with asyncio.timeout(10):
                        frame = await queue.get()
                except TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                if frame is None:
                    return
                yield (
                    "data: " + json.dumps(frame, ensure_ascii=True, separators=(",", ":")) + "\n\n"
                )
        finally:
            with CancelScope(shield=True):
                if not task.done():
                    task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    return ChatStreamResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


def chat_message_router(
    service: ChatMessageService,
    authorize,
    reply_service: DirectChatReplyService | None = None,
    group_reply_service: GroupChatReplyService | None = None,
    chat_recall: EarlierChatRecall | None = None,
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

    @router.post("/{conversation_id}/messages/search")
    async def search_history(
        world_id: UUID, conversation_id: UUID, body: ChatHistorySearchRequest
    ) -> dict:
        if chat_recall is None:
            raise HTTPException(503, "chat_history_unavailable")
        try:
            result = await chat_recall.search_history(
                ConversationId(WorldId(world_id), conversation_id), body.query, body.before_position
            )
        except EntityNotFoundError as error:
            if str(error) == "selected_player_required":
                raise HTTPException(409, "selected_player_required") from None
            raise HTTPException(404, "conversation_not_found") from None
        except ValueError:
            raise HTTPException(422, "chat_history_query_invalid") from None
        return {
            "items": [_view(message) for message in result.messages],
            "scanned_count": result.scanned_count,
            "skipped_count": result.skipped_count,
            "next_before_position": result.next_before_position,
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
        except ChatReplyValidationError as error:
            raise HTTPException(502, _validation_failure_code(error)) from None
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
        except ChatReplyValidationError as error:
            raise HTTPException(502, _validation_failure_code(error)) from None
        except ChatReplyGenerationError:
            raise HTTPException(502, "chat_generation_failed") from None

    @router.post("/{conversation_id}/turns/{turn_id}/reply/stream")
    async def stream_direct_reply(world_id: UUID, conversation_id: UUID, turn_id: UUID):
        if reply_service is None:
            raise HTTPException(503, "chat_model_unavailable")
        try:
            current = await service.direct_turn(
                ConversationId(WorldId(world_id), conversation_id),
                ChatTurnId(WorldId(world_id), turn_id),
            )
        except EntityNotFoundError:
            raise HTTPException(404, "chat_turn_not_found") from None
        except ChatTurnUnavailableError:
            raise HTTPException(409, "direct_turn_required") from None
        if current.state == "claimed":
            raise HTTPException(409, "chat_turn_already_claimed")
        return _stream_response(current, reply_service)

    @router.post("/{conversation_id}/group-turns/{turn_id}/reply/stream")
    async def stream_group_reply(world_id: UUID, conversation_id: UUID, turn_id: UUID):
        if group_reply_service is None:
            raise HTTPException(503, "chat_model_unavailable")
        try:
            current = await service.group_turn(
                ConversationId(WorldId(world_id), conversation_id),
                ChatTurnId(WorldId(world_id), turn_id),
            )
        except EntityNotFoundError:
            raise HTTPException(404, "chat_turn_not_found") from None
        except ChatTurnUnavailableError:
            raise HTTPException(409, "group_turn_required") from None
        if current.state == "claimed":
            raise HTTPException(409, "chat_turn_already_claimed")
        return _stream_response(current, group_reply_service)

    @router.get("/{conversation_id}/reply-recovery/{source_turn_id}")
    async def get_reply_recovery(world_id: UUID, conversation_id: UUID, source_turn_id: UUID):
        try:
            return await service.reply_recovery(
                ConversationId(WorldId(world_id), conversation_id),
                ChatTurnId(WorldId(world_id), source_turn_id),
            )
        except EntityNotFoundError:
            raise HTTPException(404, "chat_turn_not_found") from None

    @router.post("/{conversation_id}/reply-recovery/{source_turn_id}", status_code=201)
    async def create_reply_recovery(
        world_id: UUID,
        conversation_id: UUID,
        source_turn_id: UUID,
        body: ReplyRecoveryRequest,
        x_request_id: Annotated[UUID, Header(alias="X-Request-Id")],
    ):
        try:
            return await service.create_reply_recovery(
                RequestId(x_request_id),
                ConversationId(WorldId(world_id), conversation_id),
                ChatTurnId(WorldId(world_id), source_turn_id),
                body.expected_attempt_id,
                body.token_ceiling,
            )
        except EntityNotFoundError:
            raise HTTPException(404, "chat_turn_not_found") from None
        except IdempotencyConflictError:
            raise HTTPException(409, "chat_request_conflict") from None
        except ChatTurnUnavailableError as error:
            # Only labels produced by the recovery store are permitted.
            code = str(error)
            raise HTTPException(
                409,
                code
                if code
                in {
                    "chat_recovery_changed",
                    "chat_recovery_not_latest",
                    "chat_recovery_has_replies",
                    "chat_recovery_unknown",
                    "chat_recovery_running",
                    "chat_recovery_unavailable",
                }
                else "chat_recovery_unavailable",
            ) from None

    return router
