import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from alembic import command
from card_fixtures import card_document, json_bytes
from livingworld.application.chat_conversations import ChatConversationService
from livingworld.application.chat_messages import ChatMessageService
from livingworld.application.command_handler import CommandHandler
from livingworld.application.commands import CreateWorld
from livingworld.application.player_event_feed import PlayerEventFeedService
from livingworld.application.player_onboarding import LocalPlayerOnboardingService
from livingworld.application.simulation_clock import EffectiveWorldTimeSource, SystemMonotonicClock
from livingworld.domain.contracts import RequestId
from livingworld.domain.identifiers import WorldId
from livingworld.infrastructure.clock import SystemWallClock
from livingworld.infrastructure.persistence import Database
from livingworld.infrastructure.persistence.migration import (
    CHAT_CONVERSATION_REVISION,
    CHAT_DISPATCH_REVISION,
    CHAT_MESSAGE_REVISION,
    HEAD_REVISION,
    WORLD_CONTENT_REVISION,
    _alembic_config,
)
from livingworld.infrastructure.persistence.models import ChatTurnDispatchRecord, WorldRecord
from sqlalchemy import text


def test_existing_world_content_database_upgrades_without_recreating_world(tmp_path):
    async def run():
        db = Database(tmp_path)
        world = WorldId(uuid4())
        try:
            async with db.engine.begin() as connection:
                await connection.run_sync(
                    lambda sync: command.upgrade(_alembic_config(sync), WORLD_CONTENT_REVISION)
                )
            clock = SystemWallClock()
            handler = CommandHandler(
                db.unit_of_work,
                clock,
                world_time_source=EffectiveWorldTimeSource(clock, SystemMonotonicClock()),
            )
            await handler.execute(
                CreateWorld(request_id=RequestId(uuid4()), world_id=world, name="保留的世界")
            )
            await db.initialize()
            async with db._sessions() as session:
                assert (await session.get(WorldRecord, world.value)).name == "保留的世界"
                assert (
                    await session.scalar(text("SELECT version_num FROM alembic_version"))
                    == HEAD_REVISION
                )
            await db.initialize()
        finally:
            await db.close()

    asyncio.run(run())


def test_existing_dispatch_claim_survives_group_completion_column_upgrade(tmp_path):
    async def run():
        db = Database(tmp_path)
        world = WorldId(uuid4())
        try:
            async with db.engine.begin() as connection:
                await connection.run_sync(
                    lambda sync: command.upgrade(_alembic_config(sync), CHAT_DISPATCH_REVISION)
                )
            clock = SystemWallClock()
            handler = CommandHandler(
                db.unit_of_work,
                clock,
                world_time_source=EffectiveWorldTimeSource(clock, SystemMonotonicClock()),
            )
            players = PlayerEventFeedService(db.player_event_feed_store())
            await handler.execute(
                CreateWorld(request_id=RequestId(uuid4()), world_id=world, name="保留的世界")
            )
            await LocalPlayerOnboardingService(handler, players).start_at_home(world)
            imports = db.world_content_service()
            staged = await imports.prepare(world, "character", json_bytes(card_document()))
            card = await imports.commit(world, staged.item.import_id, staged.item.reviewed_hash)
            conversation = await ChatConversationService(
                db.chat_conversation_store(), imports, players, handler
            ).open_direct(world, card.import_id)
            messages = ChatMessageService(db.chat_message_store(), players)
            sent = await messages.send_player(
                RequestId(uuid4()), conversation.conversation_id, "迁移前的消息", 50000
            )
            # The current ORM knows the new column, so seed an actual 0020 row
            # through its historical SQL shape before upgrading it.
            async with db.engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO chat_turn_dispatches "
                        "(world_id, turn_id, claimed_at_utc) "
                        "VALUES (:world_id, :turn_id, :claimed_at)"
                    ),
                    {
                        "world_id": world.value.hex,
                        "turn_id": sent.turn_id.value.hex,
                        "claimed_at": datetime.now(UTC).isoformat(),
                    },
                )
            await db.initialize()
            assert await messages.list_messages(conversation.conversation_id) == (sent.message,)
            assert (
                await messages.direct_turn(conversation.conversation_id, sent.turn_id)
            ).state == "claimed"
            async with db._sessions() as session:
                dispatch = await session.get(
                    ChatTurnDispatchRecord, (world.value, sent.turn_id.value)
                )
                assert dispatch is not None and dispatch.completed_at_utc is None
                assert (
                    await session.scalar(text("SELECT version_num FROM alembic_version"))
                    == HEAD_REVISION
                )
            await db.initialize()
        finally:
            await db.close()

    asyncio.run(run())


def test_existing_chat_identity_database_upgrades_without_replaying_conversations(tmp_path):
    async def run():
        db = Database(tmp_path)
        world = WorldId(uuid4())
        try:
            async with db.engine.begin() as connection:
                await connection.run_sync(
                    lambda sync: command.upgrade(_alembic_config(sync), CHAT_CONVERSATION_REVISION)
                )
            clock = SystemWallClock()
            handler = CommandHandler(
                db.unit_of_work,
                clock,
                world_time_source=EffectiveWorldTimeSource(clock, SystemMonotonicClock()),
            )
            await handler.execute(
                CreateWorld(request_id=RequestId(uuid4()), world_id=world, name="保留的会话世界")
            )
            await db.initialize()
            async with db._sessions() as session:
                assert (await session.get(WorldRecord, world.value)).name == "保留的会话世界"
                assert (
                    await session.scalar(text("SELECT version_num FROM alembic_version"))
                    == HEAD_REVISION
                )
            await db.initialize()
        finally:
            await db.close()

    asyncio.run(run())


def test_existing_player_message_survives_dispatch_claim_migration(tmp_path):
    async def run():
        db = Database(tmp_path)
        world = WorldId(uuid4())
        try:
            async with db.engine.begin() as connection:
                await connection.run_sync(
                    lambda sync: command.upgrade(_alembic_config(sync), CHAT_MESSAGE_REVISION)
                )
            clock = SystemWallClock()
            handler = CommandHandler(
                db.unit_of_work,
                clock,
                world_time_source=EffectiveWorldTimeSource(clock, SystemMonotonicClock()),
            )
            players = PlayerEventFeedService(db.player_event_feed_store())
            await handler.execute(
                CreateWorld(request_id=RequestId(uuid4()), world_id=world, name="保留的消息世界")
            )
            await LocalPlayerOnboardingService(handler, players).start_at_home(world)
            imports = db.world_content_service()
            staged = await imports.prepare(world, "character", json_bytes(card_document()))
            card = await imports.commit(world, staged.item.import_id, staged.item.reviewed_hash)
            conversation = await ChatConversationService(
                db.chat_conversation_store(), imports, players, handler
            ).open_direct(world, card.import_id)
            messages = ChatMessageService(db.chat_message_store(), players)
            sent = await messages.send_player(
                RequestId(uuid4()), conversation.conversation_id, "迁移前的消息", 50000
            )
            await db.initialize()
            assert await messages.list_messages(conversation.conversation_id) == (sent.message,)
            claim = await messages.claim_direct(conversation.conversation_id, sent.turn_id)
            assert claim.player_message == sent.message
            async with db._sessions() as session:
                assert (
                    await session.get(ChatTurnDispatchRecord, (world.value, sent.turn_id.value))
                    is not None
                )
                assert (
                    await session.scalar(text("SELECT version_num FROM alembic_version"))
                    == HEAD_REVISION
                )
            await db.initialize()
        finally:
            await db.close()

    asyncio.run(run())
