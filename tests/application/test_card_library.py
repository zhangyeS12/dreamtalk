"""Synthetic SQLite/Kernel regressions; no user saves, provider or desktop process."""

import asyncio
import io
from uuid import UUID, uuid4

import pytest
from card_fixtures import card_document, json_bytes
from fastapi.testclient import TestClient
from livingworld.adapters.http.app import create_app
from livingworld.adapters.http.services import HttpServices
from livingworld.application.character_activity_setup import CharacterActivitySetupService
from livingworld.application.chat_conversations import ChatConversationService
from livingworld.application.command_handler import CommandHandler
from livingworld.application.commands import CreateWorld
from livingworld.application.content import ContentConflictError
from livingworld.application.content_authoring import EditorDraft
from livingworld.application.player_event_feed import PlayerEventFeedService
from livingworld.application.runtime import RuntimeStatus, ShutdownRequests
from livingworld.application.simulation_clock import EffectiveWorldTimeSource, SystemMonotonicClock
from livingworld.domain.content.models import CharacterDefinition, ContentSourceKind
from livingworld.domain.contracts import RequestId
from livingworld.domain.identifiers import WorldId
from livingworld.infrastructure.clock import SystemWallClock
from livingworld.infrastructure.logging import StructuredLogger
from livingworld.infrastructure.persistence import Database
from livingworld.infrastructure.persistence.models import CharacterRecord, CharacterStateRecord
from livingworld.infrastructure.persistence.world_deletion import SqlAlchemyWorldDeletionStore
from PIL import Image
from sqlalchemy import func, select


async def setup_library(path):
    db = Database(path)
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
            CreateWorld(request_id=RequestId(uuid4()), world_id=world, name="synthetic")
        )
    content = db.world_content_service()
    players = PlayerEventFeedService(db.player_event_feed_store())
    chats = ChatConversationService(db.chat_conversation_store(), content, players, handler)
    activities = CharacterActivitySetupService(
        db.character_activity_directory(), chats, players, handler
    )
    return db, worlds, content, db.card_library_service(content, activities)


def root(item):
    return next(value for value in item.contents if isinstance(value, CharacterDefinition))


def test_delete_template_keeps_world_copies_runtime_identity_and_immutable_source(tmp_path):
    async def run():
        db, worlds, content, library = await setup_library(tmp_path)
        try:
            preview = await library.preview(payload=json_bytes(card_document()))
            card = await library.commit(
                preview.preview_id, preview.card.card_id, preview.card.reviewed_hash
            )
            accepted = []
            for world in worlds:
                pending = await library.prepare_join(card.card_id, world, card.revision)
                accepted.append(
                    await library.commit_join(
                        card.card_id,
                        world,
                        pending.item.import_id,
                        pending.item.reviewed_hash,
                        None,
                    )
                )
            edit = await library.preview(
                editor=EditorDraft(kind="character", name="pending edit"),
                card_id=card.card_id,
                expected_revision=card.revision,
            )
            async with db._sessions() as session:
                before = await session.scalar(select(func.count()).select_from(CharacterRecord))
            result = await library.remove(card.card_id, card.revision)
            assert result == {"removed": True, "packs": []}
            assert await library.store.find(card.card_id) is None
            assert edit.preview_id not in library._pending
            for world, item in zip(worlds, accepted, strict=True):
                assert root(await content.store.find(item.import_id)) == root(item)
                assert await library.store.world_link(card.card_id, world) is None
                assert (await content.store.list_imports(world))[0].import_id == item.import_id
            async with db._sessions() as session:
                assert (
                    await session.scalar(select(func.count()).select_from(CharacterRecord))
                    == before
                )
            assert (
                await library.repository.load_raw_import(card.draft.raw_imports[0].import_id)
            ).original_payload == card.draft.raw_imports[0].original_payload
        finally:
            await db.close()

    asyncio.run(run())


