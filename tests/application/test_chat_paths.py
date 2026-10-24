"""Synthetic transcript paths; no real model, application or user database."""

import asyncio
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import pytest
from card_fixtures import card_document, json_bytes
from livingworld.application.chat_conversations import ChatConversationService
from livingworld.application.chat_messages import ChatMessageService
from livingworld.application.chat_paths import ChatPathError, PathConfirm, PathDraft
from livingworld.application.command_handler import CommandHandler
from livingworld.application.commands import CreateWorld
from livingworld.application.player_event_feed import PlayerEventFeedService
from livingworld.application.player_onboarding import LocalPlayerOnboardingService
from livingworld.application.simulation_clock import EffectiveWorldTimeSource, SystemMonotonicClock
from livingworld.domain.contracts import RequestId
from livingworld.domain.identifiers import ChatTurnId, WorldId
from livingworld.infrastructure.clock import SystemWallClock
from livingworld.infrastructure.persistence import Database
from livingworld.infrastructure.persistence.chat_paths import SqlAlchemyChatPathStore
from livingworld.infrastructure.persistence.models import ChatMessageRecord, WorldEventRecord
from sqlalchemy import func, select


@asynccontextmanager
async def setup(path):
    db = Database(path)
    await db.initialize()
    clock = SystemWallClock()
    handler = CommandHandler(
        db.unit_of_work,
        clock,
        world_time_source=EffectiveWorldTimeSource(clock, SystemMonotonicClock()),
    )
    players = PlayerEventFeedService(db.player_event_feed_store())
    world = WorldId(uuid4())
    await handler.execute(
        CreateWorld(request_id=RequestId(uuid4()), world_id=world, name="Synthetic paths")
    )
    await LocalPlayerOnboardingService(handler, players).start_at_home(world)
    imports = db.world_content_service()
    staged = await imports.prepare(world, "character", json_bytes(card_document()))
    card = await imports.commit(world, staged.item.import_id, staged.item.reviewed_hash)
    conversation = await ChatConversationService(
        db.chat_conversation_store(), imports, players, handler
    ).open_direct(world, card.import_id)
    messages = ChatMessageService(db.chat_message_store(), players)
    paths = SqlAlchemyChatPathStore(db._sessions)
    try:
        yield db, conversation, messages, paths
    finally:
        await db.close()


async def mutate(paths, convo, action, **values):
    world, identity, player = (
        convo.conversation_id.world_id.value,
        convo.conversation_id.value,
        convo.player_id.value,
    )
    snapshot = await paths.snapshot(world, identity, player)
    draft = PathDraft(action=action, revision=snapshot["revision"], **values)
    preview = await paths.preview(world, identity, player, draft)
    request = PathConfirm(
        draft=draft, reviewed_hash=preview["reviewed_hash"], confirmed=True, request_id=uuid4()
    )
    return await paths.commit(world, identity, player, request), request


async def reply(messages, convo, text, answer):
    sent = await messages.send_player(RequestId(uuid4()), convo.conversation_id, text, 50000)
    claim = await messages.claim_direct(convo.conversation_id, sent.turn_id)
    result = await messages.complete_direct(claim, answer)
    return sent, result


def test_checkpoint_keeps_prefix_and_branch_is_independent(tmp_path):
    async def run():
        async with setup(tmp_path) as (db, convo, messages, paths):
            first, answer = await reply(messages, convo, "first question", "first answer")
            await reply(messages, convo, "old future", "old future answer")
            async with db._sessions() as session:
                events = await session.scalar(select(func.count()).select_from(WorldEventRecord))
            checkpoint, _ = await mutate(
                paths, convo, "checkpoint", message_id=answer.message_id.value, name="Before fork"
            )
            current = await paths.snapshot(
                convo.conversation_id.world_id.value,
                convo.conversation_id.value,
                convo.player_id.value,
            )
            assert current["active"]["kind"] == "main"
            await mutate(paths, convo, "switch", path_id=checkpoint["path_id"])
            assert [m.text for m in await messages.list_messages(convo.conversation_id)] == [
                "first question",
                "first answer",
            ]
            with pytest.raises(Exception, match="chat_checkpoint_read_only"):
                await messages.send_player(
                    RequestId(uuid4()), convo.conversation_id, "not writable", 50000
                )
            await mutate(
                paths, convo, "branch", message_id=answer.message_id.value, name="New direction"
            )
            await reply(messages, convo, "new future", "new answer")
            visible = await messages.list_messages(convo.conversation_id)
            assert [m.text for m in visible] == [
                "first question",
                "first answer",
                "new future",
                "new answer",
            ]
            await mutate(paths, convo, "switch", path_id=convo.conversation_id.value)
            assert [m.text for m in await messages.list_messages(convo.conversation_id)] == [
                "first question",
                "first answer",
                "old future",
                "old future answer",
            ]
            async with db._sessions() as session:
                assert (
                    await session.scalar(select(func.count()).select_from(WorldEventRecord))
                    == events
                )
            assert first.message.message_id == visible[0].message_id

    asyncio.run(run())


