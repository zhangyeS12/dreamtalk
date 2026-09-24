"""Player sends are durable and idempotent without starting a model call."""

import asyncio
import io
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from card_fixtures import card_document, json_bytes
from fastapi.testclient import TestClient
from livingworld.adapters.http.app import create_app
from livingworld.application.chat_conversations import ChatConversationService
from livingworld.application.chat_messages import ChatMessageService
from livingworld.application.command_handler import CommandHandler
from livingworld.application.commands import CreateWorld
from livingworld.application.errors import EntityNotFoundError, IdempotencyConflictError
from livingworld.application.player_event_feed import PlayerEventFeedService
from livingworld.application.player_onboarding import LocalPlayerOnboardingService
from livingworld.application.runtime import RuntimeStatus, ShutdownRequests
from livingworld.application.simulation_clock import EffectiveWorldTimeSource, SystemMonotonicClock
from livingworld.domain.contracts import RequestId
from livingworld.domain.identifiers import ConversationId, WorldId
from livingworld.infrastructure.clock import SystemWallClock
from livingworld.infrastructure.logging import StructuredLogger
from livingworld.infrastructure.persistence import Database
from livingworld.infrastructure.persistence.models import (
    ChatMessageRecord,
    ChatTurnRecord,
    KnowledgeAssertionRecord,
    ObservationRecord,
    WorldEventRecord,
)
from sqlalchemy import func, select


def test_player_send_is_ordered_idempotent_and_world_scoped(tmp_path):
    async def run():
        db = Database(tmp_path)
        await db.initialize()
        clock = SystemWallClock()
        handler = CommandHandler(
            db.unit_of_work,
            clock,
            world_time_source=EffectiveWorldTimeSource(clock, SystemMonotonicClock()),
        )
        players = PlayerEventFeedService(db.player_event_feed_store())
        imports = db.world_content_service()
        conversations = ChatConversationService(
            db.chat_conversation_store(), imports, players, handler
        )
        messages = ChatMessageService(db.chat_message_store(), players)
        worlds = (WorldId(uuid4()), WorldId(uuid4()))
        try:
            for world in worlds:
                await handler.execute(
                    CreateWorld(request_id=RequestId(uuid4()), world_id=world, name="测试世界")
                )
                await LocalPlayerOnboardingService(handler, players).start_at_home(world)
            staged = await imports.prepare(worlds[0], "character", json_bytes(card_document()))
            card = await imports.commit(worlds[0], staged.item.import_id, staged.item.reviewed_hash)
            conversation = await conversations.open_direct(worlds[0], card.import_id)
            request = RequestId(uuid4())
            first = await messages.send_player(
                request, conversation.conversation_id, "你好", 50_000
            )
            assert first.status == "pending"
            assert first.message.position == 1
            assert first.message.sender_id == conversation.player_id
            assert (
                await messages.send_player(request, conversation.conversation_id, "你好", 50_000)
                == first
            )
            assert await asyncio.gather(
                messages.send_player(request, conversation.conversation_id, "你好", 50_000),
                messages.send_player(request, conversation.conversation_id, "你好", 50_000),
            ) == [first, first]
            second = await messages.send_player(
                RequestId(uuid4()), conversation.conversation_id, "再聊聊", 50_000
            )
            assert second.message.position == 2
            assert second.message.message_id != first.message.message_id
            assert second.turn_id != first.turn_id
            with pytest.raises(IdempotencyConflictError, match="chat_request_conflict"):
                await messages.send_player(request, conversation.conversation_id, "改写", 50_000)
            with pytest.raises(IdempotencyConflictError, match="chat_request_conflict"):
                await messages.send_player(request, conversation.conversation_id, "你好", 60_000)
            with pytest.raises(IdempotencyConflictError, match="chat_request_conflict"):
                await messages.send_player(
                    request,
                    ConversationId(worlds[1], conversation.conversation_id.value),
                    "你好",
                    50_000,
                )
            with pytest.raises(EntityNotFoundError, match="conversation_not_found"):
                await messages.list_messages(
                    ConversationId(worlds[1], conversation.conversation_id.value)
                )
            assert await messages.list_messages(conversation.conversation_id) == (
                first.message,
                second.message,
            )
            async with db._sessions() as session:
                assert await session.scalar(select(func.count()).select_from(ChatTurnRecord)) == 2
                assert (
                    await session.scalar(select(func.count()).select_from(ChatMessageRecord)) == 2
                )
                assert (
                    await session.scalar(select(func.count()).select_from(ObservationRecord)) == 0
                )
                assert (
                    await session.scalar(select(func.count()).select_from(KnowledgeAssertionRecord))
                    == 0
                )
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(WorldEventRecord)
                        .where(WorldEventRecord.event_type == "ChatMessageSent")
                    )
                    == 0
                )
        finally:
            await db.close()
        reopened = Database(tmp_path)
        await reopened.initialize()
        try:
            restored = ChatMessageService(
                reopened.chat_message_store(),
                PlayerEventFeedService(reopened.player_event_feed_store()),
            )
            assert await restored.list_messages(conversation.conversation_id) == (
                first.message,
                second.message,
            )
            assert (
                await restored.send_player(request, conversation.conversation_id, "你好", 50_000)
                == first
            )
        finally:
            await reopened.close()

    asyncio.run(run())