def test_review_snapshot_identity_no_location_restart_and_world_erasure(tmp_path):
    async def run():
        db, worlds, content, library = await setup_library(tmp_path)
        try:
            payload = json_bytes(card_document())
            draft = await library.preview(payload=payload)
            assert await library.store.list() == []
            with pytest.raises(ContentConflictError):
                await library.commit(draft.preview_id, draft.card.card_id, "0" * 64)
            card = await library.commit(
                draft.preview_id, draft.card.card_id, draft.card.reviewed_hash
            )
            assert await library.commit(draft.preview_id, card.card_id, card.reviewed_hash) == card
            raw = card.draft.raw_imports[0]
            assert raw.original_payload == payload
            duplicate = await library.preview(payload=payload)
            other = await library.commit(
                duplicate.preview_id, duplicate.card.card_id, duplicate.card.reviewed_hash
            )
            assert root(other).content_id != root(card).content_id
            accepted = []
            for world in worlds:
                preview = await library.prepare_join(card.card_id, world, card.revision)
                assert not await content.store.list_imports(world)
                assert (
                    await library.prepare_join(card.card_id, world, card.revision)
                ).item == preview.item
                saved = await library.commit_join(
                    card.card_id, world, preview.item.import_id, preview.item.reviewed_hash, None
                )
                assert (
                    await library.commit_join(
                        card.card_id, world, saved.import_id, saved.reviewed_hash, None
                    )
                ).import_id == saved.import_id
                accepted.append(saved)
                with pytest.raises(ContentConflictError, match="already_added"):
                    await library.prepare_join(card.card_id, world, card.revision)
            assert len({root(item).content_id for item in [card, *accepted]}) == 3
            async with db._sessions() as session:
                assert await session.scalar(select(func.count()).select_from(CharacterRecord)) == 2
                # None is absence of physical state, not an invented location.
                assert (
                    await session.scalar(select(func.count()).select_from(CharacterStateRecord))
                    == 0
                )
            edit = await library.preview(
                editor=EditorDraft(
                    kind="character", name="new template", description="new description"
                ),
                card_id=card.card_id,
                expected_revision=1,
            )
            revised = await library.commit(edit.preview_id, card.card_id, edit.card.reviewed_hash)
            assert root(revised).provenance.source_kind is ContentSourceKind.NATIVE
            assert revised.draft.raw_imports[0].original_payload == payload
            assert (
                root(await content.store.find(accepted[0].import_id)).display_name
                == root(card).display_name
            )
            assert (
                root(await content.store.find(accepted[1].import_id)).description
                == root(card).description
            )
            # World edits keep the origin link on the current leaf; removal allows a fresh copy.
            replacement = await content.prepare(
                worlds[0], "character", payload, accepted[0].import_id
            )
            current = await content.commit(
                worlds[0], replacement.item.import_id, replacement.item.reviewed_hash
            )
            assert (await library.store.world_link(card.card_id, worlds[0]))[
                "import_id"
            ] == current.import_id
            await content.store.remove_character(worlds[0], current.import_id)
            again = await library.prepare_join(card.card_id, worlds[0], revised.revision)
            rejoined = await library.commit_join(
                card.card_id, worlds[0], again.item.import_id, again.item.reviewed_hash, None
            )
            assert rejoined.import_id != current.import_id
            assert root(rejoined).display_name == "new template"
            # Removing one entire world must not erase the source card or the other copy.
            await SqlAlchemyWorldDeletionStore(db._sessions).purge(worlds[0], "synthetic")
            assert (await library.store.load(card.card_id)).draft.raw_imports[
                0
            ].original_payload == payload
            assert await content.store.find(accepted[1].import_id)
            assert (await library.store.summary(card.card_id))["world_ids"] == [
                str(worlds[1].value)
            ]
        finally:
            await db.close()
        reopened = Database(tmp_path)
        try:
            await reopened.initialize()
            from livingworld.infrastructure.persistence.card_library import CardLibraryStore

            saved = await CardLibraryStore(reopened._sessions).load(card.card_id)
            assert saved.name == "new template"
            assert saved.draft.raw_imports[0].original_payload == payload
        finally:
            await reopened.close()

    asyncio.run(run())


def face():
    return {
        "layout": "portrait",
        "color": "#24354c",
        "accent": "#dfc78f",
        "material": "matte",
        "frame": True,
        "image_digest": None,
        "source_digest": None,
        "crop": None,
        "image_opacity": 80,
        "layers": [],
    }


