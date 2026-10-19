"""Reviewed identities on disposable synthetic databases; no network/model calls."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from alembic import command
from card_fixtures import card_document, json_bytes
from fastapi import FastAPI
from livingworld.adapters.http.player_persona import player_persona_router
from livingworld.application.chat_context import DirectChatContextBuilder
from livingworld.application.chat_conversations import ChatConversationService
from livingworld.application.chat_messages import ChatMessageService
from livingworld.application.group_chat_context import GroupChatContextBuilder
from livingworld.application.llm import ModelRef, ProviderId
from livingworld.application.offline_contact import OfflineContactError, OfflineContactService
from livingworld.application.player_persona import (
    InitialRecognition,
    PlayerPersonaDraft,
    PlayerPersonaError,
    PlayerPersonaService,
    identity_context,
    shared_identity_context,
)
from livingworld.application.proactive_contact import ProactiveContactService
from livingworld.domain.contracts import RequestId
from livingworld.infrastructure.persistence import Database
from livingworld.infrastructure.persistence import offline_contact as offline
from livingworld.infrastructure.persistence.migration import EXAMPLE_WORLD_REVISION, _alembic_config
from livingworld.infrastructure.persistence.models import (
    LocalPlayerBindingRecord,
    WorldEventRecord,
)
from livingworld.infrastructure.persistence.offline_contact_models import (
    OfflineContactSettingsRecord as Settings,
)
from livingworld.infrastructure.persistence.player_persona_models import PlayerPersonaRecord
from sqlalchemy import func, select, text
from test_offline_contact_capacity import seed


def context_text(context):
    return "\n".join(part.text for message in context.messages for part in message.content)


async def identity(db, world, contacts):
    store = db.player_persona_store()
    choices = (await store.sources(world, "", None, characters=True)).items
    sources = {item.root_import_id: item for item in choices}
    return PlayerPersonaDraft(
        identity_name="哲",
        public_identity="新艾利都的录像店店主；不是同名的其他人。",
        story_start="合成故事起点，后续剧情尚未发生",
        source=choices[0].reference,
        recognitions=[
            InitialRecognition(
                character_import_id=contact.root_import_id,
                relationship=f"朋友{i}",
                known_details=f"PRIVATE_{i}_CANARY",
            )
            for i, contact in enumerate(contacts)
        ],
    ), sources


async def adopt(db, world, draft, revision=0):
    service = PlayerPersonaService(db.player_persona_store())
    prepared = await service.preview(world, draft, revision)
    return await service.commit(world, prepared.preview_id)


def test_preview_confirmation_cas_retry_and_no_world_events(tmp_path):
    async def run():
        db = Database(tmp_path)
        try:
            world, player, _, contacts = await seed(db, 2)
            store = db.player_persona_store()
            service = PlayerPersonaService(store)
            draft, _ = await identity(db, world, contacts)
            async with db._sessions() as session:
                before = await session.scalar(select(func.count()).select_from(WorldEventRecord))
            preview = await service.preview(world, draft, 0)
            assert (await store.snapshot(world)).revision == 0
            assert preview.draft.recognitions[0].character_name == "隔离角色0"
            # Caller-owned edits after preview cannot alter what was approved.
            draft.public_identity = "UNREVIEWED"
            saved = await service.commit(world, preview.preview_id)
            assert saved.player_id == player.value and saved.revision == 1
            assert "UNREVIEWED" not in saved.draft.public_identity
            assert await service.commit(world, preview.preview_id) == saved
            assert await PlayerPersonaService(store).commit(world, preview.preview_id) == saved
            with pytest.raises(PlayerPersonaError, match="edit_conflict"):
                await service.preview(world, saved.draft, 0)
            # Two independent editor windows cannot overwrite the winner.
            second = PlayerPersonaService(store)
            a = await service.preview(world, saved.draft, 1)
            b = await second.preview(world, saved.draft, 1)
            await service.commit(world, a.preview_id)
            with pytest.raises(PlayerPersonaError, match="edit_conflict"):
                await second.commit(world, b.preview_id)
            async with db._sessions() as session:
                assert (
                    await session.scalar(select(func.count()).select_from(WorldEventRecord))
                    == before
                )
                assert (
                    await session.get(LocalPlayerBindingRecord, world.value)
                ).player_id == player.value
        finally:
            await db.close()

    asyncio.run(run())


def test_sources_page_without_name_guessing_and_filter_disabled(tmp_path):
    async def run():
        db = Database(tmp_path)
        try:
            world, _, _, contacts = await seed(db, 1)
            imports = db.world_content_service()
            payload = {
                "name": "合成世界书",
                "entries": {
                    str(i): {
                        "uid": i,
                        "comment": "哲",
                        "key": ["哲"],
                        "content": "公开候选" * 4000,
                        "disable": i == 40,
                    }
                    for i in range(41)
                },
            }
            prepared = await imports.prepare(world, "lorebook", json_bytes(payload))
            await imports.commit(world, prepared.item.import_id, prepared.item.reviewed_hash)
            store = db.player_persona_store()
            page = await store.sources(world, "哲", None)
            assert len(page.items) == 32 and page.next_after
            rest = await store.sources(world, "哲", page.next_after)
            assert len(rest.items) == 8 and rest.next_after is None
            assert len({item.reference.content_id for item in page.items + rest.items}) == 40
            assert all(item.excerpt for item in page.items + rest.items)
            assert (await store.snapshot(world)).draft.source is None
            with pytest.raises(PlayerPersonaError, match="cursor_invalid"):
                await store.sources(world, "", "bad")
            draft, _ = await identity(db, world, contacts)
            draft.recognitions *= 2
            with pytest.raises(PlayerPersonaError, match="duplicate_character"):
                await PlayerPersonaService(store).preview(world, draft, 0)
            draft.recognitions = []
            draft.source = draft.source.model_copy(update={"reviewed_hash": "0" * 64})
            with pytest.raises(PlayerPersonaError, match="source_changed"):
                await adopt(db, world, draft)
        finally:
            await db.close()

    asyncio.run(run())


def test_recipient_isolation_source_replacement_and_world_boundary(tmp_path):
    async def run():
        db = Database(tmp_path)
        try:
            world, player, _, contacts = await seed(db, 2)
            draft, sources = await identity(db, world, contacts)
            await adopt(db, world, draft)
            store = db.player_persona_store()
            first = await store.context_for_character(world, player, contacts[0].character_id)
            second = await store.context_for_character(world, player, contacts[1].character_id)
            assert "PRIVATE_0_CANARY" in json.dumps(first)
            assert "PRIVATE_1_CANARY" not in json.dumps(first)
            assert "PRIVATE_0_CANARY" not in json.dumps(second)
            common = shared_identity_context([first, second])
            assert common["identity_name"] == "哲" and common["initial_recognition"] is None
            assert (
                shared_identity_context([first])["initial_recognition"]
                == first["initial_recognition"]
            )
            other, other_player, _, _ = await seed(db, 0)
            assert (
                await store.context_for_character(other, other_player, contacts[0].character_id)
                is None
            )
            with pytest.raises(PlayerPersonaError, match="source_changed"):
                await adopt(db, other, draft)
            # Replace the exact accepted source, even with the same visible name.
            original = next(item for item in sources.values() if item.reference == draft.source)
            document = card_document()
            document["data"]["name"] = original.title
            imports = db.world_content_service()
            prepared = await imports.prepare(
                world,
                "character",
                json_bytes(document),
                replaces_import_id=original.reference.import_id,
            )
            await imports.commit(world, prepared.item.import_id, prepared.item.reviewed_hash)
            assert (await store.snapshot(world)).source_state == "changed"
            assert (
                await store.context_for_character(world, player, contacts[0].character_id) is None
            )
            with pytest.raises(PlayerPersonaError, match="source_changed"):
                await adopt(db, world, draft, 1)
        finally:
            await db.close()

    asyncio.run(run())


def test_http_requires_confirm_and_expiry_keeps_old_identity(tmp_path, monkeypatch):
    async def run():
        db = Database(tmp_path)
        try:
            world, player, _, contacts = await seed(db, 1)
            draft, _ = await identity(db, world, contacts)
            store = db.player_persona_store()
            service = PlayerPersonaService(store)
            app = FastAPI()
            app.include_router(player_persona_router(service, lambda: None))
            prefix = f"/api/v1/worlds/{world.value}/me/persona"
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://isolated"
            ) as client:
                switched = await client.post(
                    prefix + "/preview",
                    json={
                        "draft": draft.model_dump(mode="json"),
                        "expected_revision": 0,
                        "expected_player_id": str(uuid4()),
                    },
                )
                assert switched.status_code == 409
                response = await client.post(
                    prefix + "/preview",
                    json={
                        "draft": draft.model_dump(mode="json"),
                        "expected_revision": 0,
                        "expected_player_id": str(player.value),
                    },
                )
                assert response.status_code == 200, response.text
                body = response.json()
                rejected = await client.post(
                    prefix + "/commit", json={"preview_id": body["preview_id"], "confirmed": False}
                )
                assert rejected.status_code == 422
                assert (await store.snapshot(world)).revision == 0
                invalid = await client.post(
                    prefix + "/preview",
                    content=json.dumps(
                        {
                            "draft": {"identity_name": "\ud800"},
                            "expected_revision": 0,
                            "expected_player_id": str(player.value),
                        }
                    ),
                    headers={"content-type": "application/json"},
                )
                assert invalid.status_code == 422
                monkeypatch.setattr(
                    "livingworld.application.player_persona.monotonic", lambda: float("inf")
                )
                expired = await client.post(
                    prefix + "/commit", json={"preview_id": body["preview_id"], "confirmed": True}
                )
                assert expired.status_code == 409
                assert (await store.snapshot(world)).revision == 0
        finally:
            await db.close()

    asyncio.run(run())


def test_direct_group_context_and_selector_do_not_pool_private_knowledge(tmp_path):
    async def run():
        db = Database(tmp_path)
        try:
            world, _, players, contacts = await seed(db, 2)
            draft, _ = await identity(db, world, contacts)
            await adopt(db, world, draft)
            chats = ChatConversationService(
                db.chat_conversation_store(),
                db.world_content_service(),
                players,
                SimpleNamespace(execute=AsyncMock()),
            )
            messages = ChatMessageService(db.chat_message_store(), players)
            kwargs = dict(persona_reader=db.player_persona_store().context_for_character)
            direct = DirectChatContextBuilder(
                chats, messages, db.local_profile_store(), db.character_memory_reader, **kwargs
            )
            sent = await messages.send_player(
                RequestId(uuid4()), contacts[0].conversation_id, "你好", 10000
            )
            context = await direct.build(sent)
            rendered = context_text(context)
            assert "PRIVATE_0_CANARY" in rendered and "PRIVATE_1_CANARY" not in rendered
            group = await chats.create_group(
                world, RequestId(uuid4()), tuple(c.root_import_id for c in contacts)
            )
            group_builder = GroupChatContextBuilder(
                chats, messages, db.local_profile_store(), db.character_memory_reader, **kwargs
            )
            sent = await messages.send_group_player(
                RequestId(uuid4()), group.conversation_id, "你们好", 10000
            )
            selector = await group_builder.build_selection(sent)
            assert "PRIVATE_0_CANARY" not in context_text(selector)
            assert "PRIVATE_1_CANARY" not in context_text(selector)
            for i, contact in enumerate(contacts):
                reply = await group_builder.build_reply(sent, contact.character_id)
                assert f"PRIVATE_{i}_CANARY" in context_text(reply)
                assert f"PRIVATE_{1 - i}_CANARY" not in context_text(reply)
        finally:
            await db.close()

    asyncio.run(run())


def test_offline_snapshot_remains_small_and_only_chosen_writer_gets_identity(tmp_path, monkeypatch):
    async def run():
        db = Database(tmp_path)
        try:
            world, player, players, contacts = await seed(db, 17)
            draft, _ = await identity(db, world, contacts)
            await adopt(db, world, draft)
            store = db.offline_contact_store()
            await store.configure(world, player, True, 1, True, 0)
            moment = datetime.now(UTC)

            class FixedDateTime(datetime):
                @classmethod
                def now(cls, tz=None):
                    return moment

            monkeypatch.setattr(offline, "datetime", FixedDateTime)
            async with db._sessions() as session:
                cfg = await session.get(Settings, 1)
                raw = cfg.input_json
                assert len(raw.encode()) <= 65536 and "PRIVATE_" not in raw
                cfg.last_online_at = moment - timedelta(hours=2)
                await session.commit()
            await store.pulse()
            claim = await store.claim_ready()
            assert claim is not None
            chosen = claim["input"]["characters"][0]["character_id"]
            index = next(
                i for i, contact in enumerate(contacts) if str(contact.character_id.value) == chosen
            )
            service = OfflineContactService(store, players, None, None)
            service._generate = AsyncMock(
                side_effect=[
                    (
                        SimpleNamespace(
                            text=json.dumps(
                                {
                                    "character_id": chosen,
                                    "purpose": "check_in",
                                    "offset_minutes": 30,
                                }
                            )
                        ),
                        10,
                    ),
                    (SimpleNamespace(text="隔离问候"), 20),
                ]
            )
            await service._contact(claim)
            assert service._generate.await_count == 2
            planner, writer = service._generate.call_args_list
            assert "PRIVATE_" not in str(planner)
            assert f"PRIVATE_{index}_CANARY" in str(writer)
            assert all(f"PRIVATE_{i}_CANARY" not in str(writer) for i in range(17) if i != index)
            assert await store.claim_ready() is None
        finally:
            await db.close()

    asyncio.run(run())


def test_0053_upgrade_preserves_profile_and_existing_rows(tmp_path):
    async def run():
        db = Database(tmp_path)
        try:
            async with db.engine.begin() as conn:
                await conn.run_sync(
                    lambda sync: command.upgrade(_alembic_config(sync), EXAMPLE_WORLD_REVISION)
                )
                await conn.execute(
                    text("INSERT INTO local_user_profile VALUES (1, '旧称呼', '旧描述', 7)")
                )
            await db.initialize()
            await db.initialize()
            profile = await db.local_profile_store().load()
            assert profile.name == "旧称呼" and profile.description == "旧描述"
            async with db._sessions() as session:
                assert (
                    await session.scalar(select(func.count()).select_from(PlayerPersonaRecord)) == 0
                )
        finally:
            await db.close()

    asyncio.run(run())


def test_persona_change_revokes_pending_offline_writer(tmp_path, monkeypatch):
    async def run():
        db = Database(tmp_path)
        try:
            world, player, _, contacts = await seed(db, 1)
            draft, _ = await identity(db, world, contacts)
            await adopt(db, world, draft)
            store = db.offline_contact_store()
            await store.configure(world, player, True, 1, True, 0)
            moment = datetime.now(UTC)

            class FixedDateTime(datetime):
                @classmethod
                def now(cls, tz=None):
                    return moment

            monkeypatch.setattr(offline, "datetime", FixedDateTime)
            async with db._sessions() as session:
                (await session.get(Settings, 1)).last_online_at = moment - timedelta(hours=2)
                await session.commit()
            await store.pulse()
            claim = await store.claim_ready()
            assert claim is not None
            draft.public_identity = "修改后的身份"
            await adopt(db, world, draft, 1)
            with pytest.raises(OfflineContactError, match="context_changed"):
                await store.prepare_dialogue(
                    claim["episode_id"],
                    str(contacts[0].character_id.value),
                    "check_in",
                    claim["offline_from"] + timedelta(minutes=30),
                )
        finally:
            await db.close()

    asyncio.run(run())


def test_online_joint_writer_uses_common_identity_in_one_call(monkeypatch):
    async def run():
        store = SimpleNamespace(deliver=AsyncMock(), finish=AsyncMock())
        a, b = str(uuid4()), str(uuid4())
        contexts = [
            {
                "identity_name": "哲",
                "public_identity": "店主",
                "initial_recognition": {"known_details": secret},
            }
            for secret in ("A_ONLY_CANARY", "B_ONLY_CANARY")
        ]
        shared = shared_identity_context(contexts)
        generated = AsyncMock(
            return_value=(
                SimpleNamespace(
                    text=json.dumps(
                        {
                            "purpose": "invite_leisure",
                            "messages": [
                                {
                                    "character_id": actor,
                                    "purpose": "invite_leisure",
                                    "location": "商场",
                                    "text": "我和朋友在逛街，要来吗？",
                                }
                                for actor in (a, b)
                            ],
                        }
                    )
                ),
                20,
            )
        )
        monkeypatch.setattr(
            "livingworld.application.proactive_contact.generate_bounded_text", generated
        )
        configured = (None, None, ModelRef(ProviderId("mock"), "mock-model"), 8192, lambda: True)
        service = ProactiveContactService(store, None, None, configured)
        claim = {
            "world_id": uuid4(),
            "episode_id": uuid4(),
            "player_identity": shared,
            "input": {
                "location": "商场",
                "activity": "逛街",
                "purpose": "invite_leisure",
                "common_world_background": [],
                "characters": [
                    {"character_id": actor, "name": actor, "persona": {}} for actor in (a, b)
                ],
            },
        }
        await service._contact(claim)
        assert generated.await_count == 1 and store.deliver.await_count == 1
        request = generated.call_args.args[1]
        payload = "\n".join(part.text for message in request.messages for part in message.content)
        assert "哲" in payload and "A_ONLY_CANARY" not in payload and "B_ONLY_CANARY" not in payload
        assert set(store.deliver.call_args.args[1]) == {a, b}

    asyncio.run(run())


@pytest.mark.parametrize("prose", ["中文😀" * 500, "\x00" * 1600, '"\\\n' * 500])
def test_identity_reference_is_bounded_after_escaping_and_draft_is_unchanged(prose):
    root = uuid4()
    draft = PlayerPersonaDraft(
        identity_name="哲",
        public_identity=prose,
        recognitions=[InitialRecognition(character_import_id=root, known_details=prose)],
    )
    before = draft.model_dump_json()
    selected = identity_context(draft, root, 1)
    assert len(json.dumps(selected, ensure_ascii=False).encode("utf-8")) < 12000
    assert draft.model_dump_json() == before
    assert prose.startswith(selected["public_identity"])
    assert prose.startswith(selected["initial_recognition"]["known_details"])


def test_switching_selected_player_rejects_prepared_identity(tmp_path):
    async def run():
        db = Database(tmp_path)
        try:
            world, _, _, contacts = await seed(db, 1)
            draft, _ = await identity(db, world, contacts)
            service = PlayerPersonaService(db.player_persona_store())
            preview = await service.preview(world, draft, 0)
            async with db._sessions() as session:
                binding = await session.get(LocalPlayerBindingRecord, world.value)
                await session.delete(binding)
                await session.commit()
            with pytest.raises(PlayerPersonaError, match="player_changed"):
                await service.commit(world, preview.preview_id)
            async with db._sessions() as session:
                assert (
                    await session.scalar(select(func.count()).select_from(PlayerPersonaRecord)) == 0
                )
        finally:
            await db.close()

    asyncio.run(run())
