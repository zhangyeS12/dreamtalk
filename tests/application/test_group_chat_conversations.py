"""Group membership and internal transcript writes stay durable and owner-scoped."""

import asyncio
import json
from dataclasses import replace
from uuid import uuid4

import pytest
from card_fixtures import card_document, json_bytes
from livingworld.application.chat_conversations import ChatConversationService
from livingworld.application.chat_messages import ChatMessageService
from livingworld.application.command_handler import CommandHandler
from livingworld.application.commands import AcquireKnowledge, AssertWorldTruth, CreateWorld
from livingworld.application.errors import (
    ChatTurnUnavailableError,
    EntityNotFoundError,
    IdempotencyConflictError,
)
from livingworld.application.group_chat_context import GroupChatContextBuilder
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
    WorldId,
)
from livingworld.domain.knowledge import ObservationChannel
from livingworld.domain.values import WorldTime
from livingworld.infrastructure.clock import SystemWallClock
from livingworld.infrastructure.persistence import Database
from livingworld.infrastructure.persistence.models import (
    CharacterRecord,
    ChatConversationRecord,
    ChatMessageRecord,
    ChatParticipantRecord,
    ChatTurnRecord,
    WorldEventRecord,
)
from sqlalchemy import func, select


def test_group_creation_is_durable_idempotent_and_world_scoped(tmp_path):
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
            for item in (world, other_world):
                await handler.execute(
                    CreateWorld(request_id=RequestId(uuid4()), world_id=item, name="世界")
                )
            cards = []
            for name in ("角色甲", "角色乙"):
                document = card_document()
                document["data"]["name"] = name
                staged = await imports.prepare(world, "character", json_bytes(document))
                cards.append(
                    await imports.commit(world, staged.item.import_id, staged.item.reviewed_hash)
                )
            request = RequestId(uuid4())
            with pytest.raises(EntityNotFoundError, match="selected_player_required"):
                await chats.create_group(world, request, tuple(card.import_id for card in cards))
            await LocalPlayerOnboardingService(handler, players).start_at_home(world)
            await LocalPlayerOnboardingService(handler, players).start_at_home(other_world)
            with pytest.raises(EntityNotFoundError, match="contact_not_found"):
                await chats.create_group(
                    other_world, RequestId(uuid4()), tuple(card.import_id for card in cards)
                )
            group = await chats.create_group(
                world, request, tuple(card.import_id for card in cards)
            )
            assert len(group.participants) == 2
            assert {item.character_name for item in group.participants} == {"角色甲", "角色乙"}
            assert (
                await chats.create_group(
                    world, request, tuple(reversed([card.import_id for card in cards]))
                )
                == group
            )
            assert await chats.list_groups_for_world(world) == (group,)
            assert await chats.list_groups_for_world(other_world) == ()
            assert await chats.list_for_world(world) == ()
            third_document = card_document()
            third_document["data"]["name"] = "角色丙"
            staged_third = await imports.prepare(world, "character", json_bytes(third_document))
            third = await imports.commit(
                world, staged_third.item.import_id, staged_third.item.reviewed_hash
            )
            with pytest.raises(IdempotencyConflictError, match="group_request_conflict"):
                await chats.create_group(world, request, (cards[0].import_id, third.import_id))
            with pytest.raises(ValueError, match="group_members_invalid"):
                await chats.create_group(world, RequestId(uuid4()), (cards[0].import_id,) * 2)
            with pytest.raises(ChatTurnUnavailableError, match="group_turn_unavailable"):
                await messages.send_player(
                    RequestId(uuid4()), group.conversation_id, "还不能发群聊", 1000
                )
            async with db._sessions() as session:
                assert (
                    await session.scalar(select(func.count()).select_from(ChatConversationRecord))
                    == 1
                )
                assert (
                    await session.scalar(select(func.count()).select_from(ChatParticipantRecord))
                    == 2
                )
                assert await session.scalar(select(func.count()).select_from(CharacterRecord)) == 2
                assert await session.scalar(select(func.count()).select_from(ChatTurnRecord)) == 0
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(WorldEventRecord)
                        .where(WorldEventRecord.event_type == "CharacterCreated")
                    )
                    == 2
                )
        finally:
            await db.close()
        reopened = Database(tmp_path)
        await reopened.initialize()
        try:
            restored = ChatConversationService(
                reopened.chat_conversation_store(),
                reopened.world_content_service(),
                PlayerEventFeedService(reopened.player_event_feed_store()),
                CommandHandler(
                    reopened.unit_of_work,
                    clock,
                    world_time_source=EffectiveWorldTimeSource(clock, SystemMonotonicClock()),
                ),
            )
            assert await restored.list_groups_for_world(world) == (group,)
        finally:
            await reopened.close()

    asyncio.run(run())