def design():
    return {
        "version": 1,
        "display_name": "visual only",
        "subtitle": "",
        "glyph": "✦",
        "front": face(),
        "back": face(),
    }


@pytest.fixture
def api(tmp_path):
    db, worlds, content, library = asyncio.run(setup_library(tmp_path))
    app = create_app(
        status=RuntimeStatus("test", "generation"),
        shutdown=ShutdownRequests(),
        session_token="synthetic-session",
        initialize=lambda: None,
        logger=StructuredLogger(io.StringIO()),
        services=HttpServices(world_content=content, card_library=library),
    )
    with TestClient(app, base_url="http://127.0.0.1") as client:
        yield client, worlds, library
    asyncio.run(db.close())


def test_authenticated_review_design_cas_image_crop_and_namespace(api):
    client, worlds, library = api
    base = "/api/v1/card-library"
    headers = {"Authorization": "Bearer synthetic-session"}
    assert client.get(base).status_code == 401
    pending = client.post(
        base + "/editor/preview",
        headers=headers,
        json={"draft": {"kind": "character", "name": "synthetic"}},
    )
    assert pending.status_code == 200, pending.text
    preview = pending.json()
    assert client.get(base, headers=headers).json() == []
    saved = client.post(
        base + f"/previews/{preview['preview_id']}/commit",
        headers=headers,
        json={"card_id": preview["card_id"], "reviewed_hash": preview["reviewed_hash"]},
    )
    assert saved.status_code == 200, saved.text
    card = saved.json()
    path = base + "/" + card["card_id"]
    assert client.get(path, headers=headers).json()["draft"]["name"] == "synthetic"
    image = io.BytesIO()
    photo = Image.new("RGB", (160, 100), "red")
    photo.paste("blue", (80, 0, 160, 100))
    photo.save(image, format="PNG")
    uploaded = client.post(path + "/images", headers=headers, content=image.getvalue())
    assert uploaded.status_code == 200, uploaded.text
    digest = uploaded.json()["digest"]
    invalid = {"x": 50, "y": 0, "width": 50, "height": 100, "rotation": 0}
    assert (
        client.post(path + f"/images/{digest}/crop", headers=headers, json=invalid).status_code
        == 422
    )
    crop = {"x": 50, "y": 0, "width": 50, "height": 50, "rotation": 0}
    cropped = client.post(path + f"/images/{digest}/crop", headers=headers, json=crop)
    assert cropped.status_code == 200, cropped.text
    cropped_digest = cropped.json()["digest"]
    rendered = Image.open(
        io.BytesIO(client.get(path + f"/images/{cropped_digest}", headers=headers).content)
    )
    assert rendered.size == (1200, 757)
    assert rendered.getpixel((600, 378))[2] > 230
    assert client.get(path + f"/images/{digest}", headers=headers).content == image.getvalue()
    value = design()
    value["front"].update(image_digest=cropped_digest, source_digest=digest, crop=crop)
    update = {"expected_revision": 1, "design": value}
    result = client.put(path + "/design", headers=headers, json=update)
    assert result.status_code == 200, result.text
    assert result.json()["revision"] == 2
    assert result.json()["design"]["back"]["image_digest"] is None
    assert client.put(path + "/design", headers=headers, json=update).status_code == 200
    value["back"]["color"] = "#000000"
    assert client.put(path + "/design", headers=headers, json=update).status_code == 409
    # Card presentation cannot overwrite the actual character name or prompt content.
    assert client.get(path, headers=headers).json()["draft"]["name"] == "synthetic"
    foreign = base + f"/{uuid4()}/images/{digest}"
    assert client.get(foreign, headers=headers).status_code == 404
    value["front"]["image_digest"] = "a" * 64
    assert (
        client.put(
            path + "/design", headers=headers, json={"expected_revision": 2, "design": value}
        ).status_code
        == 404
    )
    value["front"]["color"] = "red; background:url(https://invalid)"
    assert (
        client.put(
            path + "/design", headers=headers, json={"expected_revision": 2, "design": value}
        ).status_code
        == 422
    )
    join = path + f"/worlds/{worlds[0].value}"
    prepared = client.post(join + "/preview", headers=headers, json={"expected_revision": 2})
    assert prepared.status_code == 200, prepared.text
    item = prepared.json()["content"]
    confirmation = {
        "import_id": item["import_id"],
        "reviewed_hash": item["reviewed_hash"],
        "initial_location_id": None,
    }
    assert client.post(join + "/commit", headers=headers, json=confirmation).status_code == 200
    assert client.post(join + "/commit", headers=headers, json=confirmation).status_code == 200
    assert client.get(base, headers=headers).json()[0]["world_ids"] == [str(worlds[0].value)]


