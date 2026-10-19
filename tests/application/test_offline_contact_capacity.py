"""Offline preparation and no-replay regressions on disposable synthetic SQLite data."""

import asyncio
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from card_fixtures import card_document, json_bytes
from livingworld.application.chat_conversations import ChatConversationService
from livingworld.application.command_handler import CommandHandler
from livingworld.application.commands import CreateWorld
from livingworld.application.director import DirectorError
from livingworld.application.offline_contact import OfflineContactService
from livingworld.application.offline_contact_inputs import (
    MAX_INPUT_BYTES,
    bounded_text,
    capture_cursor,
    encode_input,
    pack_snapshot,
)
from livingworld.application.player_event_feed import PlayerEventFeedService
from livingworld.application.player_onboarding import LocalPlayerOnboardingService
from livingworld.application.simulation_clock import EffectiveWorldTimeSource, SystemMonotonicClock
from livingworld.domain.contracts import RequestId
from livingworld.domain.identifiers import WorldId
from livingworld.infrastructure.clock import SystemWallClock
from livingworld.infrastructure.persistence import Database
from livingworld.infrastructure.persistence import offline_contact as persistence
from livingworld.infrastructure.persistence.models import WorldContentImportRecord, WorldEventRecord
from livingworld.infrastructure.persistence.offline_contact_models import (
    OfflineContactEpisodeRecord as Episode,
)
from livingworld.infrastructure.persistence.offline_contact_models import (
    OfflineContactSettingsRecord as Settings,
)
from sqlalchemy import func, select


@pytest.mark.parametrize("value", ["中文😀" * 100, '\x00\x01\n"\\' * 100, "abc" * 100])
def test_clipping_counts_json_escaping_and_unicode_without_rewriting_source(value):
    clipped = bounded_text(value, 51)
    assert value.startswith(clipped)
    assert len(encode_input(clipped).encode("utf-8")) <= 51
    assert len(encode_input(clipped + value[len(clipped)]).encode("utf-8")) > 51


def test_worst_case_frozen_input_fits_sqlite_limit_and_preserves_authored_data():
    characters = [
        {
            "character_id": str(uuid4()),
            "conversation_id": str(uuid4()),
            "accepted_import_id": str(uuid4()),
            "name": "角色😀" * 500,
            "persona": {
                field: "中文😀\x00\n\\" * 8000
                for field in ("personality", "description", "background")
            },
        }
        for _ in range(16)
    ]
    original = deepcopy(characters)
    preparation = dict(
        selected=16,
        excluded=0,
        clipped=0,
        batched=True,
        background_omitted=False,
        context_limited=False,
    )
    background = [
        {
            "import_id": str(uuid4()),
            "entry_id": str(uuid4()),
            "title": "公开背景",
            "content": "\x00" * 12_000,
        }
    ]
    raw = pack_snapshot({}, characters, background, [], preparation)
    decoded = json.loads(raw)
    assert len(raw.encode("utf-8")) <= MAX_INPUT_BYTES
    assert len(decoded["characters"]) == 16
    assert decoded["input_preparation"]["clipped"] == 16
    assert decoded["input_preparation"]["context_limited"] is True
    assert decoded["common_world_background"] == []
    assert [c["accepted_import_id"] for c in decoded["characters"]] == [
        c["accepted_import_id"] for c in original
    ]
    assert characters == original


def test_legacy_and_unusable_cohort_cursors_are_safe_without_schema_changes():
    assert capture_cursor('{"characters":[],"eligible":false}', advance=False) is None
    before, after = uuid4(), uuid4()
    raw = encode_input({"input_selection": {"after": str(before), "next_after": str(after)}})
    assert capture_cursor(raw, advance=False) == before
    assert capture_cursor(raw, advance=True) == after
    bad = json.loads(raw)
    bad["input_preparation"] = {"selected": 0, "excluded": 64, "batched": True}
    assert capture_cursor(encode_input(bad), advance=False) == after


async def seed(db, count, *, long=False):
    await db.initialize()
    clock = SystemWallClock()
    handler = CommandHandler(
        db.unit_of_work,
        clock,
        world_time_source=EffectiveWorldTimeSource(clock, SystemMonotonicClock()),
    )
    world = WorldId(uuid4())
    await handler.execute(
        CreateWorld(request_id=RequestId(uuid4()), world_id=world, name="隔离世界")
    )
    players = PlayerEventFeedService(db.player_event_feed_store())
    player = await LocalPlayerOnboardingService(handler, players).start_at_home(world)
    imports = db.world_content_service()
    chats = ChatConversationService(db.chat_conversation_store(), imports, players, handler)
    contacts = []
    for index in range(count):
        card = card_document()
        card["data"].update(name=f"隔离角色{index}", creator_notes="PRIVATE_NOTES_CANARY")
        if long:
            card["data"]["description"] = "中文😀\x00\n\\" * 8000
        draft = await imports.prepare(world, "character", json_bytes(card))
        accepted = await imports.commit(world, draft.item.import_id, draft.item.reviewed_hash)
        contacts.append(await chats.open_direct(world, accepted.import_id))
    return world, player, players, contacts