def test_player_send_rejects_blank_or_unbounded_text_before_write(tmp_path):
    async def run():
        db = Database(tmp_path)
        await db.initialize()
        try:
            service = ChatMessageService(
                db.chat_message_store(), PlayerEventFeedService(db.player_event_feed_store())
            )
            conversation = ConversationId(WorldId(uuid4()), uuid4())
            for text, ceiling in (("   ", 50000), ("hello", 0), ("a" * 65537, 50000)):
                with pytest.raises(ValueError):
                    await service.send_player(RequestId(uuid4()), conversation, text, ceiling)
        finally:
            await db.close()

    asyncio.run(run())


def test_chat_transcript_http_is_authenticated_and_bound_to_selected_world_player(tmp_path):
    db = Database(tmp_path)
    clock = SystemWallClock()
    handler = CommandHandler(
        db.unit_of_work,
        clock,
        world_time_source=EffectiveWorldTimeSource(clock, SystemMonotonicClock()),
    )
    players = PlayerEventFeedService(db.player_event_feed_store())
    messages = ChatMessageService(db.chat_message_store(), players)
    worlds = (WorldId(uuid4()), WorldId(uuid4()))

    async def setup():
        await db.initialize()
        for world in worlds:
            await handler.execute(
                CreateWorld(request_id=RequestId(uuid4()), world_id=world, name="世界")
            )

    asyncio.run(setup())
    app = create_app(
        RuntimeStatus("test", "generation"),
        ShutdownRequests(),
        "secret",
        lambda: None,
        StructuredLogger(io.StringIO()),
        chat_messages=messages,
    )
    path = f"/api/v1/worlds/{worlds[0].value}/conversations/{uuid4()}/messages"
    try:
        with TestClient(app, base_url="http://127.0.0.1") as client:
            assert client.get(path).status_code == 401
            headers = {"Authorization": "Bearer secret"}
            assert client.get(path, headers=headers).status_code == 409

            async def populate():
                await LocalPlayerOnboardingService(handler, players).start_at_home(worlds[0])
                imports = db.world_content_service()
                staged = await imports.prepare(worlds[0], "character", json_bytes(card_document()))
                card = await imports.commit(
                    worlds[0], staged.item.import_id, staged.item.reviewed_hash
                )
                conversation = await ChatConversationService(
                    db.chat_conversation_store(), imports, players, handler
                ).open_direct(worlds[0], card.import_id)
                sent = await messages.send_player(
                    RequestId(uuid4()), conversation.conversation_id, "仅当前玩家可见", 50_000
                )
                return conversation, sent

            conversation, sent = asyncio.run(populate())
            path = (
                f"/api/v1/worlds/{worlds[0].value}/conversations/"
                f"{conversation.conversation_id.value}/messages"
            )
            response = client.get(path, headers=headers)
            assert response.status_code == 200
            assert response.json() == [
                {
                    "message_id": str(sent.message.message_id.value),
                    "turn_id": str(sent.turn_id.value),
                    "conversation_id": str(conversation.conversation_id.value),
                    "position": 1,
                    "sender_kind": "player",
                    "sender_id": str(conversation.player_id.value),
                    "text": "仅当前玩家可见",
                    "created_at_utc": sent.message.created_at_utc.isoformat(),
                }
            ]
            timestamp = datetime.fromisoformat(response.json()[0]["created_at_utc"])
            assert timestamp.utcoffset() == timedelta(0)
            assert client.get(path, headers={"Authorization": "Bearer wrong"}).status_code == 401
            other_world_path = (
                f"/api/v1/worlds/{worlds[1].value}/conversations/"
                f"{conversation.conversation_id.value}/messages"
            )
            assert client.get(other_world_path, headers=headers).status_code == 409
            asyncio.run(LocalPlayerOnboardingService(handler, players).start_at_home(worlds[1]))
            assert client.get(other_world_path, headers=headers).status_code == 404
            assert "仅当前玩家可见" not in client.get(other_world_path, headers=headers).text
    finally:
        asyncio.run(db.close())
