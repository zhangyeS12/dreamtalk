"""Capacity regressions with disposable SQLite graphs, no providers or user data."""

import asyncio
from copy import deepcopy
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import UUID, uuid4, uuid5

import httpx
import pytest
from card_fixtures import card_document, json_bytes
from fastapi import FastAPI
from livingworld.adapters.http.content_authoring import content_authoring_router
from livingworld.application.content_authoring import authored_graph
from livingworld.application.content_editor_pages import editor_page, merge_editor_patch
from livingworld.application.director import DirectorError
from livingworld.application.input_budget import encode_input, planning_references
from livingworld.domain.content.models import LoreEntry
from livingworld.infrastructure.persistence import Database
from livingworld.infrastructure.persistence import proactive_contact as proactive
from livingworld.infrastructure.persistence.character_lineage import latest_character_import
from livingworld.infrastructure.persistence.director_background import read_director_background
from livingworld.infrastructure.persistence.director_models import (
    DirectorCandidateRecord as Routine,
)
from livingworld.infrastructure.persistence.director_models import DirectorPlanRecord as Plan
from livingworld.infrastructure.persistence.director_models import (
    DirectorSettingsRecord as Director,
)
from livingworld.infrastructure.persistence.location_policy_models import (
    CharacterLocationPolicyRecord,
)
from livingworld.infrastructure.persistence.models import (
    CharacterStateRecord,
    ChatConversationRecord,
    ChatMessageRecord,
    ChatTurnRecord,
    WorldCommonLoreRecord,
    WorldContentImportRecord,
)
from livingworld.infrastructure.persistence.proactive_models import ProactiveEpisodeRecord
from sqlalchemy import func, select
from test_offline_contact_capacity import seed


async def book(db, world, count, *, long=False, bad=False, escaped=False):
    entries = {
        str(i): {
            "uid": i,
            "key": [],
            "comment": f"entry-{i}",
            "content": "正文",
            "constant": True,
            "disable": False,
        }
        for i in range(count)
    }
    entries[str(count - 1)]["order"] = -1000
    entries[str(count - 1)]["comment"] = "priority-anchor"
    if long:
        entries["0"]["content"] = "长正文" * 8000
    if escaped:
        entries["0"].update(content="\x00" * 12000, order=-2000)
    if bad:
        entries["0"].update(key=["x" * 20000], constant=False, comment="bad-condition")
    imports = db.world_content_service()
    preview = await imports.prepare(
        world, "lorebook", json_bytes({"name": "合成世界书", "entries": entries})
    )
    return await imports.commit(world, preview.item.import_id, preview.item.reviewed_hash)


def test_large_book_pages_and_sparse_preview_preserve_unloaded_and_long_content(tmp_path):
    async def run():
        db = Database(tmp_path)
        try:
            world, _, _, _ = await seed(db, 0)
            original = await book(db, world, 150, long=True)
            page = editor_page(original, 128)
            assert page["total_entries"] == 150 and len(page["draft"]["entries"]) == 22
            first = next(x for x in original.contents if isinstance(x, LoreEntry))
            fields = merge_editor_patch(
                original,
                {"name": "改名"},
                [(first.content_id.value, {"title": "只改标题"})],
                [],
                [],
            )
            draft = await authored_graph(fields, original, db.content_repository())
            entries = [x for x in draft.contents if isinstance(x, LoreEntry)]
            assert len(entries) == 150
            assert entries[0].title == "只改标题" and entries[0].content == first.content
            assert [x.content for x in entries[1:]] == [
                x.content for x in original.contents if isinstance(x, LoreEntry)
            ][1:]
            app = FastAPI()
            service = db.world_content_service()
            app.include_router(
                content_authoring_router(service, db.content_repository(), None, lambda: None)
            )
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://isolated"
            ) as client:
                prefix = f"/api/v1/worlds/{world.value}/content/editor/{original.import_id}"
                response = await client.get(prefix + "/page?offset=0")
                assert response.status_code == 200
                assert response.json()["draft"]["entries"][0]["content"] == first.content
                response = await client.post(
                    prefix + "/preview-changes",
                    json={
                        "fields": {"name": "HTTP改名"},
                        "updates": [],
                        "removed": [],
                        "added": [],
                    },
                )
                assert response.status_code == 200, response.text
                preview_result = response.json()
                # Preparing a preview does not replace the accepted source.
                assert await db.world_content_service().store.is_current(original.import_id)
                response = await client.post(
                    prefix + "/preview-changes", json={"fields": {}, "removed": [str(uuid4())]}
                )
                assert response.status_code == 422
                saved = await service.commit(
                    world, UUID(preview_result["import_id"]), preview_result["reviewed_hash"]
                )
                assert [x.content for x in saved.contents if isinstance(x, LoreEntry)] == [
                    x.content for x in original.contents if isinstance(x, LoreEntry)
                ]
                response = await client.get(prefix + "/page?offset=0")
                assert response.status_code == 409
        finally:
            await db.close()

    asyncio.run(run())


