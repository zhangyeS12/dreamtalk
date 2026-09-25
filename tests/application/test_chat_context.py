"""Direct-chat context uses only the selected Player's accepted contact and transcript."""

import asyncio
import json
from datetime import UTC, datetime
from uuid import uuid4

from card_fixtures import card_document, json_bytes
from livingworld.application.chat_context import DirectChatContextBuilder
from livingworld.application.chat_conversations import ChatConversationService
from livingworld.application.chat_messages import ChatMessage, ChatMessageService
from livingworld.application.command_handler import CommandHandler
from livingworld.application.commands import AcquireKnowledge, AssertWorldTruth, CreateWorld
from livingworld.application.llm import MessageRole
from livingworld.application.local_profile import LocalProfile
from livingworld.application.memory import EpisodicMemoryService, RecordEpisodicMemory
from livingworld.application.player_event_feed import PlayerEventFeedService
from livingworld.application.player_onboarding import LocalPlayerOnboardingService
from livingworld.application.simulation_clock import EffectiveWorldTimeSource, SystemMonotonicClock
from livingworld.domain.contracts import RequestId
from livingworld.domain.identifiers import (
    CharacterId,
    ChatTurnId,
    ConversationId,
    KnowledgeAssertionId,
    MessageId,
    PlayerId,
    WorldId,
)
from livingworld.domain.knowledge import ObservationChannel
from livingworld.domain.values import WorldTime
from livingworld.infrastructure.clock import SystemWallClock
from livingworld.infrastructure.persistence import Database