def test_edit_keeps_original_and_cuts_old_future_from_context(tmp_path):
    async def run():
        async with setup(tmp_path) as (db, convo, messages, paths):
            _, answer = await reply(messages, convo, "question", "original answer")
            await reply(messages, convo, "later question", "later answer")
            await mutate(
                paths, convo, "edit", message_id=answer.message_id.value, text="reviewed answer"
            )
            visible = await messages.list_messages(convo.conversation_id)
            assert [m.text for m in visible] == ["question", "reviewed answer"]
            async with db._sessions() as session:
                original = await session.get(
                    ChatMessageRecord,
                    (convo.conversation_id.world_id.value, answer.message_id.value),
                )
                assert original.text == "original answer"
            sent = await messages.send_player(
                RequestId(uuid4()), convo.conversation_id, "continue", 50000
            )
            context = await messages.context_messages(
                convo.conversation_id, sent.message, allow_current_replies=False
            )
            assert [m.text for m in context] == ["question", "reviewed answer", "continue"]

    asyncio.run(run())


def test_candidate_is_pending_once_and_old_reply_remains_selectable(tmp_path):
    async def run():
        async with setup(tmp_path) as (_, convo, messages, paths):
            _, original = await reply(messages, convo, "question", "answer one")
            result, request = await mutate(
                paths, convo, "candidate", message_id=original.message_id.value, token_ceiling=30000
            )
            world, identity, player = (
                convo.conversation_id.world_id.value,
                convo.conversation_id.value,
                convo.player_id.value,
            )
            assert await paths.commit(world, identity, player, request) == result
            assert [m.text for m in await messages.list_messages(convo.conversation_id)] == [
                "question"
            ]
            turn = ChatTurnId(convo.conversation_id.world_id, UUID(result["turn_id"]))
            claim = await messages.claim_direct(convo.conversation_id, turn)
            await messages.complete_direct(claim, "answer two")
            assert [m.text for m in await messages.list_messages(convo.conversation_id)] == [
                "question",
                "answer two",
            ]
            await mutate(paths, convo, "switch", path_id=identity)
            assert [m.text for m in await messages.list_messages(convo.conversation_id)] == [
                "question",
                "answer one",
            ]

    asyncio.run(run())


def test_preview_is_invalidated_by_a_new_message(tmp_path):
    async def run():
        async with setup(tmp_path) as (_, convo, messages, paths):
            _, answer = await reply(messages, convo, "question", "answer")
            world, identity, player = (
                convo.conversation_id.world_id.value,
                convo.conversation_id.value,
                convo.player_id.value,
            )
            draft = PathDraft(action="checkpoint", revision=0, message_id=answer.message_id.value)
            preview = await paths.preview(world, identity, player, draft)
            await messages.send_player(
                RequestId(uuid4()), convo.conversation_id, "new question", 50000
            )
            with pytest.raises(ChatPathError, match="chat_path_preview_changed"):
                await paths.commit(
                    world,
                    identity,
                    player,
                    PathConfirm(
                        draft=draft,
                        reviewed_hash=preview["reviewed_hash"],
                        confirmed=True,
                        request_id=uuid4(),
                    ),
                )

    asyncio.run(run())