def test_public_background_over_512_is_ranked_and_bad_metadata_is_isolated(tmp_path):
    async def run():
        db = Database(tmp_path)
        try:
            world, _, _, _ = await seed(db, 0)
            imported = await book(db, world, 550, bad=True)
            entries = [x for x in imported.contents if isinstance(x, LoreEntry)]
            async with db._sessions() as session:
                session.add_all(
                    [
                        WorldCommonLoreRecord(
                            world_id=world.value,
                            import_id=imported.import_id,
                            entry_id=x.content_id.value,
                        )
                        for x in entries[:-1]
                    ]
                )
                await session.commit()
            async with db._sessions() as session:
                selected = await read_director_background(session, world, texts=("合成",))
                assert len(selected) == 16
                assert all(
                    x.entry.title not in {"bad-condition", "priority-anchor"} for x in selected
                )
                session.add(
                    WorldCommonLoreRecord(
                        world_id=world.value,
                        import_id=imported.import_id,
                        entry_id=entries[-1].content_id.value,
                    )
                )
                await session.commit()
            async with db._sessions() as session:
                selected = await read_director_background(session, world, texts=("合成",))
                assert selected[0].entry.title == "priority-anchor"
                assert len(selected) == 16
                news = await read_director_background(session, world, news_name="世界")
                assert news[0].entry.title == "priority-anchor"
        finally:
            await db.close()

    asyncio.run(run())


async def place(db, world, contacts):
    home = uuid5(world.value, "livingworld:local-home:v1")
    async with db._sessions() as session:
        for contact in contacts:
            session.add(
                CharacterStateRecord(
                    world_id=world.value,
                    character_id=contact.character_id.value,
                    location_id=home,
                    revision=1,
                )
            )
            session.add(
                CharacterLocationPolicyRecord(
                    world_id=world.value,
                    character_id=contact.character_id.value,
                    initial_location_id=home,
                    locked=False,
                    revision=0,
                )
            )
        await session.commit()
    return home


def test_director_packs_long_personas_without_dropping_selected_roles(tmp_path):
    async def run():
        db = Database(tmp_path)
        try:
            world, _, _, contacts = await seed(db, 2, long=True)
            await place(db, world, contacts)
            async with db._sessions() as session:
                snapshot = await db.director_store().planning_input(session, world, 0)
                assert len(encode_input(snapshot).encode("utf-8")) <= 65536
                assert {c["character_id"] for c in snapshot["characters"]} == {
                    str(c.character_id.value) for c in contacts
                }
                assert all(c["mobility_route_ids"] for c in snapshot["characters"])
                assert "PRIVATE_NOTES_CANARY" not in encode_input(snapshot)
        finally:
            await db.close()

    asyncio.run(run())


def test_129_replacements_resolve_but_a_real_cycle_is_rejected(tmp_path):
    async def run():
        db = Database(tmp_path)
        try:
            world, _, _, contacts = await seed(db, 1)
            root = contacts[0].root_import_id
            current = root
            imports = db.world_content_service()
            for _ in range(129):
                preview = await imports.prepare(
                    world, "character", json_bytes(card_document()), replaces_import_id=current
                )
                current = (
                    await imports.commit(world, preview.item.import_id, preview.item.reviewed_hash)
                ).import_id
            async with db._sessions() as session:
                assert await latest_character_import(session, world.value, root) == current
                persona = await db.director_store().approved_persona(
                    session, world, contacts[0].character_id.value, text_limit=8192
                )
                assert persona["accepted_import_id"] == str(current)
                (await session.get(WorldContentImportRecord, root)).replaces_import_id = current
                await session.commit()
            async with db._sessions() as session:
                with pytest.raises(ValueError, match="lineage"):
                    await latest_character_import(session, world.value, root)
        finally:
            await db.close()

    asyncio.run(run())


