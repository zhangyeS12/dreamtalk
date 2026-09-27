import asyncio
from dataclasses import replace
from uuid import uuid4

import pytest
from card_fixtures import card_document, json_bytes
from livingworld.application.command_handler import CommandHandler
from livingworld.application.commands import CreateWorld
from livingworld.application.content import ContentConflictError
from livingworld.application.errors import EntityNotFoundError
from livingworld.application.imports import ContentImportError
from livingworld.application.simulation_clock import EffectiveWorldTimeSource, SystemMonotonicClock
from livingworld.domain.content.models import CharacterDefinition, ContentRevision
from livingworld.domain.contracts import RequestId
from livingworld.domain.identifiers import WorldId
from livingworld.infrastructure.clock import SystemWallClock
from livingworld.infrastructure.persistence import Database
from livingworld.infrastructure.persistence.models import (
    CharacterRecord,
    WorldContentImportRecord,
    WorldEventRecord,
)
from lorebook_fixtures import book_document
from sqlalchemy import func, select


def test_world_import_preview_atomic_retry_isolation_snapshot_and_restart(tmp_path):
    async def run():
        db = Database(tmp_path)
        await db.initialize()
        clock = SystemWallClock()
        handler = CommandHandler(
            db.unit_of_work,
            clock,
            world_time_source=EffectiveWorldTimeSource(clock, SystemMonotonicClock()),
        )
        worlds = [WorldId(uuid4()), WorldId(uuid4())]
        for world in worlds:
            await handler.execute(
                CreateWorld(request_id=RequestId(uuid4()), world_id=world, name="world_a")
            )
        service = db.world_content_service()
        document = card_document()
        document["data"]["tags"] = ["npc", "", "   "]
        payload = json_bytes(document)
        pending = await service.prepare(worlds[0], "character", payload)
        assert pending.preview.warnings
        assert await service.store.list_imports(worlds[0]) == ()
        with pytest.raises(ContentConflictError):
            await service.commit(worlds[1], pending.item.import_id, pending.item.reviewed_hash)
        with pytest.raises(ContentConflictError):
            await service.commit(worlds[0], pending.item.import_id, "0" * 64)
        first, retry = await asyncio.gather(
            *(
                service.commit(worlds[0], pending.item.import_id, pending.item.reviewed_hash)
                for _ in range(2)
            )
        )
        assert first == retry
        assert len(await service.store.list_imports(worlds[0])) == 1
        other = await service.prepare(worlds[1], "character", payload)
        second = await service.commit(worlds[1], other.item.import_id, other.item.reviewed_hash)
        assert first.contents[0].content_id != second.contents[0].content_id
        repository = db.content_repository()
        root = next(item for item in first.contents if isinstance(item, CharacterDefinition))
        # Library edits must not alter the world's accepted snapshot.
        changed = replace(root, description="library edit", revision=ContentRevision(1))
        draft = replace(
            pending.preview.content.draft,
            contents=tuple(changed if item == root else item for item in first.contents),
        )
        await repository.save(draft, {item.content_id: item.revision for item in first.contents})
        assert (await service.store.find(first.import_id)).contents == first.contents
        raw = pending.preview.content.draft.raw_imports[0]
        assert (await repository.load_raw_import(raw.import_id)).original_payload == payload
        book = await service.prepare(worlds[0], "lorebook", json_bytes(book_document()))
        await service.commit(worlds[0], book.item.import_id, book.item.reviewed_hash)
        document["data"]["description"] = "Updated only in first world"
        replacement = await service.prepare(
            worlds[0], "character", json_bytes(document), first.import_id
        )
        stale_replacement = await service.prepare(
            worlds[0], "character", json_bytes(document), first.import_id
        )
        with pytest.raises(ContentConflictError):
            await service.prepare(worlds[1], "character", payload, first.import_id)
        updated = await service.commit(
            worlds[0], replacement.item.import_id, replacement.item.reviewed_hash
        )
        with pytest.raises(ContentConflictError):
            await service.commit(
                worlds[0],
                stale_replacement.item.import_id,
                stale_replacement.item.reviewed_hash,
            )
        current = await service.store.list_imports(worlds[0])
        assert len(current) == 2
        assert updated in current and first not in current
        assert (await service.store.list_imports(worlds[1]))[0] == second
        assert await service.commit(worlds[0], updated.import_id, updated.reviewed_hash) == updated
        async with db._sessions() as session:
            assert await session.scalar(select(func.count()).select_from(WorldEventRecord)) == 2
            assert await session.scalar(select(func.count()).select_from(CharacterRecord)) == 0
        await db.close()
        reopened = Database(tmp_path)
        await reopened.initialize()
        restored = reopened.world_content_service()
        assert await restored.commit(worlds[0], first.import_id, first.reviewed_hash) == first
        assert len(await restored.store.list_imports(worlds[0])) == 2
        assert updated in await restored.store.list_imports(worlds[0])
        assert len(await restored.store.list_imports(worlds[1])) == 1
        await reopened.close()

    asyncio.run(run())