def test_group_api_requires_auth_and_rejects_undispatched_messages(tmp_path):
    import io

    from fastapi.testclient import TestClient
    from livingworld.adapters.http.app import create_app
    from livingworld.application.runtime import RuntimeStatus, ShutdownRequests
    from livingworld.infrastructure.logging import StructuredLogger

    db = Database(tmp_path)
    world = WorldId(uuid4())
    clock = SystemWallClock()
    handler = CommandHandler(
        db.unit_of_work,
        clock,
        world_time_source=EffectiveWorldTimeSource(clock, SystemMonotonicClock()),
    )
    players = PlayerEventFeedService(db.player_event_feed_store())
    imports = db.world_content_service()

    async def setup():
        await db.initialize()
        await handler.execute(
            CreateWorld(request_id=RequestId(uuid4()), world_id=world, name="世界")
        )
        await LocalPlayerOnboardingService(handler, players).start_at_home(world)
        ids = []
        for name in ("角色甲", "角色乙"):
            document = card_document()
            document["data"]["name"] = name
            staged = await imports.prepare(world, "character", json_bytes(document))
            committed = await imports.commit(
                world, staged.item.import_id, staged.item.reviewed_hash
            )
            ids.append(str(committed.import_id))
        return ids

    ids = asyncio.run(setup())
    app = create_app(
        RuntimeStatus("test", "generation"),
        ShutdownRequests(),
        "secret",
        lambda: None,
        StructuredLogger(io.StringIO()),
        chat_conversations=ChatConversationService(
            db.chat_conversation_store(), imports, players, handler
        ),
        chat_messages=ChatMessageService(db.chat_message_store(), players),
    )
    path = f"/api/v1/worlds/{world.value}/conversations"
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.post(path + "/groups", json={"import_ids": ids}).status_code == 401
        headers = {"Authorization": "Bearer secret", "X-Request-Id": str(uuid4())}
        first = client.post(path + "/groups", json={"import_ids": ids}, headers=headers)
        assert first.status_code == 200
        assert first.json()["kind"] == "group"
        assert len(first.json()["participants"]) == 2
        assert (
            client.post(path + "/groups", json={"import_ids": ids}, headers=headers).json()
            == first.json()
        )
        assert client.get(path, headers=headers).json() == []
        assert client.get(path + "/groups", headers=headers).json() == [first.json()]
        sent = client.post(
            path + f"/{first.json()['conversation_id']}/messages",
            json={"text": "你好", "token_ceiling": 1000},
            headers={**headers, "X-Request-Id": str(uuid4())},
        )
        assert sent.status_code == 409
        assert sent.json()["detail"] == "group_turn_unavailable"
    asyncio.run(db.close())


