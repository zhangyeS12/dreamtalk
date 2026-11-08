"""Personal cards on synthetic data: confirmed ownership, no NPC or location side effects."""

import asyncio
from uuid import uuid4

import pytest
from alembic import command
from card_fixtures import card_document, card_text, json_bytes, png_bytes
from livingworld.application.player_persona import (
    PlayerPersonaDraft,
    PlayerPersonaError,
    PlayerPersonaService,
)
from livingworld.domain.identifiers import WorldId
from livingworld.infrastructure.imports.character_cards import CharacterCardImporter
from livingworld.infrastructure.persistence import Database
from livingworld.infrastructure.persistence.migration import WORLD_STYLE_REVISION, _alembic_config
from livingworld.infrastructure.persistence.models import Base, WorldRecord, WorldStyleRecord
from livingworld.infrastructure.persistence.player_persona import read_player_persona
from livingworld.infrastructure.persistence.player_persona_models import PlayerCardRecord
from sqlalchemy import func, select, text
from test_offline_contact_capacity import seed


def payload(kind="json"):
    card = card_document()
    card["data"].update(
        name="玩家专用",
        description="公开玩家身份：{{char}}，与{{user}}交谈。",
        personality="温和",
        creator_notes="PRIVATE_CREATOR_CANARY",
        system_prompt="PRIVATE_CARD_SYSTEM_CANARY",
    )
    return json_bytes(card) if kind == "json" else png_bytes(card_text("chara", card))


async def world_counts(db):
    names = {
        "world_content_imports",
        "characters",
        "character_states",
        "character_location_policies",
        "relationships",
        "locations",
        "players",
        "player_presences",
        "world_events",
    }
    assert names <= Base.metadata.tables.keys()
    async with db._sessions() as session:
        return {
            name: await session.scalar(select(func.count()).select_from(Base.metadata.tables[name]))
            for name in names
        }


@pytest.mark.parametrize("kind", ["json", "png"])
def test_card_confirm_persists_raw_bytes_and_never_creates_world_npc(tmp_path, kind):
    async def run():
        db = Database(tmp_path)
        try:
            world, player, _, contacts = await seed(db, 1)
            counts = await world_counts(db)
            graph = await db.faction_store().snapshot(world.value)
            store = db.player_persona_store()
            service = PlayerPersonaService(store, CharacterCardImporter())
            raw = payload(kind)
            choice = await service.import_card(world, raw, 0, player.value)
            assert choice.reference.scope == "player" and choice.root_import_id is None
            assert "玩家专用，与对话对象交谈" in choice.text
            draft = PlayerPersonaDraft(
                identity_name=choice.title, public_identity=choice.text, source=choice.reference
            )
            preview = await service.preview(world, draft, 0, expected_player=player.value)
            async with db._sessions() as session:
                assert await session.scalar(select(func.count()).select_from(PlayerCardRecord)) == 0
            assert (await store.snapshot(world)).revision == 0
            saved = await service.commit(world, preview.preview_id)
            assert saved.source_state == "current" and saved.source_title == "玩家专用"
            assert saved.draft.source.scope == "player"
            assert await service.commit(world, preview.preview_id) == saved
            assert await world_counts(db) == counts
            assert await db.faction_store().snapshot(world.value) == graph
            async with db._sessions() as session:
                row = await session.get(PlayerCardRecord, (world.value, player.value))
                assert row.raw_payload == raw
                assert "PRIVATE_CARD_SYSTEM_CANARY" in row.snapshot_json
                context = await read_player_persona(
                    session, world, player.value, contacts[0].root_import_id
                )
                assert context["identity_name"] == "玩家专用"
                assert "PRIVATE_CARD_SYSTEM_CANARY" not in str(context)
                assert "PRIVATE_CREATOR_CANARY" not in str(context)
            await db.close()
            db = Database(tmp_path)
            await db.initialize()
            assert await db.player_persona_store().snapshot(world) == saved
            assert await world_counts(db) == counts
        finally:
            await db.close()

    asyncio.run(run())


def test_card_reference_cannot_cross_world_and_replacements_do_not_fill_pending_slots(tmp_path):
    async def run():
        db = Database(tmp_path)
        try:
            world, player, _, _ = await seed(db, 0)
            other, other_player, _, _ = await seed(db, 0)
            service = PlayerPersonaService(db.player_persona_store(), CharacterCardImporter())
            for _ in range(4):
                choice = await service.import_card(world, payload(), 0, player.value)
            draft = PlayerPersonaDraft(
                identity_name="玩家专用", public_identity="身份", source=choice.reference
            )
            with pytest.raises(PlayerPersonaError, match="source_changed"):
                await service.preview(other, draft, 0, expected_player=other_player.value)
            forged = draft.model_copy(deep=True)
            forged.source.reviewed_hash = "0" * 64
            with pytest.raises(PlayerPersonaError, match="source_changed"):
                await service.preview(world, forged, 0)
            preview = await service.preview(world, draft, 0)
            saved = await service.commit(world, preview.preview_id)
            with pytest.raises(PlayerPersonaError, match="source_changed"):
                await service.preview(other, draft, 0)
            assert (await service.store.snapshot(other)).revision == 0
            assert await service.store.snapshot(world) == saved
            # A later import replaces this player's card atomically, not an NPC.
            counts = await world_counts(db)
            replacement = await service.import_card(world, payload("png"), 1, player.value)
            draft.source = replacement.reference
            preview = await service.preview(world, draft, 1)
            assert (await service.commit(world, preview.preview_id)).revision == 2
            assert await world_counts(db) == counts
        finally:
            await db.close()

    asyncio.run(run())


def test_old_0055_upgrade_preserves_world_style_and_identity_tables(tmp_path):
    async def run():
        db = Database(tmp_path)
        world = WorldId(uuid4())
        try:
            async with db.engine.begin() as connection:
                await connection.run_sync(
                    lambda sync: command.upgrade(_alembic_config(sync), WORLD_STYLE_REVISION)
                )
            async with db._sessions() as session, session.begin():
                session.add(WorldRecord(world_id=world.value, name="旧世界", revision=0))
                await session.flush()
                session.add(
                    WorldStyleRecord(world_id=world.value, instructions="旧风格", revision=3)
                )
            await db.initialize()
            await db.initialize()
            assert (await db.world_style_store().load(world)).instructions == "旧风格"
            async with db._sessions() as session:
                assert await session.scalar(select(func.count()).select_from(PlayerCardRecord)) == 0
                assert await session.scalar(text("SELECT count(*) FROM world_player_personas")) == 0
        finally:
            await db.close()

    asyncio.run(run())