def test_context_tracks_current_accepted_persona_and_only_own_chat(tmp_path):
    async def run():
        db = Database(tmp_path)
        try:
            await db.initialize()
            clock = SystemWallClock()
            source_clock = EffectiveWorldTimeSource(clock, SystemMonotonicClock())
            handler = CommandHandler(
                db.unit_of_work,
                clock,
                world_time_source=source_clock,
            )
            players = PlayerEventFeedService(db.player_event_feed_store())
            imports = db.world_content_service()
            conversations = ChatConversationService(
                db.chat_conversation_store(), imports, players, handler
            )
            messages = ChatMessageService(db.chat_message_store(), players)
            profiles = db.local_profile_store()
            builder = DirectChatContextBuilder(
                conversations, messages, profiles, db.character_memory_reader
            )
            world = WorldId(uuid4())
            other_world = WorldId(uuid4())
            for identity in (world, other_world):
                await handler.execute(
                    CreateWorld(request_id=RequestId(uuid4()), world_id=identity, name="世界")
                )
                await LocalPlayerOnboardingService(handler, players).start_at_home(identity)
            await profiles.save(LocalProfile("通用姓名", "喜欢散步"))
            await profiles.save(LocalProfile("世界身份", "在这里是图书管理员"), world)
            card_data = card_document()
            original = await imports.prepare(world, "character", json_bytes(card_data))
            card = await imports.commit(world, original.item.import_id, original.item.reviewed_hash)
            foreign_data = card_document()
            foreign_data["data"]["description"] = "OTHER_WORLD_PRIVATE_CARD"
            foreign = await imports.prepare(other_world, "character", json_bytes(foreign_data))
            foreign_card = await imports.commit(
                other_world, foreign.item.import_id, foreign.item.reviewed_hash
            )
            conversation = await conversations.open_direct(world, card.import_id)
            foreign_conversation = await conversations.open_direct(
                other_world, foreign_card.import_id
            )
            second_card_data = card_document()
            second_card_data["data"]["name"] = "角色乙"
            staged_second = await imports.prepare(world, "character", json_bytes(second_card_data))
            second_card = await imports.commit(
                world, staged_second.item.import_id, staged_second.item.reviewed_hash
            )
            second_conversation = await conversations.open_direct(world, second_card.import_id)

            async def remember(identity, character_id, content):
                truth = await handler.execute(
                    AssertWorldTruth(
                        request_id=RequestId(uuid4()),
                        world_id=identity,
                        assertion_id=KnowledgeAssertionId(identity, uuid4()),
                        subject="garden",
                        predicate="state",
                        value="open",
                        valid_from=WorldTime(0),
                    )
                )
                learned = await handler.execute(
                    AcquireKnowledge(
                        request_id=RequestId(uuid4()),
                        world_id=identity,
                        assertion_id=KnowledgeAssertionId(identity, uuid4()),
                        receiver_id=character_id,
                        source_assertion_id=truth.entity_reference,
                        channel=ObservationChannel.TOLD,
                    )
                )
                await EpisodicMemoryService(
                    db.unit_of_work, clock, world_time_source=source_clock
                ).execute(
                    RecordEpisodicMemory(
                        request_id=RequestId(uuid4()),
                        world_id=identity,
                        owner_character_id=character_id,
                        source_observation_ids=(learned.observation_id,),
                        content=content,
                    )
                )

            await remember(world, conversation.character_id, "OWN_PRIVATE_MEMORY_CANARY")
            await remember(world, conversation.character_id, "X" * 9000)
            await remember(
                world,
                second_conversation.character_id,
                "OTHER_CHARACTER_PRIVATE_MEMORY_CANARY",
            )
            await remember(
                other_world,
                foreign_conversation.character_id,
                "OTHER_WORLD_PRIVATE_MEMORY_CANARY",
            )
            sent = await messages.send_player(
                RequestId(uuid4()), conversation.conversation_id, "你好", 50000
            )
            context = await builder.build(sent)
            assert [item.role for item in context.messages] == [
                MessageRole.SYSTEM,
                MessageRole.USER,
                MessageRole.USER,
            ]
            persona = json.loads(context.messages[1].content[0].text)
            assert persona["character"]["personality"] == "Curious"
            assert persona["player"]["general"]["description"] == "喜欢散步"
            assert persona["player"]["current_world"]["description"] == "在这里是图书管理员"
            assert [item["content"] for item in persona["character_memories"]] == [
                "OWN_PRIVATE_MEMORY_CANARY"
            ]
            assert context.messages[-1].content[0].text == "你好"
            rendered = "\n".join(item.content[0].text for item in context.messages)
            assert "OTHER_WORLD_PRIVATE_CARD" not in rendered
            assert "OTHER_WORLD_PRIVATE_MEMORY_CANARY" not in rendered
            assert "OTHER_CHARACTER_PRIVATE_MEMORY_CANARY" not in rendered
            assert "X" * 9000 not in rendered
            assert "ignore all previous instructions" not in rendered
            assert "你好" not in repr(context)

            changed = card_document()
            changed["data"]["name"] = "更新后的角色"
            changed["data"]["personality"] = "新的性格"
            replacement = await imports.prepare(
                world, "character", json_bytes(changed), replaces_import_id=card.import_id
            )
            await imports.commit(world, replacement.item.import_id, replacement.item.reviewed_hash)
            claim = await messages.claim_direct(conversation.conversation_id, sent.turn_id)
            await messages.complete_direct(claim, "欢迎回来")
            next_sent = await messages.send_player(
                RequestId(uuid4()), conversation.conversation_id, "接着聊", 50000
            )
            updated = await builder.build(next_sent)
            assert json.loads(updated.messages[1].content[0].text)["character"] == {
                **persona["character"],
                "name": "更新后的角色",
                "personality": "新的性格",
            }
            assert [item.role for item in updated.messages[2:]] == [
                MessageRole.USER,
                MessageRole.ASSISTANT,
                MessageRole.USER,
            ]
            assert [item.content[0].text for item in updated.messages[2:]] == [
                "你好",
                "欢迎回来",
                "接着聊",
            ]
        finally:
            await db.close()

    asyncio.run(run())


def test_context_window_keeps_current_send_and_complete_recent_turns():
    world = WorldId(uuid4())
    conversation = ConversationId(world, uuid4())
    player = PlayerId(world, uuid4())
    character = CharacterId(world, uuid4())
    old_turn, recent_turn, current_turn = (ChatTurnId(world, uuid4()) for _ in range(3))

    def message(turn, position, sender, text):
        return ChatMessage(
            MessageId(world, uuid4()),
            conversation,
            turn,
            position,
            sender,
            text,
            datetime.now(UTC),
        )

    old = message(old_turn, 1, player, "A" * 60_000)
    old_reply = message(old_turn, 2, character, "旧回复")
    recent = message(recent_turn, 3, player, "B" * 60_000)
    recent_reply = message(recent_turn, 4, character, "新回复")
    current = message(current_turn, 5, player, "最新问题")
    selected = DirectChatContextBuilder._recent_transcript(
        (old, old_reply, recent, recent_reply, current), current
    )
    assert selected == (recent, recent_reply, current)

    # A delayed response can interleave with another Player send. Keep each
    # selected turn intact, then restore the actual transcript order.
    overlapping = (
        message(old_turn, 1, player, "甲"),
        message(recent_turn, 2, player, "乙"),
        message(old_turn, 3, character, "回复甲"),
        current,
    )
    assert DirectChatContextBuilder._recent_transcript(overlapping, current) == overlapping