def test_513_conversations_keep_global_and_paged_unread_counts(tmp_path):
    async def run():
        db = Database(tmp_path)
        try:
            world, player, _, contacts = await seed(db, 1)
            identities = [UUID(int=i + 1) for i in range(513)]
            now = datetime.now(UTC)
            async with db._sessions() as session:
                session.add_all(
                    [
                        ChatConversationRecord(
                            world_id=world.value,
                            conversation_id=c,
                            player_id=player.value,
                            kind="group",
                            created_at_utc=now,
                        )
                        for c in identities
                    ]
                )
                await session.commit()
                turn = uuid4()
                session.add(
                    ChatTurnRecord(
                        world_id=world.value,
                        turn_id=turn,
                        conversation_id=identities[-1],
                        request_id=uuid4(),
                        fingerprint="0" * 64,
                        token_ceiling=1,
                        status="pending",
                        created_at_utc=now,
                    )
                )
                await session.flush()
                session.add(
                    ChatMessageRecord(
                        world_id=world.value,
                        message_id=uuid4(),
                        conversation_id=identities[-1],
                        turn_id=turn,
                        position=1,
                        sender_character_id=contacts[0].character_id.value,
                        text="合成消息",
                        created_at_utc=now,
                    )
                )
                await session.commit()
            store = db.chat_unread_store()
            first = await store.snapshot(world, player, page=True)
            assert len(first["items"]) == 128 and first["has_unread"] is True
            assert not any(x["unread"] for x in first["items"])
            rows, cursor = list(first["items"]), first["next_after"]
            while cursor:
                page = await store.snapshot(world, player, page=True, after=UUID(cursor))
                rows.extend(page["items"])
                cursor = page["next_after"]
            assert len(rows) == 514 and len({x["conversation_id"] for x in rows}) == 514
            assert sum(x["unread"] for x in rows) == 1
            assert len((await store.snapshot(world, player))["items"]) == 514
        finally:
            await db.close()

    asyncio.run(run())


def test_proactive_scan_rotates_past_64_blocked_worlds_without_starting_jobs(tmp_path, monkeypatch):
    async def run():
        db = Database(tmp_path)
        try:
            store = db.proactive_contact_store()
            worlds = []
            for _ in range(65):
                world, player, _, _ = await seed(db, 0)
                worlds.append(world.value)
                await store.configure(world, player, True, 15, True, 0)
            from livingworld.infrastructure.persistence.proactive_models import (
                ProactiveSettingsRecord,
            )

            async with db._sessions() as session:
                for cfg in (await session.scalars(select(ProactiveSettingsRecord))).all():
                    cfg.next_at = 0
                await session.commit()
            gate = AsyncMock(return_value=True)
            monkeypatch.setattr(proactive, "contact_blocked", gate)
            assert await store.claim_ready() is None
            assert len(gate.await_args_list) == 64
            assert await store.claim_ready() is None
            assert {call.args[1] for call in gate.await_args_list} == set(worlds)
            async with db._sessions() as session:
                assert (
                    await session.scalar(select(func.count()).select_from(ProactiveEpisodeRecord))
                    == 0
                )
        finally:
            await db.close()

    asyncio.run(run())


def test_reference_packing_counts_escaping_and_preserves_sources():
    source = {
        "characters": [
            {
                "character_id": str(uuid4()),
                "accepted_import_id": str(uuid4()),
                "name": "角色",
                "persona": {
                    k: "中文\x00\\\n" * 8000 for k in ("personality", "description", "background")
                },
            }
        ],
        "common_world_background": [{"title": "背景", "content": "\x00" * 12000}],
    }
    original = deepcopy(source)
    result = planning_references(source)
    assert len(encode_input(result).encode("utf-8")) <= 65536
    assert (
        result["characters"][0]["accepted_import_id"]
        == source["characters"][0]["accepted_import_id"]
    )
    assert result["common_world_background"] == []
    assert source == original