def test_stale_native_preview_cannot_overwrite_saved_card_or_join(api):
    client, worlds, library = api

    async def run():
        first = await library.preview(editor=EditorDraft(kind="character", name="A"))
        card = await library.commit(first.preview_id, first.card.card_id, first.card.reviewed_hash)
        a = await library.preview(
            editor=EditorDraft(kind="character", name="B"),
            card_id=card.card_id,
            expected_revision=1,
        )
        b = await library.preview(
            editor=EditorDraft(kind="character", name="C"),
            card_id=card.card_id,
            expected_revision=1,
        )
        join = await library.prepare_join(card.card_id, worlds[0], 1)
        await library.commit(a.preview_id, card.card_id, a.card.reviewed_hash)
        with pytest.raises(ContentConflictError):
            await library.commit(b.preview_id, card.card_id, b.card.reviewed_hash)
        with pytest.raises(ContentConflictError):
            await library.commit_join(
                card.card_id, worlds[0], join.item.import_id, join.item.reviewed_hash, None
            )
        assert not await library.world_content.store.list_imports(worlds[0])
        assert (await library.store.load(card.card_id)).name == "B"

    asyncio.run(run())


def test_sparse_library_edit_keeps_long_accepted_text_and_original_file(api):
    client, worlds, library = api
    headers = {"Authorization": "Bearer synthetic-session"}
    document = card_document()
    document["data"]["description"] = "long accepted description " * 1000
    payload = json_bytes(document)
    preview = client.post(
        "/api/v1/card-library/import/preview", headers=headers, content=payload
    ).json()
    saved = client.post(
        f"/api/v1/card-library/previews/{preview['preview_id']}/commit",
        headers=headers,
        json={"card_id": preview["card_id"], "reviewed_hash": preview["reviewed_hash"]},
    )
    assert saved.status_code == 200
    path = "/api/v1/card-library/" + preview["card_id"]
    assert (
        client.get(path, headers=headers).json()["draft"]["description"]
        == document["data"]["description"]
    )
    revised = client.post(
        path + "/editor/preview-changes?expected_revision=1",
        headers=headers,
        json={"fields": {"personality": "a short intentional edit"}},
    )
    assert revised.status_code == 200, revised.text
    change = revised.json()
    assert change["content"]["characters"][0]["description"] == document["data"]["description"]
    confirmation = client.post(
        f"/api/v1/card-library/previews/{change['preview_id']}/commit",
        headers=headers,
        json={"card_id": change["card_id"], "reviewed_hash": change["reviewed_hash"]},
    )
    assert confirmation.status_code == 200
    card = asyncio.run(library.store.load(UUID(preview["card_id"])))
    assert card.draft.raw_imports[0].original_payload == payload
    assert root(card).personality == "a short intentional edit"


@pytest.mark.parametrize("table", ["card_library", "card_library_images", "card_library_worlds"])
def test_update_continuity_rejects_changed_library_payload_with_same_identity(tmp_path, table):
    import sqlite3

    from livingworld.infrastructure.save_database import _verify_database_continuity
    from livingworld.infrastructure.save_errors import SaveSafetyError

    saved, app = tmp_path / "saved", tmp_path / "app"
    for folder, payload in [(saved, "original"), (app / "data", "changed")]:
        folder.mkdir(parents=True)
        with sqlite3.connect(folder / "runtime.sqlite3") as connection:
            connection.execute(f'CREATE TABLE "{table}" (id TEXT PRIMARY KEY, payload TEXT)')
            connection.execute(f'INSERT INTO "{table}" VALUES (?, ?)', ("same identity", payload))
    with pytest.raises(SaveSafetyError, match="save_update_content_changed"):
        _verify_database_continuity(app, saved, frozen=True)