def test_large_directory_freezes_one_batch_rotates_and_sends_only_once(tmp_path, monkeypatch):
    async def run():
        db = Database(tmp_path)
        try:
            world, player, players, contacts = await seed(db, 17, long=True)
            store = db.offline_contact_store()
            async with db._sessions() as session:
                projected = await store.director.approved_persona(
                    session, world, contacts[0].character_id.value, text_limit=8192
                )
                assert projected["persona_truncated"] is True
                assert "\x00" in projected["persona"]["description"]
                assert ("中文😀\x00\n\\" * 8000).startswith(projected["persona"]["description"])
                assert len(projected["persona"]["description"].encode("utf-8")) <= 8192
            async with db._sessions() as session:
                originals = (
                    await session.scalars(select(WorldContentImportRecord.snapshot_json))
                ).all()
                events = await session.scalar(select(func.count()).select_from(WorldEventRecord))
            await store.configure(world, player, True, 1, True, 0)
            async with db._sessions() as session:
                frozen_raw = (await session.get(Settings, 1)).input_json
            frozen = json.loads(frozen_raw)
            assert len(frozen_raw.encode("utf-8")) <= MAX_INPUT_BYTES
            assert len(frozen["characters"]) == 16
            assert frozen["input_preparation"]["batched"] is True
            assert frozen["input_preparation"]["clipped"] == 16
            assert "PRIVATE_NOTES_CANARY" not in frozen_raw
            await store.pulse()
            async with db._sessions() as session:
                assert (await session.get(Settings, 1)).input_json == frozen_raw
            # The optional bounded projection must not relax the normal Director policy.
            with pytest.raises(DirectorError, match="director_world_capacity"):
                async with db._sessions() as session:
                    await store.director.approved_persona(
                        session, world, contacts[0].character_id.value
                    )
            moment = datetime.now(UTC)

            class FixedDateTime(datetime):
                @classmethod
                def now(cls, tz=None):
                    return moment

            monkeypatch.setattr(persistence, "datetime", FixedDateTime)
            async with db._sessions() as session:
                (await session.get(Settings, 1)).last_online_at = moment - timedelta(hours=2)
                await session.commit()
            await store.pulse()
            claim = await store.claim_ready()
            assert claim is not None
            assert claim["input"] == frozen
            async with db._sessions() as session:
                upcoming = json.loads((await session.get(Settings, 1)).input_json)
            old_ids = {c["character_id"] for c in frozen["characters"]}
            new_ids = {c["character_id"] for c in upcoming["characters"]}
            assert new_ids != old_ids
            assert len(new_ids | old_ids) == 17
            chosen = frozen["characters"][0]["character_id"]
            service = OfflineContactService(store, players, None, None)
            service._generate = AsyncMock(
                side_effect=[
                    (
                        SimpleNamespace(
                            text=encode_input(
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
            async with db._sessions() as session:
                episode = await session.get(Episode, claim["episode_id"])
                assert episode.state == "delivered"
                assert episode.message_id is not None
                assert (
                    await session.scalars(select(WorldContentImportRecord.snapshot_json))
                ).all() == originals
                assert (
                    await session.scalar(select(func.count()).select_from(WorldEventRecord))
                    == events
                )
                (await session.get(Settings, 1)).last_online_at = moment - timedelta(hours=2)
                await session.commit()
            await store.pulse()
            assert await store.claim_ready() is None
            async with db._sessions() as session:
                assert await session.scalar(select(func.count()).select_from(Episode)) == 1
            assert service._generate.await_count == 2
        finally:
            await db.close()

    asyncio.run(run())


def test_invalid_candidate_is_isolated_and_preparation_error_clears_without_a_model(tmp_path):
    async def run():
        db = Database(tmp_path)
        try:
            world, player, _, contacts = await seed(db, 17)
            store = db.offline_contact_store()
            original = store.director.approved_persona
            bad_id = min(
                contacts, key=lambda contact: contact.conversation_id.value
            ).character_id.value

            async def one_bad(session, scope, character, **kwargs):
                if character == bad_id:
                    raise DirectorError("director_character_mapping_invalid")
                return await original(session, scope, character, **kwargs)

            store.director.approved_persona = one_bad
            await store.configure(world, player, True, 1, True, 0)
            state = await store.snapshot(world, player)
            assert state["state"] == "idle" and state["error"] is None
            assert state["input_preparation"]["selected"] == 16
            assert state["input_preparation"]["excluded"] == 1
            store.director.approved_persona = AsyncMock(
                side_effect=DirectorError("director_character_mapping_invalid")
            )
            await store.pulse()
            assert (await store.snapshot(world, player))[
                "error"
            ] == "offline_candidates_unavailable"
            store.director.approved_persona = original
            await store.pulse()
            restored = await store.snapshot(world, player)
            assert restored["state"] == "idle" and restored["error"] is None
            assert await store.claim_ready() is None
        finally:
            await db.close()

    asyncio.run(run())


def test_unusable_full_scan_yields_to_later_valid_contacts_on_local_heartbeat(tmp_path):
    async def run():
        db = Database(tmp_path)
        try:
            world, player, _, contacts = await seed(db, 65)
            store = db.offline_contact_store()
            original = store.director.approved_persona
            last = max(contacts, key=lambda c: c.conversation_id.value)
            calls = []

            async def mostly_bad(session, scope, character, **kwargs):
                calls.append(character)
                if character != last.character_id.value:
                    raise DirectorError("director_character_mapping_invalid")
                return await original(session, scope, character, **kwargs)

            store.director.approved_persona = mostly_bad
            await store.configure(world, player, True, 1, True, 0)
            assert len(calls) == 64
            assert (await store.snapshot(world, player))[
                "error"
            ] == "offline_candidates_unavailable"
            calls.clear()
            await store.pulse()
            assert len(calls) <= 64
            async with db._sessions() as session:
                cfg = await session.get(Settings, 1)
                prepared = json.loads(cfg.input_json)
                assert [c["character_id"] for c in prepared["characters"]] == [
                    str(last.character_id.value)
                ]
                assert cfg.error is None
            assert await store.claim_ready() is None
        finally:
            await db.close()

    asyncio.run(run())


def test_legacy_frozen_episode_is_valid_but_replaced_source_still_cancels(tmp_path, monkeypatch):
    async def run():
        db = Database(tmp_path)
        try:
            world, player, _, _ = await seed(db, 1)
            store = db.offline_contact_store()
            await store.configure(world, player, True, 1, True, 0)
            moment = datetime.now(UTC)

            class FixedDateTime(datetime):
                @classmethod
                def now(cls, tz=None):
                    return moment

            monkeypatch.setattr(persistence, "datetime", FixedDateTime)
            async with db._sessions() as session:
                cfg = await session.get(Settings, 1)
                old = json.loads(cfg.input_json)
                old.pop("input_preparation")
                old.pop("input_selection")
                for c in old["characters"]:
                    c.pop("persona_truncated")
                cfg.input_json = encode_input(old)
                cfg.last_online_at = moment - timedelta(hours=2)
                await session.commit()
            await store.pulse()
            claim = await store.claim_ready()
            assert claim is not None and claim["input"] == old
            source = UUID(old["characters"][0]["accepted_import_id"])
            imports = db.world_content_service()
            draft = await imports.prepare(
                world, "character", json_bytes(card_document()), replaces_import_id=source
            )
            await imports.commit(world, draft.item.import_id, draft.item.reviewed_hash)
            async with db._sessions() as session:
                assert not await store._valid(
                    session, await session.get(Episode, claim["episode_id"])
                )
        finally:
            await db.close()

    asyncio.run(run())


def test_unavailable_optional_public_background_does_not_block_contact_preparation(
    tmp_path, monkeypatch
):
    async def run():
        db = Database(tmp_path)
        try:
            world, player, _, _ = await seed(db, 1)
            store = db.offline_contact_store()
            monkeypatch.setattr(
                persistence,
                "read_director_background",
                AsyncMock(side_effect=DirectorError("director_background_capacity")),
            )
            await store.configure(world, player, True, 1, True, 0)
            state = await store.snapshot(world, player)
            assert state["state"] == "idle" and state["error"] is None
            assert state["input_preparation"]["selected"] == 1
            assert state["input_preparation"]["background_omitted"] is True
            async with db._sessions() as session:
                snapshot = json.loads((await session.get(Settings, 1)).input_json)
                assert snapshot["common_world_background"] == []
            assert await store.claim_ready() is None
        finally:
            await db.close()

    asyncio.run(run())


@pytest.mark.parametrize("state", ["failed", "interrupted", "delivered", "skipped"])
def test_preparation_recovery_preserves_the_actual_episode_receipt(state):
    async def run():
        world, player = uuid4(), uuid4()
        episode = SimpleNamespace(
            world_id=world,
            player_id=player,
            generation=4,
            state=state,
            error="offline_generation_failed" if state == "failed" else None,
        )
        session = SimpleNamespace(get=AsyncMock(return_value=episode))
        cfg = SimpleNamespace(
            enabled=True,
            input_json='{"eligible":true}',
            state="attention",
            error="offline_input_capacity",
            episode_id=uuid4(),
            world_id=world,
            player_id=player,
            revision=4,
        )
        await persistence.SqlAlchemyOfflineContactStore(None, None)._preparation_status(
            session, cfg
        )
        assert cfg.state == ("attention" if state in {"failed", "interrupted"} else state)
        assert cfg.error == episode.error
        session.get.assert_awaited_once()

    asyncio.run(run())


def test_empty_directory_clears_obsolete_preparation_error_without_starting_work():
    async def run():
        session = SimpleNamespace(get=AsyncMock())
        cfg = SimpleNamespace(
            enabled=True,
            episode_id=None,
            state="attention",
            error="offline_input_capacity",
            input_json=encode_input(
                {
                    "eligible": False,
                    "input_preparation": {"selected": 0, "excluded": 0},
                }
            ),
        )
        await persistence.SqlAlchemyOfflineContactStore(None, None)._preparation_status(
            session, cfg
        )
        assert cfg.state == "idle" and cfg.error is None
        session.get.assert_not_awaited()

    asyncio.run(run())