@pytest.mark.parametrize("all_bad", [False, True])
def test_online_preparation_isolates_bad_candidates_and_heals_without_replaying(tmp_path, all_bad):
    async def run():
        db = Database(tmp_path)
        try:
            world, player, _, contacts = await seed(db, 2, long=True)
            home = await place(db, world, contacts)
            plan = uuid4()
            now = datetime.now(UTC)
            async with db._sessions() as session:
                session.add(
                    Plan(
                        world_id=world.value,
                        plan_id=plan,
                        generation=1,
                        window_start=0,
                        window_end=86400000000,
                        candidate_count=2,
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
                session.add_all(
                    [
                        Routine(
                            world_id=world.value,
                            candidate_id=uuid4(),
                            plan_id=plan,
                            character_id=c.character_id.value,
                            location_id=home,
                            activity="rest",
                            due_at=0,
                            end_at=86400000000,
                            expected_revision=0,
                            state="active",
                        )
                        for c in contacts
                    ]
                )
                await session.commit()
            store = db.proactive_contact_store()
            await store.configure(world, player, True, 15, True, 0)
            from livingworld.infrastructure.persistence.proactive_models import (
                ProactiveSettingsRecord,
            )

            async with db._sessions() as session:
                (
                    await session.get(ProactiveSettingsRecord, (world.value, player.value))
                ).next_at = 0
                await session.commit()
            original = store._source
            checked = []

            async def bad_then_valid(session, cfg, kind, identity):
                checked.append(identity)
                if all_bad or len(checked) == 1:
                    raise DirectorError("director_character_mapping_invalid")
                return await original(session, cfg, kind, identity)

            store._source = bad_then_valid
            claim = await store.claim_ready()
            if all_bad:
                assert claim is None and len(checked) == 2
                state = await store.snapshot(world, player)
                assert state["state"] == "idle" and state["error"] == "proactive_input_unavailable"
                async with db._sessions() as session:
                    cfg = await session.get(ProactiveSettingsRecord, (world.value, player.value))
                    cfg.state = "attention"  # Legacy preparation failure, without a claim.
                    await session.commit()
                await store.interrupt_abandoned()
                assert (await store.snapshot(world, player))["state"] == "idle"
                store._source = original
                claim = await store.claim_ready()
            assert claim is not None
            assert len(encode_input(claim["input"]).encode("utf-8")) <= 65536
            assert await store.claim_ready() is None
            state = await store.snapshot(world, player)
            assert state["state"] == "writing" and state["error"] is None
            async with db._sessions() as session:
                assert (
                    await session.scalar(select(func.count()).select_from(ProactiveEpisodeRecord))
                    == 1
                )
            store._source = original
            replies = {
                c["character_id"]: "正在休息，要一起聊聊吗？" for c in claim["input"]["characters"]
            }
            await store.deliver(claim, replies, 20)
            async with db._sessions() as session:
                assert (
                    await session.scalar(select(func.count()).select_from(ChatMessageRecord)) == 1
                )
            assert await store.claim_ready() is None
            # An erroneous preparation label cannot unlock an actual paid receipt.
            async with db._sessions() as session:
                cfg = await session.get(ProactiveSettingsRecord, (world.value, player.value))
                cfg.state, cfg.error = "attention", "proactive_input_unavailable"
                receipt = await session.get(
                    ProactiveEpisodeRecord, (world.value, claim["episode_id"])
                )
                receipt.state, receipt.error = "failed", "proactive_generation_failed"
                await session.commit()
            await store.interrupt_abandoned()
            assert (await store.snapshot(world, player))["state"] == "attention"

        finally:
            await db.close()

    asyncio.run(run())


def test_escaped_public_background_is_skipped_without_losing_other_news_sources(tmp_path):
    async def run():
        db = Database(tmp_path)
        try:
            world, _, _, _ = await seed(db, 0)
            imported = await book(db, world, 2, escaped=True)
            async with db._sessions() as session:
                session.add_all(
                    [
                        WorldCommonLoreRecord(
                            world_id=world.value,
                            import_id=imported.import_id,
                            entry_id=x.content_id.value,
                        )
                        for x in imported.contents
                        if isinstance(x, LoreEntry)
                    ]
                )
                await session.commit()
            from livingworld.infrastructure.persistence.world_story import _news_background

            async with db._sessions() as session:
                background = await _news_background(session, world)
                assert len(background) == 1 and background[0]["title"] == "priority-anchor"
                assert len(encode_input(background).encode("utf-8")) <= 12 * 1024
        finally:
            await db.close()

    asyncio.run(run())