def test_preview_bounds_discard_and_failed_transaction(tmp_path, monkeypatch):
    async def run():
        db = Database(tmp_path)
        await db.initialize()
        clock = SystemWallClock()
        world = WorldId(uuid4())
        handler = CommandHandler(
            db.unit_of_work,
            clock,
            world_time_source=EffectiveWorldTimeSource(clock, SystemMonotonicClock()),
        )
        await handler.execute(
            CreateWorld(request_id=RequestId(uuid4()), world_id=world, name="world_a")
        )
        service = db.world_content_service()
        payload = json_bytes(card_document())
        with pytest.raises(EntityNotFoundError):
            await service.prepare(WorldId(uuid4()), "character", payload)
        first = await service.prepare(world, "character", payload)
        second = await service.prepare(world, "character", payload)
        with pytest.raises(ContentImportError, match="capacity"):
            await service.prepare(world, "character", payload)
        service.discard(world, second.item.import_id)
        with pytest.raises(ContentImportError, match="expired"):
            await service.commit(world, second.item.import_id, second.item.reviewed_hash)
        from livingworld.infrastructure.persistence import world_content

        original = world_content.save_content_draft

        async def fail_after_save(*args):
            await original(*args)
            raise RuntimeError("simulated failure before world binding")

        monkeypatch.setattr(world_content, "save_content_draft", fail_after_save)
        with pytest.raises(RuntimeError):
            await service.commit(world, first.item.import_id, first.item.reviewed_hash)
        assert await db.content_repository().load(first.item.contents[0].content_id) is None
        async with db._sessions() as session:
            assert (
                await session.scalar(select(func.count()).select_from(WorldContentImportRecord))
                == 0
            )
        await db.close()

    asyncio.run(run())


def test_world_content_http_auth_preview_commit_and_read(tmp_path):
    import io

    from fastapi.testclient import TestClient
    from livingworld.adapters.http.app import create_app
    from livingworld.application.runtime import RuntimeStatus, ShutdownRequests
    from livingworld.infrastructure.logging import StructuredLogger

    database = Database(tmp_path)
    world = WorldId(uuid4())

    async def setup():
        await database.initialize()
        clock = SystemWallClock()
        handler = CommandHandler(
            database.unit_of_work,
            clock,
            world_time_source=EffectiveWorldTimeSource(clock, SystemMonotonicClock()),
        )
        await handler.execute(
            CreateWorld(request_id=RequestId(uuid4()), world_id=world, name="test_world")
        )

    asyncio.run(setup())
    logs = io.StringIO()
    app = create_app(
        RuntimeStatus("test", "generation"),
        ShutdownRequests(),
        "secret",
        lambda: None,
        StructuredLogger(logs),
        allowed_origins=["http://127.0.0.1:5173"],
        world_content=database.world_content_service(),
    )
    path = f"/api/v1/worlds/{world.value}/content"
    headers = {"Authorization": "Bearer secret", "Origin": "http://127.0.0.1:5173"}
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.get(path).status_code == 401
        response = client.post(
            path + "/preview?kind=character",
            headers={**headers, "Content-Type": "application/octet-stream"},
            content=json_bytes(card_document()),
        )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
        preview = response.json()
        assert preview["characters"][0]["name"]
        assert preview["characters"][0]["authored_instructions"]
        assert client.get(path, headers=headers).json() == []
        commit = client.post(
            path + f"/{preview['import_id']}/commit",
            headers=headers,
            json={"reviewed_hash": preview["reviewed_hash"]},
        )
        assert commit.status_code == 200
        assert (
            client.post(
                path + f"/{preview['import_id']}/commit",
                headers=headers,
                json={"reviewed_hash": preview["reviewed_hash"]},
            ).status_code
            == 200
        )
        assert len(client.get(path, headers=headers).json()) == 1
        lore_preview = client.post(
            path + "/preview?kind=lorebook",
            headers={**headers, "Content-Type": "application/octet-stream"},
            content=json_bytes(book_document()),
        ).json()
        lore = client.post(
            path + f"/{lore_preview['import_id']}/commit",
            headers=headers,
            json={"reviewed_hash": lore_preview["reviewed_hash"]},
        ).json()
        entry = lore["entries"][0]
        assert entry["common"] is False
        visibility_path = path + f"/{lore['import_id']}/entries/{entry['id']}/common"
        assert client.put(visibility_path, json={"common": True}).status_code == 401
        assert client.put(visibility_path, headers=headers, json={"common": True}).json() == {
            "common": True
        }
        stored_lore = next(
            item for item in client.get(path, headers=headers).json() if item["kind"] == "lorebook"
        )
        assert stored_lore["entries"][0]["common"] is True
        assert client.put(visibility_path, headers=headers, json={"common": False}).json() == {
            "common": False
        }
    assert "secret" not in logs.getvalue()
    asyncio.run(database.close())
