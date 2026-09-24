"""Player sends are durable and idempotent without starting a model call."""

import asyncio
from uuid import uuid4

import pytest
from card_fixtures import card_document, json_bytes
from livingworld.application.chat_conversations import ChatConversationService
from livingworld.application.chat_messages import ChatMessageService
from livingworld.application.command_handler import CommandHandler
from livingworld.application.commands import CreateWorld
from livingworld.application.errors import EntityNotFoundError, IdempotencyConflictError
from livingworld.application.player_event_feed import PlayerEventFeedService
from livingworld.application.player_onboarding import LocalPlayerOnboardingService
from livingworld.application.simulation_clock import EffectiveWorldTimeSource, SystemMonotonicClock
from livingworld.domain.contracts import RequestId
from livingworld.domain.identifiers import ConversationId, WorldId
from livingworld.infrastructure.clock import SystemWallClock
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
