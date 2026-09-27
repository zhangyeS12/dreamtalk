"""Public background is explicit; imported lore stays hidden by default."""

import asyncio
import json
from uuid import uuid4

import pytest
from card_fixtures import card_document, json_bytes
from livingworld.application.chat_context import DirectChatContextBuilder
from livingworld.application.chat_conversations import ChatConversationService
from livingworld.application.chat_messages import ChatMessageService
from livingworld.application.command_handler import CommandHandler
from livingworld.application.commands import CreateWorld
from livingworld.application.errors import EntityNotFoundError
from livingworld.application.group_chat_context import GroupChatContextBuilder
from livingworld.application.player_event_feed import PlayerEventFeedService
from livingworld.application.player_onboarding import LocalPlayerOnboardingService
from livingworld.application.simulation_clock import EffectiveWorldTimeSource, SystemMonotonicClock
from livingworld.domain.content.models import LoreEntry
from livingworld.domain.contracts import RequestId
from livingworld.domain.identifiers import WorldId
from livingworld.infrastructure.clock import SystemWallClock
from livingworld.infrastructure.persistence import Database
from livingworld.infrastructure.persistence.models import KnowledgeAssertionRecord, WorldEventRecord
from lorebook_fixtures import book_document
from sqlalchemy import func, select


