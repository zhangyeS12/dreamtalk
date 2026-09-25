"""A claimed direct turn may commit one reply without repeating provider work."""

import asyncio
from dataclasses import replace
from uuid import uuid4

import pytest
from card_fixtures import card_document, json_bytes
from livingworld.application.chat_conversations import ChatConversationService
from livingworld.application.chat_messages import ChatMessageService
from livingworld.application.command_handler import CommandHandler
from livingworld.application.commands import CreateWorld
from livingworld.application.errors import (
    ChatTurnUnavailableError,
    EntityNotFoundError,
    IdempotencyConflictError,
)
from livingworld.application.player_event_feed import PlayerEventFeedService
from livingworld.application.player_onboarding import LocalPlayerOnboardingService
from livingworld.application.simulation_clock import EffectiveWorldTimeSource, SystemMonotonicClock
from livingworld.domain.contracts import RequestId
from livingworld.domain.identifiers import CharacterId, ChatTurnId, WorldId
from livingworld.infrastructure.clock import SystemWallClock
from livingworld.infrastructure.persistence import Database
from livingworld.infrastructure.persistence.models import (
    ChatMessageRecord,
    ChatTurnDispatchRecord,
    KnowledgeAssertionRecord,
    ObservationRecord,
    WorldEventRecord,
)
from sqlalchemy import func, select


async def _setup(db):
    await db.initialize()
    clock = SystemWallClock()
    handler = CommandHandler(
        db.unit_of_work,
        clock,
        world_time_source=EffectiveWorldTimeSource(clock, SystemMonotonicClock()),
    )
    players = PlayerEventFeedService(db.player_event_feed_store())
    world = WorldId(uuid4())
    await handler.execute(CreateWorld(request_id=RequestId(uuid4()), world_id=world, name="世界"))
    await LocalPlayerOnboardingService(handler, players).start_at_home(world)
    imports = db.world_content_service()
    staged = await imports.prepare(world, "character", json_bytes(card_document()))
    card = await imports.commit(world, staged.item.import_id, staged.item.reviewed_hash)
    conversation = await ChatConversationService(
        db.chat_conversation_store(), imports, players, handler
    ).open_direct(world, card.import_id)
    messages = ChatMessageService(db.chat_message_store(), players)
    sent = await messages.send_player(
        RequestId(uuid4()), conversation.conversation_id, "你好", 50000
    )
    return conversation, messages, sent


def test_direct_reply_claim_is_once_only_and_completion_is_idempotent(tmp_path):
    async def run():
        db = Database(tmp_path)
        try:
            conversation, messages, sent = await _setup(db)
            async with db._sessions() as session:
                events_before = await session.scalar(
                    select(func.count()).select_from(WorldEventRecord)
                )
            claimed = await asyncio.gather(
                messages.claim_direct(conversation.conversation_id, sent.turn_id),
                messages.claim_direct(conversation.conversation_id, sent.turn_id),
                return_exceptions=True,
            )
            claims = [item for item in claimed if not isinstance(item, Exception)]
            errors = [item for item in claimed if isinstance(item, Exception)]
            assert len(claims) == len(errors) == 1
            assert isinstance(errors[0], ChatTurnUnavailableError)
            claim = claims[0]
            assert claim.player_message == sent.message
            assert claim.character_id == conversation.character_id
            assert claim.token_ceiling == 50000
            assert "你好" not in repr(claim)
            with pytest.raises(ValueError, match="chat_reply_invalid"):
                await messages.complete_direct(claim, "  ")
            with pytest.raises(ChatTurnUnavailableError, match="chat_turn_claim_invalid"):
                await messages.complete_direct(
                    replace(claim, character_id=CharacterId(claim.turn_id.world_id, uuid4())),
                    "假的回复",
                )
            with pytest.raises(ChatTurnUnavailableError, match="chat_turn_claim_invalid"):
                await messages.complete_direct(replace(claim, token_ceiling=60000), "假的回复")
            reply = await messages.complete_direct(claim, "你好，今天想聊什么？")
            assert reply.position == 2
            assert reply.sender_id == conversation.character_id
            assert reply.turn_id == sent.turn_id
            assert await messages.complete_direct(claim, "你好，今天想聊什么？") == reply
            with pytest.raises(IdempotencyConflictError, match="chat_reply_conflict"):
                await messages.complete_direct(claim, "不同的回复")
            assert await messages.list_messages(conversation.conversation_id) == (
                sent.message,
                reply,
            )
            async with db._sessions() as session:
                assert (
                    await session.scalar(select(func.count()).select_from(ChatTurnDispatchRecord))
                    == 1
                )
                assert (
                    await session.scalar(select(func.count()).select_from(ChatMessageRecord)) == 2
                )
                assert (
                    await session.scalar(select(func.count()).select_from(WorldEventRecord))
                    == events_before
                )
                assert (
                    await session.scalar(select(func.count()).select_from(ObservationRecord)) == 0
                )
                assert (
                    await session.scalar(select(func.count()).select_from(KnowledgeAssertionRecord))
                    == 0
                )
        finally:
            await db.close()

    asyncio.run(run())


def test_interrupted_claim_survives_restart_without_reclaim_or_fake_reply(tmp_path):
    async def run():
        db = Database(tmp_path)
        try:
            conversation, messages, sent = await _setup(db)
            await messages.claim_direct(conversation.conversation_id, sent.turn_id)
        finally:
            await db.close()
        reopened = Database(tmp_path)
        try:
            await reopened.initialize()
            players = PlayerEventFeedService(reopened.player_event_feed_store())
            messages = ChatMessageService(reopened.chat_message_store(), players)
            with pytest.raises(ChatTurnUnavailableError, match="chat_turn_already_claimed"):
                await messages.claim_direct(conversation.conversation_id, sent.turn_id)
            assert await messages.list_messages(conversation.conversation_id) == (sent.message,)
            with pytest.raises(EntityNotFoundError, match="chat_world_mismatch"):
                other_world = WorldId(uuid4())
                await messages.claim_direct(
                    conversation.conversation_id, ChatTurnId(other_world, sent.turn_id.value)
                )
        finally:
            await reopened.close()

    asyncio.run(run())