def test_memories_follow_reply_origin_and_supersession_is_route_local(tmp_path):
    from livingworld.application.long_chat_memory import MemoryAnnotation

    async def run():
        async with setup(tmp_path) as (db, convo, messages, paths):
            memory = db.long_chat_memory_store()
            first = await messages.send_player(
                RequestId(uuid4()), convo.conversation_id, "I like tea", 50000
            )
            claim = await messages.claim_direct(convo.conversation_id, first.turn_id)
            answer = await messages.complete_direct(
                claim,
                "I remember tea",
                memories=(
                    MemoryAnnotation(
                        kind="preference",
                        topic="drink",
                        content="likes tea",
                        source="player",
                        quote="like tea",
                    ),
                ),
            )
            original = await memory.snapshot(
                convo.conversation_id, convo.player_id, convo.character_id
            )
            old_id = original["items"][0]["entry_id"]
            # Fork through the question only: player-source extraction belongs to the omitted reply.
            await mutate(paths, convo, "branch", message_id=first.message.message_id.value)
            assert (
                await memory.snapshot(convo.conversation_id, convo.player_id, convo.character_id)
            )["items"] == []
            await mutate(paths, convo, "switch", path_id=convo.conversation_id.value)
            await mutate(paths, convo, "branch", message_id=answer.message_id.value)
            second = await messages.send_player(
                RequestId(uuid4()), convo.conversation_id, "I prefer coffee now", 50000
            )
            claim = await messages.claim_direct(convo.conversation_id, second.turn_id)
            await messages.complete_direct(
                claim,
                "Coffee instead",
                memories=(
                    MemoryAnnotation(
                        kind="preference",
                        topic="drink",
                        content="likes coffee",
                        source="player",
                        quote="prefer coffee",
                        replaces=old_id,
                    ),
                ),
            )
            branch = await memory.snapshot(
                convo.conversation_id, convo.player_id, convo.character_id
            )
            assert {item["content"] for item in branch["items"] if item["state"] == "active"} == {
                "likes coffee"
            }
            await mutate(paths, convo, "switch", path_id=convo.conversation_id.value)
            restored = await memory.snapshot(
                convo.conversation_id, convo.player_id, convo.character_id
            )
            assert [(item["content"], item["state"]) for item in restored["items"]] == [
                ("likes tea", "active")
            ]

    asyncio.run(run())


def test_group_candidate_replaces_whole_round_and_keeps_original(tmp_path):
    async def run():
        async with setup(tmp_path) as (db, direct, messages, paths):
            imports = db.world_content_service()
            data = card_document()
            data["data"]["name"] = "Second synthetic character"
            staged = await imports.prepare(
                direct.conversation_id.world_id, "character", json_bytes(data)
            )
            card = await imports.commit(
                direct.conversation_id.world_id, staged.item.import_id, staged.item.reviewed_hash
            )
            clock = SystemWallClock()
            players = PlayerEventFeedService(db.player_event_feed_store())
            handler = CommandHandler(
                db.unit_of_work,
                clock,
                world_time_source=EffectiveWorldTimeSource(clock, SystemMonotonicClock()),
            )
            group = await ChatConversationService(
                db.chat_conversation_store(), imports, players, handler
            ).create_group(
                direct.conversation_id.world_id,
                RequestId(uuid4()),
                (direct.root_import_id, card.import_id),
            )
            sent = await messages.send_group_player(
                RequestId(uuid4()), group.conversation_id, "group question", 50000
            )
            from unittest.mock import AsyncMock

            from livingworld.application.group_chat_context import GroupChatContextBuilder
            from test_advanced_lore import lore

            entry = lore("group background", meta={"constant": True, "sticky": 4})
            builder = GroupChatContextBuilder(
                ChatConversationService(db.chat_conversation_store(), imports, players, handler),
                messages,
                db.local_profile_store(),
                db.character_memory_reader,
                AsyncMock(return_value=(entry,)),
                lore_activation_reader=db.chat_lore_reader(),
            )
            context = await builder.build_reply(sent, group.participants[0].character_id)
            assert "group background" in context.messages[1].content[0].text
            assert context.layout.lore_commit is not None
            import json

            background = json.loads(context.messages[1].content[0].text)["common_world_background"]
            await context.layout.lore_commit(tuple(item["_lore_start_key"] for item in background))
            async with db._sessions() as session:
                from livingworld.infrastructure.persistence.chat_path_models import (
                    ChatLoreActivationRecord,
                )

                assert (
                    await session.scalar(select(func.count()).select_from(ChatLoreActivationRecord))
                    == 1
                )
            claim = await messages.claim_group(group.conversation_id, sent.turn_id)
            old = await messages.complete_group_reply(
                claim, group.participants[0].character_id, 0, "old first"
            )
            await messages.complete_group_reply(
                claim, group.participants[1].character_id, 1, "old second"
            )
            await messages.finish_group(claim)
            result, _ = await mutate(paths, group, "candidate", message_id=old.message_id.value)
            attempt = ChatTurnId(group.conversation_id.world_id, UUID(result["turn_id"]))
            claim = await messages.claim_group(group.conversation_id, attempt)
            await messages.complete_group_reply(
                claim, group.participants[1].character_id, 0, "new round"
            )
            await messages.finish_group(claim)
            assert [m.text for m in await messages.list_messages(group.conversation_id)] == [
                "group question",
                "new round",
            ]
            await mutate(paths, group, "switch", path_id=group.conversation_id.value)
            assert [m.text for m in await messages.list_messages(group.conversation_id)] == [
                "group question",
                "old first",
                "old second",
            ]

    asyncio.run(run())


