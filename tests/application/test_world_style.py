"""World-style checks on synthetic SQLite, HTTP transports and mocked generation only."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from alembic import command
from fastapi import FastAPI
from livingworld.adapters.http.world_style import world_style_router
from livingworld.application.chat_context import DirectChatContextBuilder
from livingworld.application.chat_conversations import ChatConversationService
from livingworld.application.chat_messages import ChatMessageService
from livingworld.application.group_chat_context import GroupChatContextBuilder
from livingworld.application.llm import ModelRef, ProviderId
from livingworld.application.offline_contact import OfflineContactService
from livingworld.application.proactive_contact import ProactiveContactService
from livingworld.application.world_style import WorldStyle, WorldStyleService, validate_style
from livingworld.domain.contracts import API_PROTOCOL, RequestId
from livingworld.domain.errors import ConcurrencyConflictError
from livingworld.domain.identifiers import WorldId
from livingworld.infrastructure.persistence import Database
from livingworld.infrastructure.persistence import offline_contact as offline
from livingworld.infrastructure.persistence.director_models import (
    DirectorCandidateRecord as Routine,
)
from livingworld.infrastructure.persistence.director_models import DirectorPlanRecord as Plan
from livingworld.infrastructure.persistence.director_models import (
    DirectorSettingsRecord as Director,
)
from livingworld.infrastructure.persistence.migration import (
    HEAD_REVISION,
    PLAYER_PERSONA_REVISION,
    _alembic_config,
)
from livingworld.infrastructure.persistence.models import (
    ChatMessageRecord,
    WorldEventRecord,
    WorldRecord,
)
from livingworld.infrastructure.persistence.offline_contact_models import (
    OfflineContactSettingsRecord as OfflineSettings,
)
from livingworld.infrastructure.persistence.proactive_models import ProactiveSettingsRecord
from sqlalchemy import func, select, text
from test_capacity_boundaries import place
from test_offline_contact_capacity import seed


def body(context):
    return "\n".join(part.text for message in context.messages for part in message.content)


def test_upgrade_existing_0054_preserves_world_and_profile(tmp_path):
    async def run():
        db = Database(tmp_path)
        world = WorldId(uuid4())
        try:
            async with db.engine.begin() as connection:
                await connection.run_sync(
                    lambda sync: command.upgrade(_alembic_config(sync), PLAYER_PERSONA_REVISION)
                )
                await connection.execute(
                    text("INSERT INTO worlds VALUES (:id, '旧世界', 7)"), {"id": world.value.hex}
                )
                await connection.execute(
                    text("INSERT INTO local_world_profiles VALUES (:id, '旧身份', '保留描述', 3)"),
                    {"id": world.value.hex},
                )
            await db.initialize()
            await db.initialize()
            assert await db.world_style_store().load(world) == WorldStyle()
            assert (await db.local_profile_store().load(world)).description == "保留描述"
            async with db._sessions() as session:
                assert (
                    await session.scalar(text("SELECT version_num FROM alembic_version"))
                    == HEAD_REVISION
                )
                assert (await session.execute(text("SELECT name, revision FROM worlds"))).one() == (
                    "旧世界",
                    7,
                )
        finally:
            await db.close()

    asyncio.run(run())


def test_http_preview_binding_confirmation_conflict_and_world_isolation(tmp_path):
    async def run():
        db = Database(tmp_path)
        try:
            first, _, _, _ = await seed(db, 0)
            service = WorldStyleService(db.world_style_store())
            app = FastAPI()
            app.include_router(world_style_router(service, lambda: None))
            path = f"/api/v{API_PROTOCOL}/worlds/{first.value}/style"
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
            ) as client:
                draft = {"instructions": "都市悬疑", "expected_revision": 0}
                preview = (await client.post(path + "/preview", json=draft)).json()
                assert (await client.get(path)).json() == {"instructions": "", "revision": 0}
                payload = {**draft, "preview_id": preview["preview_id"], "confirmed": True}
                assert (
                    await client.post(path + "/commit", json={**payload, "confirmed": False})
                ).status_code == 422
                assert (
                    await client.post(
                        path + "/commit", json={**payload, "instructions": "被替换内容"}
                    )
                ).status_code == 422
                assert (await client.post(path + "/commit", json=payload)).json() == {
                    "instructions": "都市悬疑",
                    "revision": 1,
                }
                assert (await client.post(path + "/commit", json=payload)).status_code == 409
                assert (
                    await client.post(path + "/commit", json={**payload, "confirmed": 1})
                ).status_code == 422
                malformed = await client.post(
                    path + "/preview", json={**draft, "expected_revision": True}
                )
                assert malformed.status_code == 422 and "都市悬疑" not in malformed.text
            async with db._sessions() as session:
                count = await session.scalar(select(func.count()).select_from(WorldEventRecord))
            saved = await service.preview(first, "", 1)
            from livingworld.application.world_style import style_preview_id

            await service.confirm(first, "", 1, style_preview_id(first, saved))
            async with db._sessions() as session:
                assert (
                    await session.scalar(select(func.count()).select_from(WorldEventRecord))
                    == count
                )
            # The preview hash also binds the world, even at the same revision.
            other = WorldId(uuid4())
            async with db._sessions() as session, session.begin():
                session.add(WorldRecord(world_id=other.value, name="另一个世界", revision=0))
            with pytest.raises(ValueError, match="preview_changed"):
                await service.confirm(other, "都市悬疑", 0, preview["preview_id"])
            assert await service.store.load(other) == WorldStyle()
            assert await service.store.load(first) == WorldStyle("", 2)
        finally:
            await db.close()

    asyncio.run(run())


def test_style_cas_allows_only_one_concurrent_editor(tmp_path):
    async def run():
        db = Database(tmp_path)
        try:
            world, _, _, _ = await seed(db, 0)
            store = db.world_style_store()
            results = await asyncio.gather(
                store.save(world, WorldStyle("甲")),
                store.save(world, WorldStyle("乙")),
                return_exceptions=True,
            )
            assert sum(isinstance(result, WorldStyle) for result in results) == 1
            assert sum(isinstance(result, ConcurrencyConflictError) for result in results) == 1
        finally:
            await db.close()

    asyncio.run(run())


@pytest.mark.parametrize("value", ["中" * 4001, "\x00" * 4000, "\ud800"])
def test_capacity_counts_unicode_and_json_escaping(value):
    with pytest.raises(ValueError, match="world_style_"):
        validate_style(value)


def test_direct_and_group_use_world_style_without_exposing_it_to_selector(tmp_path):
    async def run():
        db = Database(tmp_path)
        try:
            world, _, players, contacts = await seed(db, 2)
            await db.world_style_store().save(world, WorldStyle("STYLE_CANARY：都市悬疑"))
            chats = ChatConversationService(
                db.chat_conversation_store(),
                db.world_content_service(),
                players,
                SimpleNamespace(execute=AsyncMock()),
            )
            messages = ChatMessageService(db.chat_message_store(), players)
            args = (chats, messages, db.local_profile_store(), db.character_memory_reader)
            direct = DirectChatContextBuilder(*args, style_reader=db.world_style_store())
            sent = await messages.send_player(
                RequestId(uuid4()), contacts[0].conversation_id, "你好", 10000
            )
            context = await direct.build(sent)
            assert body(context).count("STYLE_CANARY") == 1
            assert body(context).index("STYLE_CANARY") < body(context).index("【当前角色】")
            group = await chats.create_group(
                world, RequestId(uuid4()), tuple(c.root_import_id for c in contacts)
            )
            sent = await messages.send_group_player(
                RequestId(uuid4()), group.conversation_id, "你好", 10000
            )
            builder = GroupChatContextBuilder(*args, style_reader=db.world_style_store())
            assert "STYLE_CANARY" not in body(await builder.build_selection(sent))
            for contact in contacts:
                assert (
                    body(await builder.build_reply(sent, contact.character_id)).count(
                        "STYLE_CANARY"
                    )
                    == 1
                )
        finally:
            await db.close()

    asyncio.run(run())


@pytest.mark.parametrize("change", [False, True])
def test_online_snapshot_writer_and_atomic_stale_delivery(tmp_path, monkeypatch, change):
    async def run():
        db = Database(tmp_path)
        try:
            world, player, _, contacts = await seed(db, 1)
            home = await place(db, world, contacts)
            await db.world_style_store().save(world, WorldStyle("ONLINE_STYLE_CANARY"))
            plan, now = uuid4(), datetime.now(UTC)
            async with db._sessions() as session:
                session.add(
                    Plan(
                        world_id=world.value,
                        plan_id=plan,
                        generation=1,
                        window_start=0,
                        window_end=86400000000,
                        candidate_count=1,
                        input_json="{}",
                        state="ready",
                        created_at=now,
                    )
                )
                session.add(
                    Director(
                        world_id=world.value,
                        player_id=player.value,
                        enabled=True,
                        revision=1,
                        state="ready",
                        plan_id=plan,
                        consented_at=now,
                    )
                )
                await session.flush()
                session.add(
                    Routine(
                        world_id=world.value,
                        candidate_id=uuid4(),
                        plan_id=plan,
                        character_id=contacts[0].character_id.value,
                        location_id=home,
                        activity="rest",
                        due_at=0,
                        end_at=86400000000,
                        expected_revision=0,
                        state="active",
                    )
                )
                await session.commit()
            store = db.proactive_contact_store()
            await store.configure(world, player, True, 15, True, 0)
            async with db._sessions() as session:
                (
                    await session.get(ProactiveSettingsRecord, (world.value, player.value))
                ).next_at = 0
                await session.commit()
            claim = await store.claim_ready()
            assert claim and claim["input"]["world_style_revision"] == 1
            calls = []

            async def generated(configured, request, **kwargs):
                calls.append(request)
                if change:
                    await db.world_style_store().save(world, WorldStyle("新风格", 1))
                data = claim["input"]
                response = {
                    "purpose": data["purpose"],
                    "messages": [
                        {
                            "character_id": c["character_id"],
                            "purpose": data["purpose"],
                            "location": data["location"],
                            "text": "“一起来吗？”",
                        }
                        for c in data["characters"]
                    ],
                }
                return SimpleNamespace(text=json.dumps(response)), 20

            monkeypatch.setattr(
                "livingworld.application.proactive_contact.generate_bounded_text", generated
            )
            config = (None, None, ModelRef(ProviderId("mock"), "mock"), 8192, lambda: True)
            await ProactiveContactService(store, None, None, config)._contact(claim)
            assert len(calls) == 1
            assert calls[0].messages[0].content[0].text.count("ONLINE_STYLE_CANARY") == 1
            async with db._sessions() as session:
                assert await session.scalar(
                    select(func.count()).select_from(ChatMessageRecord)
                ) == (0 if change else 1)
            assert await store.claim_ready() is None
        finally:
            await db.close()

    asyncio.run(run())


@pytest.mark.parametrize("change", [False, True])
def test_offline_max_style_snapshot_and_pending_writer_cancellation(tmp_path, monkeypatch, change):
    async def run():
        db = Database(tmp_path)
        try:
            world, player, players, contacts = await seed(db, 17, long=True)
            style = "中" * 4000
            await db.world_style_store().save(world, WorldStyle(style))
            store = db.offline_contact_store()
            await store.configure(world, player, True, 1, True, 0)
            moment = datetime.now(UTC)

            class FixedDateTime(datetime):
                @classmethod
                def now(cls, tz=None):
                    return moment

            monkeypatch.setattr(offline, "datetime", FixedDateTime)
            async with db._sessions() as session:
                cfg = await session.get(OfflineSettings, 1)
                assert len(cfg.input_json.encode("utf-8")) <= 65536
                assert json.loads(cfg.input_json)["world_style"] == style
                cfg.last_online_at = moment - timedelta(hours=2)
                await session.commit()
            await store.pulse()
            claim = await store.claim_ready()
            assert claim is not None
            chosen = claim["input"]["characters"][0]["character_id"]
            service = OfflineContactService(store, players, None, None)
            calls = []

            async def generate(*args):
                calls.append(args)
                if len(calls) == 1:
                    return SimpleNamespace(
                        text=json.dumps(
                            {"character_id": chosen, "purpose": "check_in", "offset_minutes": 30}
                        )
                    ), 10
                if change:
                    await db.world_style_store().save(world, WorldStyle("新风格", 1))
                return SimpleNamespace(text="“最近好吗？”"), 20

            service._generate = generate
            await service._contact(claim)
            assert len(calls) == 2 and style in calls[1][3] and style not in calls[0][3]
            async with db._sessions() as session:
                assert (await session.get(OfflineSettings, 1)).state == (
                    "skipped" if change else "delivered"
                )
                assert await session.scalar(
                    select(func.count()).select_from(ChatMessageRecord)
                ) == (0 if change else 1)
            assert await store.claim_ready() is None
        finally:
            await db.close()

    asyncio.run(run())
