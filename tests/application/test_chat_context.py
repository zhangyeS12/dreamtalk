"""Direct-chat context uses only the selected Player's accepted contact and transcript."""

import asyncio
import json
from uuid import uuid4

from card_fixtures import card_document, json_bytes
from livingworld.application.chat_context import DirectChatContextBuilder
from livingworld.application.chat_conversations import ChatConversationService
from livingworld.application.chat_messages import ChatMessageService
from livingworld.application.command_handler import CommandHandler
from livingworld.application.commands import CreateWorld
from livingworld.application.llm import MessageRole
from livingworld.application.local_profile import LocalProfile
from livingworld.application.player_event_feed import PlayerEventFeedService
from livingworld.application.player_onboarding import LocalPlayerOnboardingService
from livingworld.application.simulation_clock import EffectiveWorldTimeSource, SystemMonotonicClock
from livingworld.domain.contracts import RequestId
from livingworld.domain.identifiers import WorldId
from livingworld.infrastructure.clock import SystemWallClock
from livingworld.infrastructure.persistence import Database


def test_context_tracks_current_accepted_persona_and_only_own_chat(tmp_path):
    async def run():
        db = Database(tmp_path)
        try:
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
            profiles = db.local_profile_store()
            builder = DirectChatContextBuilder(conversations, messages, profiles)
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
            await imports.commit(other_world, foreign.item.import_id, foreign.item.reviewed_hash)
            conversation = await conversations.open_direct(world, card.import_id)
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
            assert context.messages[-1].content[0].text == "你好"
            rendered = "\n".join(item.content[0].text for item in context.messages)
            assert "OTHER_WORLD_PRIVATE_CARD" not in rendered
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