def test_running_or_unknown_reply_blocks_changes_and_export_switch_is_rejected(tmp_path):
    from livingworld.application.errors import EntityNotFoundError
    from livingworld.infrastructure.persistence.chat_export import SqlAlchemyChatExportStore
    from livingworld.infrastructure.persistence.models import ChatReplyExecutionRecord

    async def run():
        async with setup(tmp_path) as (db, convo, messages, paths):
            sent, answer = await reply(messages, convo, "original question", "original answer")
            export = SqlAlchemyChatExportStore(db._sessions)
            saved = await export.snapshot(convo.conversation_id, convo.player_id, None)
            next_turn = await messages.send_player(
                RequestId(uuid4()), convo.conversation_id, "still running", 50000
            )
            await messages.claim_direct(convo.conversation_id, next_turn.turn_id)
            with pytest.raises(ChatPathError, match="chat_path_reply_running"):
                await mutate(paths, convo, "branch", message_id=answer.message_id.value)
            async with db._sessions() as session, session.begin():
                row = await session.get(
                    ChatReplyExecutionRecord,
                    (convo.conversation_id.world_id.value, next_turn.turn_id.value),
                )
                row.state = "unknown"
            with pytest.raises(ChatPathError, match="chat_path_reply_running"):
                await mutate(paths, convo, "branch", message_id=sent.message.message_id.value)
            async with db._sessions() as session, session.begin():
                row = await session.get(
                    ChatReplyExecutionRecord,
                    (convo.conversation_id.world_id.value, next_turn.turn_id.value),
                )
                row.state = "failed"
            await mutate(paths, convo, "branch", message_id=answer.message_id.value)
            with pytest.raises(EntityNotFoundError, match="export_transcript_changed"):
                await export.page(saved, 0)

    asyncio.run(run())


def test_0056_upgrade_preserves_all_original_rows_and_backfills_memory_origin(tmp_path):
    from livingworld.application.long_chat_memory import MemoryAnnotation
    from livingworld.infrastructure.persistence.migration import (
        CHARACTER_EVOLUTION_TABLES,
        CHAT_PATH_TABLES,
        HEAD_REVISION,
    )
    from sqlalchemy import text

    async def run():
        async with setup(tmp_path) as (db, convo, messages, _):
            sent = await messages.send_player(
                RequestId(uuid4()), convo.conversation_id, "legacy preference", 50000
            )
            claim = await messages.claim_direct(convo.conversation_id, sent.turn_id)
            answer = await messages.complete_direct(
                claim,
                "legacy answer",
                memories=(
                    MemoryAnnotation(
                        kind="preference",
                        topic="legacy",
                        content="preserved preference",
                        source="player",
                        quote="legacy preference",
                    ),
                ),
            )
            async with db.engine.begin() as connection:
                # 0057 only adds tables. Removing those tables recreates the
                # exact previous schema while retaining synthetic legacy content.
                for name in (
                    "chat_lore_activations",
                    "chat_memory_origins",
                    "chat_path_operations",
                    "chat_path_turns",
                    "chat_path_messages",
                    "chat_path_states",
                    "chat_paths",
                ):
                    assert name in CHAT_PATH_TABLES
                    await connection.execute(text(f'DROP TABLE "{name}"'))
                for name in CHARACTER_EVOLUTION_TABLES:
                    await connection.execute(text(f'DROP TABLE "{name}"'))
                await connection.execute(
                    text("UPDATE alembic_version SET version_num='0056_player_cards'")
                )
                before = (
                    await connection.execute(text("SELECT * FROM chat_messages ORDER BY position"))
                ).all()
                old_memories = (
                    await connection.execute(text("SELECT * FROM long_chat_memories"))
                ).all()
            await db.initialize()
            await db.initialize()
            async with db.engine.connect() as connection:
                assert (
                    await connection.execute(text("SELECT * FROM chat_messages ORDER BY position"))
                ).all() == before
                assert (await connection.execute(text("PRAGMA foreign_key_check"))).all() == []
                assert (
                    await connection.execute(text("SELECT * FROM long_chat_memories"))
                ).all() == old_memories
                assert (
                    await connection.scalar(text("SELECT message_id FROM chat_memory_origins"))
                    == answer.message_id.value.hex
                )
                assert (
                    await connection.scalar(text("SELECT version_num FROM alembic_version"))
                    == HEAD_REVISION
                )

    asyncio.run(run())


