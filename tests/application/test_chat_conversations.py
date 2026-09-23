import asyncio
from uuid import uuid4

import pytest
from card_fixtures import card_document, json_bytes
from livingworld.application.chat_conversations import ChatConversationService
from livingworld.application.command_handler import CommandHandler
from livingworld.application.commands import CreateWorld
from livingworld.application.errors import EntityNotFoundError
from livingworld.application.player_event_feed import PlayerEventFeedService
from livingworld.application.player_onboarding import LocalPlayerOnboardingService
from livingworld.application.simulation_clock import EffectiveWorldTimeSource, SystemMonotonicClock
from livingworld.domain.contracts import RequestId
from livingworld.domain.identifiers import WorldId
from livingworld.infrastructure.clock import SystemWallClock
from livingworld.infrastructure.persistence import Database
from livingworld.infrastructure.persistence.models import (
    CharacterRecord,
    ChatConversationRecord,
    ChatParticipantRecord,
    WorldEventRecord,
)
from sqlalchemy import func, select


def test_open_contact_is_lazy_idempotent_world_scoped_and_durable(tmp_path):
    async def run():
        db = Database(tmp_path)
        await db.initialize()
        clock = SystemWallClock()
        source_clock = EffectiveWorldTimeSource(clock, SystemMonotonicClock())
        handler = CommandHandler(db.unit_of_work, clock, world_time_source=source_clock)
        players = PlayerEventFeedService(db.player_event_feed_store())
        imports = db.world_content_service()
        chats = ChatConversationService(db.chat_conversation_store(), imports, players, handler)
        worlds = (WorldId(uuid4()), WorldId(uuid4()))
        try:
            for world in worlds:
                await handler.execute(
                    CreateWorld(request_id=RequestId(uuid4()), world_id=world, name="世界")
                )
            source = json_bytes(card_document())
            staged = await imports.prepare(worlds[0], "character", source)
            card = await imports.commit(worlds[0], staged.item.import_id, staged.item.reviewed_hash)
            async with db._sessions() as session:
                assert await session.scalar(select(func.count()).select_from(CharacterRecord)) == 0
                assert (
                    await session.scalar(select(func.count()).select_from(ChatConversationRecord))
                    == 0
                )
            with pytest.raises(EntityNotFoundError, match="selected_player_required"):
                await chats.open_direct(worlds[0], card.import_id)
            assert await chats.list_for_world(worlds[0]) == ()
            await LocalPlayerOnboardingService(handler, players).start_at_home(worlds[0])
            first = await chats.open_direct(worlds[0], card.import_id)
            assert first == await chats.open_direct(worlds[0], card.import_id)
            assert await asyncio.gather(
                chats.open_direct(worlds[0], card.import_id),
                chats.open_direct(worlds[0], card.import_id),
            ) == [first, first]
            assert await chats.list_for_world(worlds[0]) == (first,)
            await LocalPlayerOnboardingService(handler, players).start_at_home(worlds[1])
            with pytest.raises(EntityNotFoundError, match="contact_not_found"):
                await chats.open_direct(worlds[1], card.import_id)
            async with db._sessions() as session:
                assert await session.scalar(select(func.count()).select_from(CharacterRecord)) == 1
                assert (
                    await session.scalar(select(func.count()).select_from(ChatConversationRecord))
                    == 1
                )
                assert (
                    await session.scalar(select(func.count()).select_from(ChatParticipantRecord))
                    == 1
                )
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(WorldEventRecord)
                        .where(WorldEventRecord.event_type == "CharacterCreated")
                    )
                    == 1
                )
            revised = card_document()
            revised["data"]["name"] = "更新后的角色"
            replacement = await imports.prepare(
                worlds[0], "character", json_bytes(revised), replaces_import_id=card.import_id
            )
            changed = await imports.commit(
                worlds[0], replacement.item.import_id, replacement.item.reviewed_hash
            )
            updated_conversation = await chats.open_direct(worlds[0], changed.import_id)
            assert updated_conversation.conversation_id == first.conversation_id
            assert updated_conversation.character_id == first.character_id
            assert updated_conversation.character_name == "更新后的角色"
            assert await chats.list_for_world(worlds[0]) == (updated_conversation,)
        finally:
            await db.close()

        reopened = Database(tmp_path)
        await reopened.initialize()
        try:
            restored = ChatConversationService(
                reopened.chat_conversation_store(),
                reopened.world_content_service(),
                PlayerEventFeedService(reopened.player_event_feed_store()),
                CommandHandler(reopened.unit_of_work, clock, world_time_source=source_clock),
            )
            assert await restored.list_for_world(worlds[0]) == (updated_conversation,)
            assert await restored.open_direct(worlds[0], changed.import_id) == updated_conversation
        finally:
            await reopened.close()

    asyncio.run(run())


def test_chat_http_requires_session_and_selected_player(tmp_path):
    import io

    from fastapi.testclient import TestClient
    from livingworld.adapters.http.app import create_app
    from livingworld.application.runtime import RuntimeStatus, ShutdownRequests
    from livingworld.infrastructure.logging import StructuredLogger

    db = Database(tmp_path)
    world = WorldId(uuid4())
    clock = SystemWallClock()
    source_clock = EffectiveWorldTimeSource(clock, SystemMonotonicClock())
    handler = CommandHandler(db.unit_of_work, clock, world_time_source=source_clock)
    imports = db.world_content_service()
    players = PlayerEventFeedService(db.player_event_feed_store())

    async def setup():
        await db.initialize()
        await handler.execute(
            CreateWorld(request_id=RequestId(uuid4()), world_id=world, name="世界")
        )
        staged = await imports.prepare(world, "character", json_bytes(card_document()))
        return await imports.commit(world, staged.item.import_id, staged.item.reviewed_hash)

    card = asyncio.run(setup())
    app = create_app(
        RuntimeStatus("test", "generation"),
        ShutdownRequests(),
        "secret",
        lambda: None,
        StructuredLogger(io.StringIO()),
        chat_conversations=ChatConversationService(
            db.chat_conversation_store(), imports, players, handler
        ),
    )
    path = f"/api/v1/worlds/{world.value}/conversations"
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.get(path).status_code == 401
        headers = {"Authorization": "Bearer secret"}
        assert client.get(path, headers=headers).json() == []
        assert client.post(path + f"/direct/{card.import_id}", headers=headers).status_code == 409
        asyncio.run(LocalPlayerOnboardingService(handler, players).start_at_home(world))
        first = client.post(path + f"/direct/{card.import_id}", headers=headers)
        assert first.status_code == 200
        assert (
            client.post(path + f"/direct/{card.import_id}", headers=headers).json() == first.json()
        )
        assert client.get(path, headers=headers).json() == [first.json()]
        assert client.get(path, headers={"Authorization": "Bearer wrong"}).status_code == 401
    asyncio.run(db.close())