def test_common_lore_is_explicit_current_world_scoped_and_group_visible(tmp_path):
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
        chats = ChatConversationService(db.chat_conversation_store(), imports, players, handler)
        messages = ChatMessageService(db.chat_message_store(), players)
        world, other_world = WorldId(uuid4()), WorldId(uuid4())
        try:
            for identity in (world, other_world):
                await handler.execute(
                    CreateWorld(request_id=RequestId(uuid4()), world_id=identity, name="world")
                )
                await LocalPlayerOnboardingService(handler, players).start_at_home(identity)
            document = book_document()
            document["entries"]["0"]["content"] = "PUBLIC_CITY_BACKGROUND_CANARY"
            document["entries"]["1"]["content"] = "HIDDEN_PLOT_CANARY"
            document["entries"]["1"]["disable"] = False
            staged = await imports.prepare(world, "lorebook", json_bytes(document))
            book = await imports.commit(world, staged.item.import_id, staged.item.reviewed_hash)
            entries = [item for item in book.contents if isinstance(item, LoreEntry)]
            public = next(item for item in entries if "PUBLIC_CITY" in item.content)
            hidden = next(item for item in entries if "HIDDEN_PLOT" in item.content)
            assert hidden != public
            assert await imports.list_common_lore(world) == ()
            with pytest.raises(EntityNotFoundError):
                await imports.set_common_lore(
                    other_world, book.import_id, public.content_id.value, True
                )
            await imports.set_common_lore(world, book.import_id, public.content_id.value, True)
            await imports.set_common_lore(world, book.import_id, public.content_id.value, True)
            assert [item.entry.content for item in await imports.list_common_lore(world)] == [
                "PUBLIC_CITY_BACKGROUND_CANARY"
            ]
            assert await imports.list_common_lore(other_world) == ()
            reopened = Database(tmp_path)
            await reopened.initialize()
            try:
                assert [
                    item.entry.content
                    for item in await reopened.world_content_service().list_common_lore(world)
                ] == ["PUBLIC_CITY_BACKGROUND_CANARY"]
            finally:
                await reopened.close()

            cards = []
            for name in ("character_a", "character_b", "character_c"):
                document = card_document()
                document["data"]["name"] = name
                pending = await imports.prepare(world, "character", json_bytes(document))
                cards.append(
                    await imports.commit(world, pending.item.import_id, pending.item.reviewed_hash)
                )
            direct = await chats.open_direct(world, cards[0].import_id)
            group = await chats.create_group(
                world, RequestId(uuid4()), tuple(item.import_id for item in cards[:2])
            )
            direct_builder = DirectChatContextBuilder(
                chats,
                messages,
                db.local_profile_store(),
                db.character_memory_reader,
                imports.list_common_lore,
            )
            group_builder = GroupChatContextBuilder(
                chats,
                messages,
                db.local_profile_store(),
                db.character_memory_reader,
                imports.list_common_lore,
            )
            sent = await messages.send_player(
                RequestId(uuid4()), direct.conversation_id, "hello", 50000
            )
            direct_input = json.loads(
                (await direct_builder.build(sent)).messages[1].content[0].text
            )
            assert direct_input["common_world_background"] == [
                {"title": public.title, "content": "PUBLIC_CITY_BACKGROUND_CANARY"}
            ]
            assert "HIDDEN_PLOT_CANARY" not in json.dumps(direct_input)
            group_sent = await messages.send_group_player(
                RequestId(uuid4()), group.conversation_id, "大家好", 50000
            )
            claim = await messages.claim_group(group.conversation_id, group_sent.turn_id)
            await messages.complete_group_reply(
                claim, group.participants[0].character_id, 0, "我知道广场的传闻"
            )
            next_group_sent = await messages.send_group_player(
                RequestId(uuid4()), group.conversation_id, "继续聊", 50000
            )
            for participant in group.participants:
                reply = await group_builder.build_reply(next_group_sent, participant.character_id)
                payload = json.loads(reply.messages[1].content[0].text)
                assert payload["common_world_background"][0]["content"] == (
                    "PUBLIC_CITY_BACKGROUND_CANARY"
                )
                assert [item["text"] for item in payload["transcript"]] == [
                    "大家好",
                    "我知道广场的传闻",
                    "继续聊",
                ]
                assert "HIDDEN_PLOT_CANARY" not in reply.messages[1].content[0].text
            second_direct = await chats.open_direct(world, cards[1].import_id)
            private_send = await messages.send_player(
                RequestId(uuid4()), second_direct.conversation_id, "你听到了什么？", 50000
            )
            private_input = json.loads(
                (await direct_builder.build(private_send)).messages[1].content[0].text
            )
            assert [item["text"] for item in private_input["group_messages_seen"]] == [
                "大家好",
                "我知道广场的传闻",
                "继续聊",
            ]
            assert all(
                item["conversation_id"] == str(group.conversation_id.value)
                for item in private_input["group_messages_seen"]
            )
            outsider = await chats.open_direct(world, cards[2].import_id)
            outsider_send = await messages.send_player(
                RequestId(uuid4()), outsider.conversation_id, "你听到了什么？", 50000
            )
            outsider_input = json.loads(
                (await direct_builder.build(outsider_send)).messages[1].content[0].text
            )
            assert outsider_input["group_messages_seen"] == []
            await imports.set_common_lore(world, book.import_id, public.content_id.value, False)
            hidden_send = await messages.send_player(
                RequestId(uuid4()), direct.conversation_id, "再聊", 50000
            )
            hidden_input = json.loads(
                (await direct_builder.build(hidden_send)).messages[1].content[0].text
            )
            assert hidden_input["common_world_background"] == []
            await imports.set_common_lore(world, book.import_id, public.content_id.value, True)
            async with db._sessions() as session:
                assert (
                    await session.scalar(select(func.count()).select_from(KnowledgeAssertionRecord))
                    == 0
                )
                initial_events = await session.scalar(
                    select(func.count()).select_from(WorldEventRecord)
                )
            assert initial_events is not None
            replacement_document = book_document()
            replacement_document["entries"]["0"]["content"] = "REPLACEMENT_BACKGROUND_CANARY"
            replacement = await imports.prepare(
                world, "lorebook", json_bytes(replacement_document), book.import_id
            )
            await imports.commit(world, replacement.item.import_id, replacement.item.reviewed_hash)
            assert await imports.list_common_lore(world) == ()
            with pytest.raises(EntityNotFoundError):
                await imports.set_common_lore(world, book.import_id, public.content_id.value, True)
            assert await imports.list_common_lore(world) == ()
            async with db._sessions() as session:
                assert (
                    await session.scalar(select(func.count()).select_from(WorldEventRecord))
                    == initial_events
                )
        finally:
            await db.close()

    asyncio.run(run())