def test_complete_share_roundtrip_across_databases_and_independent_world(tmp_path):
    import zipfile
    from dataclasses import asdict

    from livingworld.application.card_design import DesignWrite
    from livingworld.application.imports import ContentImportError
    from livingworld.application.world_covers import CoverCrop
    from livingworld.infrastructure.imports.character_cards import CharacterCardImporter

    async def run():
        src, _, _, sender = await setup_library(tmp_path / "sender")
        dst, worlds, _, receiver = await setup_library(tmp_path / "receiver")
        try:
            document = card_document()
            document["data"]["description"] = "complete description " * 1000
            original = json_bytes(document)
            preview = await sender.preview(payload=original)
            card = await sender.commit(
                preview.preview_id, preview.card.card_id, preview.card.reviewed_hash
            )
            look = design()
            look["back"].update(color="#49354e", material="holo")
            look["back"]["layers"] = [
                {
                    "id": "note",
                    "anchor": "center",
                    "kind": "text",
                    "text": "independent back",
                    "x": 42,
                    "y": 58,
                    "size": 19,
                    "rotation": 17,
                    "opacity": 73,
                    "color": "#ffffff",
                }
            ]
            originals = {}
            for side, color in [("front", "red"), ("back", "blue")]:
                buffer = io.BytesIO()
                Image.new("RGB", (800, 505), color).save(buffer, format="PNG")
                source = await sender.upload(card.card_id, buffer.getvalue())
                crop = CoverCrop(x=0, y=0, width=100, height=100, rotation=0)
                cropped = await sender.crop(card.card_id, source["digest"], crop)
                look[side].update(
                    source_digest=source["digest"],
                    image_digest=cropped["digest"],
                    crop=asdict(crop),
                )
                originals[source["digest"]] = buffer.getvalue()
            look = DesignWrite.model_validate(look).model_dump()
            await sender.save_design(card.card_id, 1, look)
            shared = await sender.export(card.card_id, 2)
            assert shared.filename.endswith(".charx")
            assert shared.payload == (await sender.export(card.card_id, 2)).payload
            public = CharacterCardImporter().parse(
                shared.payload, imported_at=SystemWallClock().now_utc()
            )
            assert root(public.draft).description == document["data"]["description"]
            with zipfile.ZipFile(io.BytesIO(shared.payload)) as archive:
                assert set(archive.namelist()) == {
                    "card.json",
                    "dreamtalk.json",
                    "dreamtalk.lwcontent",
                    *[
                        f"assets/x_dreamtalk/images/{d}"
                        for d in [
                            *originals,
                            look["front"]["image_digest"],
                            look["back"]["image_digest"],
                        ]
                    ],
                }
            incoming = await receiver.preview(payload=shared.payload)
            assert incoming.shared and incoming.card.design == look
            assert len(incoming.images) == 4
            assert await receiver.store.list() == []
            # Missing or changed image bytes cannot silently become a text-only import.
            with zipfile.ZipFile(io.BytesIO(shared.payload)) as archive:
                share_files = {name: archive.read(name) for name in archive.namelist()}
            photo_path = f"assets/x_dreamtalk/images/{look['front']['source_digest']}"
            for omit in (True, False):
                damaged = io.BytesIO()
                with zipfile.ZipFile(damaged, "w") as archive:
                    for name, data in share_files.items():
                        if name == photo_path:
                            if omit:
                                continue
                            data = b"changed image"
                        archive.writestr(name, data)
                with pytest.raises(ContentImportError):
                    await receiver.preview(payload=damaged.getvalue())
                assert await receiver.store.list() == []
            assert receiver.preview_image(incoming.preview_id, look["front"]["image_digest"])[0]
            with pytest.raises(ContentConflictError):
                await receiver.commit(incoming.preview_id, incoming.card.card_id, "f" * 64)
            saved = await receiver.commit(
                incoming.preview_id, incoming.card.card_id, incoming.card.reviewed_hash
            )
            assert saved.card_id != card.card_id
            assert root(saved).content_id != root(card).content_id
            assert root(saved).description == root(card).description
            assert any(raw.original_payload == original for raw in saved.draft.raw_imports)
            assert any(raw.original_payload == shared.payload for raw in saved.draft.raw_imports)
            assert saved.design == look
            for digest, data in originals.items():
                assert (await receiver.image(saved.card_id, digest))[0] == data
            # Received originals can still be re-cropped, not merely displayed as flattened faces.
            assert await receiver.crop(
                saved.card_id, look["back"]["source_digest"], CoverCrop(**look["back"]["crop"])
            )
            # Re-sharing does not nest previous whole share archives or include world copies.
            again = await receiver.export(saved.card_id, saved.revision)
            assert len(again.payload) < len(shared.payload) + 1024
            join = await receiver.prepare_join(saved.card_id, worlds[0], saved.revision)
            await receiver.commit_join(
                saved.card_id, worlds[0], join.item.import_id, join.item.reviewed_hash, None
            )
            assert (await receiver.export(saved.card_id, saved.revision)).payload == again.payload
            async with dst._sessions() as session:
                assert (
                    await session.scalar(select(func.count()).select_from(CharacterStateRecord))
                    == 0
                )
            await dst.close()
            reopened = Database(tmp_path / "receiver")
            await reopened.initialize()
            try:
                restored = reopened.card_library_service(reopened.world_content_service(), None)
                assert (await restored.store.load(saved.card_id)).design == look
                assert (await restored.image(saved.card_id, look["front"]["source_digest"]))[
                    0
                ] == originals[look["front"]["source_digest"]]
            finally:
                await reopened.close()
        finally:
            await src.close()
            await dst.close()

    asyncio.run(run())