def test_internal_group_turn_claim_and_multi_reply_are_durable_and_idempotent(tmp_path):
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
            for item in (world, other_world):
                await handler.execute(
                    CreateWorld(request_id=RequestId(uuid4()), world_id=item, name="世界")
                )
            await LocalPlayerOnboardingService(handler, players).start_at_home(world)
            await LocalPlayerOnboardingService(handler, players).start_at_home(other_world)
            cards = []
            for name in ("角色甲", "角色乙"):
                document = card_document()
                document["data"]["name"] = name
                staged = await imports.prepare(world, "character", json_bytes(document))
                cards.append(
                    await imports.commit(world, staged.item.import_id, staged.item.reviewed_hash)
                )
            group = await chats.create_group(
                world, RequestId(uuid4()), tuple(card.import_id for card in cards)
            )
            current = await chats.current_group_characters(group.conversation_id)
            assert {persona.display_name for _, persona in current} == {"角色甲", "角色乙"}
            replacement = card_document()
            replacement["data"]["name"] = "角色甲新版"
            staged = await imports.prepare(
                world, "character", json_bytes(replacement), cards[0].import_id
            )
            await imports.commit(world, staged.item.import_id, staged.item.reviewed_hash)
            updated = await chats.current_group_characters(group.conversation_id)
            assert {persona.display_name for _, persona in updated} == {"角色甲新版", "角色乙"}
            assert tuple(participant.character_id for participant, _ in updated) == tuple(
                participant.character_id for participant, _ in current
            )
            with pytest.raises(EntityNotFoundError, match="conversation_not_found"):
                await chats.current_group_characters(
                    ConversationId(other_world, group.conversation_id.value)
                )
            async with db._sessions() as session:
                event_count = await session.scalar(
                    select(func.count()).select_from(WorldEventRecord)
                )
            request = RequestId(uuid4())
            sent = await messages.send_group_player(request, group.conversation_id, "大家好", 5000)
            assert (
                await messages.group_turn(group.conversation_id, sent.turn_id)
            ).state == "pending"
            assert (
                await messages.send_group_player(request, group.conversation_id, "大家好", 5000)
                == sent
            )
            with pytest.raises(IdempotencyConflictError, match="chat_request_conflict"):
                await messages.send_group_player(request, group.conversation_id, "不同内容", 5000)
            # Even a matching public retry cannot bypass the direct-only endpoint boundary.
            with pytest.raises(ChatTurnUnavailableError, match="group_turn_unavailable"):
                await messages.send_player(request, group.conversation_id, "大家好", 5000)
            with pytest.raises(EntityNotFoundError, match="chat_world_mismatch"):
                await messages.claim_group(
                    group.conversation_id, ChatTurnId(other_world, sent.turn_id.value)
                )
            preclaim_context = GroupChatContextBuilder(
                chats, messages, db.local_profile_store(), db.character_memory_reader
            )
            assert (
                json.loads(
                    (await preclaim_context.build_selection(sent)).messages[1].content[0].text
                )["transcript"][-1]["text"]
                == "大家好"
            )
            assert json.loads(
                (await preclaim_context.build_reply(sent, updated[0][0].character_id))
                .messages[1]
                .content[0]
                .text
            )["character"]["name"] in {"角色甲新版", "角色乙"}
            claim = await messages.claim_group(group.conversation_id, sent.turn_id)
            assert (
                await messages.group_turn(group.conversation_id, sent.turn_id)
            ).state == "claimed"
            assert set(claim.character_ids) == {
                participant.character_id for participant in group.participants
            }
            assert claim.player_message == sent.message
            with pytest.raises(ChatTurnUnavailableError, match="chat_turn_already_claimed"):
                await messages.claim_group(group.conversation_id, sent.turn_id)
            first_character, second_character = claim.character_ids
            truth = await handler.execute(
                AssertWorldTruth(
                    request_id=RequestId(uuid4()),
                    world_id=world,
                    assertion_id=KnowledgeAssertionId(world, uuid4()),
                    subject="garden",
                    predicate="state",
                    value="open",
                    valid_from=WorldTime(0),
                )
            )
            for character_id, content in (
                (first_character, "FIRST_PRIVATE_MEMORY_CANARY"),
                (second_character, "SECOND_PRIVATE_MEMORY_CANARY"),
            ):
                learned = await handler.execute(
                    AcquireKnowledge(
                        request_id=RequestId(uuid4()),
                        world_id=world,
                        assertion_id=KnowledgeAssertionId(world, uuid4()),
                        receiver_id=character_id,
                        source_assertion_id=truth.entity_reference,
                        channel=ObservationChannel.TOLD,
                    )
                )
                await EpisodicMemoryService(
                    db.unit_of_work,
                    clock,
                    world_time_source=EffectiveWorldTimeSource(clock, SystemMonotonicClock()),
                ).execute(
                    RecordEpisodicMemory(
                        request_id=RequestId(uuid4()),
                        world_id=world,
                        owner_character_id=character_id,
                        source_observation_ids=(learned.observation_id,),
                        content=content,
                    )
                )
            async with db._sessions() as session:
                event_count = await session.scalar(
                    select(func.count()).select_from(WorldEventRecord)
                )
            profiles = db.local_profile_store()
            await profiles.save(LocalProfile("通用姓名", "喜欢散步"))
            await profiles.save(LocalProfile("世界身份", "在这里是旅人"), world)
            context = GroupChatContextBuilder(chats, messages, profiles, db.character_memory_reader)
            participants = tuple(
                (participant.character_id, persona) for participant, persona in updated
            )
            named = next(
                identity
                for identity, persona in participants
                if persona.display_name == "角色甲新版"
            )
            assert context.explicit_target("你好 @角色甲新版！", participants) == named
            assert context.explicit_target("你好", participants) is None
            duplicate_name = replace(
                participants[1][1], display_name=participants[0][1].display_name
            )
            with pytest.raises(ValueError, match="group_mention_ambiguous"):
                context.explicit_target(
                    f"@{participants[0][1].display_name}",
                    (participants[0], (participants[1][0], duplicate_name)),
                )
            selection = await context.build_selection(claim)
            selection_data = json.loads(selection.messages[1].content[0].text)
            assert {item["name"] for item in selection_data["participants"]} == {
                "角色甲新版",
                "角色乙",
            }
            assert "PRIVATE_MEMORY_CANARY" not in repr(selection)
            assert "PRIVATE_MEMORY_CANARY" not in selection.messages[1].content[0].text
            first_context = await context.build_reply(claim, first_character)
            first_data = json.loads(first_context.messages[1].content[0].text)
            assert [item["content"] for item in first_data["character_memories"]] == [
                "FIRST_PRIVATE_MEMORY_CANARY"
            ]
            assert first_data["player"]["current_world"]["description"] == "在这里是旅人"
            assert "SECOND_PRIVATE_MEMORY_CANARY" not in first_context.messages[1].content[0].text
            first = await messages.complete_group_reply(claim, first_character, 0, "你好")
            later_selection = await context.build_selection(claim)
            assert (
                json.loads(later_selection.messages[1].content[0].text)["transcript"][-1]["text"]
                == "你好"
            )
            second_context = await context.build_reply(claim, second_character)
            second_data = json.loads(second_context.messages[1].content[0].text)
            assert [item["content"] for item in second_data["character_memories"]] == [
                "SECOND_PRIVATE_MEMORY_CANARY"
            ]
            assert "FIRST_PRIVATE_MEMORY_CANARY" not in second_context.messages[1].content[0].text
            assert await messages.complete_group_reply(claim, first_character, 0, "你好") == first
            with pytest.raises(IdempotencyConflictError, match="chat_reply_conflict"):
                await messages.complete_group_reply(claim, second_character, 0, "你好")
            with pytest.raises(ChatTurnUnavailableError, match="chat_reply_ordinal_gap"):
                await messages.complete_group_reply(claim, second_character, 2, "收到")
            with pytest.raises(ChatTurnUnavailableError, match="chat_turn_claim_invalid"):
                await messages.complete_group_reply(
                    claim, CharacterId(world, uuid4()), 1, "不在群里的角色"
                )
            second = await messages.complete_group_reply(claim, second_character, 1, "收到")
            finished = await messages.finish_group(claim)
            assert finished.state == "completed"
            assert finished.replies == (first, second)
            assert await messages.finish_group(claim) == finished
            with pytest.raises(ChatTurnUnavailableError, match="group_turn_completed"):
                await messages.complete_group_reply(claim, first_character, 2, "多余回复")
            assert [
                item.message_id for item in await messages.list_messages(group.conversation_id)
            ] == [
                sent.message.message_id,
                first.message_id,
                second.message_id,
            ]
            async with db._sessions() as session:
                assert await session.scalar(select(func.count()).select_from(ChatTurnRecord)) == 1
                assert (
                    await session.scalar(select(func.count()).select_from(ChatMessageRecord)) == 3
                )
                assert (
                    await session.scalar(select(func.count()).select_from(WorldEventRecord))
                    == event_count
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
            assert [
                item.message_id for item in await restored.list_messages(group.conversation_id)
            ] == [
                sent.message.message_id,
                first.message_id,
                second.message_id,
            ]
            with pytest.raises(ChatTurnUnavailableError, match="chat_turn_already_claimed"):
                await restored.claim_group(group.conversation_id, sent.turn_id)
            assert await restored.complete_group_reply(claim, second_character, 1, "收到") == second
            assert (await restored.group_turn(group.conversation_id, sent.turn_id)) == finished
        finally:
            await reopened.close()

    asyncio.run(run())