def test_summary_cannot_inherit_hidden_ancestors(tmp_path):
    import json
    from datetime import UTC, datetime

    from livingworld.infrastructure.persistence.conversation_memory import (
        ConversationMemoryRevisionRecord,
    )

    async def run():
        async with setup(tmp_path) as (db, convo, messages, paths):
            _, first = await reply(messages, convo, "shared question", "shared answer")
            _, future = await reply(messages, convo, "future question", "future answer")
            async with db._sessions() as session, session.begin():
                for revision, base, source, position, content in [
                    (1, 0, [first.message_id.value], first.position, "shared summary"),
                    (2, 1, [future.message_id.value], future.position, "future summary"),
                    (3, 2, [], future.position, "correction of future"),
                ]:
                    session.add(
                        ConversationMemoryRevisionRecord(
                            world_id=convo.conversation_id.world_id.value,
                            conversation_id=convo.conversation_id.value,
                            player_id=convo.player_id.value,
                            revision=revision,
                            base_revision=base,
                            source_ids=json.dumps([str(identity) for identity in source]),
                            through_position=position,
                            content=content,
                            user_edited=False,
                            created_at=datetime.now(UTC),
                        )
                    )
            store = db.conversation_memory_store()
            assert (await store.snapshot(convo.conversation_id, convo.player_id))["current"][
                "revision"
            ] == 3
            await mutate(paths, convo, "branch", message_id=first.message_id.value)
            assert (await store.snapshot(convo.conversation_id, convo.player_id))["current"][
                "content"
            ] == "shared summary"

    asyncio.run(run())


def test_http_json_confirmation_owner_and_stale_preview(tmp_path):
    import httpx
    from fastapi import FastAPI
    from livingworld.adapters.http.chat_paths import chat_path_router
    from livingworld.application.chat_paths import ChatPathService
    from livingworld.domain.contracts import API_PROTOCOL

    async def run():
        async with setup(tmp_path) as (db, convo, messages, paths):
            _, answer = await reply(messages, convo, "question", "answer")
            service = ChatPathService(paths, PlayerEventFeedService(db.player_event_feed_store()))
            app = FastAPI()
            app.include_router(chat_path_router(service, lambda: None))
            route = (
                f"/api/v{API_PROTOCOL}/worlds/{convo.conversation_id.world_id.value}"
                f"/conversations/{convo.conversation_id.value}/paths"
            )
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
            ) as client:
                initial = (await client.get(route)).json()
                assert initial["revision"] == 0
                draft = {
                    "action": "edit",
                    "revision": 0,
                    "message_id": str(answer.message_id.value),
                    "text": "changed text",
                }
                response = await client.post(route + "/preview", json=draft)
                assert response.status_code == 200
                preview = response.json()
                payload = {
                    "draft": preview["draft"],
                    "reviewed_hash": preview["reviewed_hash"],
                    "confirmed": True,
                    "request_id": str(uuid4()),
                }
                assert (
                    await client.post(route + "/commit", json={**payload, "confirmed": 1})
                ).status_code == 422
                assert (await client.post(route + "/commit", json=payload)).status_code == 200
                assert (await client.post(route + "/preview", json=draft)).status_code == 409
                foreign = route.replace(str(convo.conversation_id.value), str(uuid4()))
                assert (await client.get(foreign)).status_code == 404

    asyncio.run(run())