def test_share_http_snapshot_auth_and_rejected_packages_leave_no_card(api):
    import json
    import zipfile

    client, _, _ = api
    base = "/api/v1/card-library"
    headers = {"Authorization": "Bearer synthetic-session"}
    preview = client.post(
        base + "/editor/preview",
        headers=headers,
        json={"draft": {"kind": "character", "name": "Share synthetic"}},
    ).json()
    card = client.post(
        base + f"/previews/{preview['preview_id']}/commit",
        headers=headers,
        json={"card_id": preview["card_id"], "reviewed_hash": preview["reviewed_hash"]},
    ).json()
    path = base + "/" + card["card_id"]
    assert client.get(path + "/export/info?expected_revision=1").status_code == 401
    info = client.get(path + "/export/info?expected_revision=1", headers=headers)
    assert info.status_code == 200, info.text
    info = info.json()
    response = client.get(
        path + f"/export?expected_revision=1&expected_digest={info['digest']}", headers=headers
    )
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    assert (
        client.get(
            path + "/export?expected_revision=2&expected_digest=" + info["digest"], headers=headers
        ).status_code
        == 409
    )
    assert (
        client.get(
            path + "/export?expected_revision=1&expected_digest=" + "a" * 64, headers=headers
        ).status_code
        == 409
    )
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}

    def encode(changed):
        target = io.BytesIO()
        with zipfile.ZipFile(target, "w") as archive:
            for name, data in changed.items():
                archive.writestr(name, data)
        return target.getvalue()

    manifest = json.loads(files["dreamtalk.json"])
    for changes in [
        {"dreamtalk.json": json_bytes({**manifest, "version": 2})},
        {"card.json": b"{}"},
        {"dreamtalk.json": json_bytes({**manifest, "design": {"version": 1}})},
        {"extra.js": b"not executable"},
        {"dir/../extra": b"invalid path"},
        {"dreamtalk.lwcontent": b"broken"},
    ]:
        result = client.post(
            base + "/import/preview", headers=headers, content=encode({**files, **changes})
        )
        assert result.status_code == 422, result.text
        assert len(client.get(base, headers=headers).json()) == 1
    incoming = client.post(base + "/import/preview", headers=headers, content=response.content)
    assert incoming.status_code == 200, incoming.text
    incoming = incoming.json()
    assert incoming["shared"] and incoming["image_count"] == 0
    assert len(client.get(base, headers=headers).json()) == 1
    client.post(base + f"/previews/{incoming['preview_id']}/discard", headers=headers)
    assert (
        client.get(
            base + f"/previews/{incoming['preview_id']}/images/" + "a" * 64, headers=headers
        ).status_code
        == 422
    )
