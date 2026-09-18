"""Native portability, transaction evidence, untrusted ZIP boundaries and Stage-3 acceptance."""

import asyncio
import json
import socket
import stat
import subprocess
import urllib.request
import warnings
import zipfile
from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
from io import BytesIO
from uuid import uuid4

import pytest
from livingworld.application.commands import (
    AcquireKnowledge,
    AssertWorldTruth,
    ChangeRelationship,
    FormCharacterBelief,
)
from livingworld.application.content import ContentConflictError, ContentDraft, ContentService
from livingworld.application.content_packages import (
    ConflictDecision,
    ConflictState,
    PackageDraft,
    PackageError,
    PackageId,
    PackageLimits,
)
from livingworld.application.exports import ExportRequest, ExportService, ExportTarget
from livingworld.domain.content.identifiers import WorldContentId
from livingworld.domain.content.models import (
    CharacterDefinition,
    ContentRevision,
    LoreCollection,
    LoreEntry,
    WorldContent,
)
from livingworld.domain.content.serialization import (
    deserialize_content,
    json_value,
    semantic_hash,
    serialize_content,
    stable_json,
)
from livingworld.domain.identifiers import KnowledgeAssertionId
from livingworld.domain.knowledge import ObservationChannel
from livingworld.domain.values import WorldTime
from livingworld.infrastructure.exports.json_content import JsonContentExporter
from livingworld.infrastructure.imports.character_cards import CharacterCardImporter
from livingworld.infrastructure.imports.lorebooks import LorebookImporter
from livingworld.infrastructure.packages.lwcontent import LwContentAdapter
from livingworld.infrastructure.persistence import Database
from livingworld.infrastructure.persistence.migration import HEAD_REVISION
from package_fixtures import (
    LOCAL_ASSET,
    NOW,
    accept,
    native_package,
    service,
    simple_package,
    zip_bytes,
    zip_members,
)
from sqlalchemy import event, text


def update_member(package, root):
    return replace(
        package,
        content=replace(
            package.content,
            contents=tuple(
                root if value.content_id == root.content_id else value
                for value in package.content.contents
            ),
        ),
    )


async def local_edit(database, root, **changes):
    edited = replace(root, revision=ContentRevision(root.revision.value + 1), **changes)
    content = ContentService(database.content_repository())
    preview = content.preview(ContentDraft(contents=(edited,)))
    await content.commit(
        preview,
        reviewed_hash=preview.preview_hash,
        expected_revisions={root.content_id: root.revision},
    )
    return edited


def test_world_collection_additive_legacy_encoding_and_typed_round_trip():
    package = native_package()
    world = next(root for root in package.content.contents if isinstance(root, WorldContent))
    old = replace(world, lore_collection_ids=(), assets=())
    old_data = json_value(old)
    del old_data["lore_collection_ids"]
    old_json = stable_json({"kind": "world_content", "data": old_data})
    assert serialize_content(old) == old_json
    assert serialize_content(deserialize_content(old_json)) == old_json
    assert semantic_hash(deserialize_content(old_json)) == sha256(old_json.encode()).hexdigest()
    assert deserialize_content(serialize_content(world)) == world
    # Entry-level authored references remain separate and can coexist.
    entry = next(root for root in package.content.contents if isinstance(root, LoreEntry))
    both = replace(world, lore_entry_ids=(entry.content_id,))
    assert deserialize_content(serialize_content(both)) == both


def test_native_round_trip_preserves_ids_revisions_sources_assets_and_restart(tmp_path):
    async def run():
        package = native_package()
        source, target = Database(tmp_path / "source"), Database(tmp_path / "target")
        try:
            await source.initialize()
            await target.initialize()
            preview = await accept(source, package)
            assert all(item.state is ConflictState.NEW for item in preview.conflicts)
            exported = await service(source).export(
                package.root_ids, package_id=package.package_id, created_at_utc=NOW
            )
            assert exported.suggested_extension == ".lwcontent"
            assert exported.summary["package_id"] == package.package_id.value.hex
            assert exported.summary["format_version"] == 1
            assert exported.summary["content_counts"]["character_definition"] == 2
            assert exported.summary["packaged_blob_count"] == 1
            assert exported.summary["archive_size"] == len(exported.package_bytes)
            assert exported.summary["uncompressed_size"] is None
            with pytest.raises(TypeError):
                exported.summary["asset_count"] = 0
            manifest = json.loads(zip_members(exported.package_bytes)["manifest.json"])
            assert manifest["format_version"] == 1
            assert "baseline" not in stable_json(manifest)
            imported = service(target).parse(exported.package_bytes)
            await accept(target, imported)
            repo = target.package_repository()
            for root in package.content.contents:
                assert await repo.load(root.content_id) == root
                assert (
                    await repo.load_baseline(root.content_id)
                ).accepted_semantic_hash == semantic_hash(root)
            for asset in package.content.assets:
                assert await repo.load_asset(asset.asset_id) == asset
            for raw in package.content.raw_imports:
                assert await repo.load_raw_import(raw.import_id) == raw
            for blob in package.blobs:
                binding = await repo.load_blob_binding(blob.binding.asset_id)
                assert binding == blob.binding
                assert await target.content_asset_store().read(binding) == LOCAL_ASSET
            stored = list((target.data_dir / "content-assets/sha256").rglob("*"))
            assert sum(path.is_file() for path in stored) == 1  # Two asset IDs share one blob.
            await target.close()
            target = Database(tmp_path / "target")
            await target.initialize()
            repeated = await service(target).export(
                package.root_ids, package_id=package.package_id, created_at_utc=NOW
            )
            assert repeated.semantic_hash == exported.semantic_hash
            assert repeated.warnings == exported.warnings
            assert zip_members(repeated.package_bytes) == zip_members(exported.package_bytes)
            async with target.engine.connect() as connection:
                assert (
                    await connection.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar_one() == HEAD_REVISION
                assert (await connection.execute(text("PRAGMA foreign_key_check"))).all() == []
        finally:
            await source.close()
            await target.close()

    asyncio.run(run())


def test_dependency_closure_shared_dependencies_and_no_unrelated_library_content(tmp_path):
    async def run():
        database = Database(tmp_path)
        package = native_package()
        try:
            await database.initialize()
            await accept(database, package)
            unrelated = simple_package()
            await accept(database, unrelated)
            chars = tuple(
                root.content_id
                for root in package.content.contents
                if isinstance(root, CharacterDefinition)
            )
            result = await service(database).export(
                chars, package_id=PackageId(uuid4()), created_at_utc=NOW
            )
            roots = result.package.content.contents
            assert not any(isinstance(root, WorldContent) for root in roots)
            assert unrelated.root_ids[0] not in {root.content_id for root in roots}
            collections = [root.content_id for root in roots if isinstance(root, LoreCollection)]
            assert len(collections) == len(set(collections)) == 2
            world = next(
                root for root in package.content.contents if isinstance(root, WorldContent)
            )
            result = await service(database).export(
                (world.content_id,), package_id=PackageId(uuid4()), created_at_utc=NOW
            )
            assert set(world.lore_collection_ids) <= {
                root.content_id for root in result.package.content.contents
            }
            assert len(result.package.blobs) == 2
            with pytest.raises(PackageError, match="unresolved_package_dependency"):
                await service(database).export(
                    (replace(world.content_id, value=uuid4()),),
                    package_id=PackageId(uuid4()),
                    created_at_utc=NOW,
                )
        finally:
            await database.close()

    asyncio.run(run())


def test_zip_order_and_administrative_graph_order_do_not_change_semantics():
    package = native_package()
    adapter = LwContentAdapter()
    payload = adapter.write(package)
    ordered = zip_members(payload)
    reversed_zip = zip_bytes(dict(reversed(list(ordered.items()))))
    assert adapter.read(reversed_zip).semantic_hash == package.semantic_hash
    reversed_package = replace(
        package,
        root_ids=tuple(reversed(package.root_ids)),
        content=replace(
            package.content,
            contents=tuple(reversed(package.content.contents)),
            assets=tuple(reversed(package.content.assets)),
            raw_imports=tuple(reversed(package.content.raw_imports)),
        ),
        blobs=tuple(reversed(package.blobs)),
    )
    assert zip_members(adapter.write(reversed_package)) == ordered


def test_preview_summary_and_unknown_future_version_are_explicit(tmp_path):
    async def run():
        database = Database(tmp_path)
        try:
            await database.initialize()
            package = service(database).parse(LwContentAdapter().write(native_package()))
            preview = await service(database).preview(package)
            summary = preview.summary
            assert summary["content_counts"]["character_definition"] == 2
            assert summary["content_counts"]["world_content"] == 1
            assert summary["content_counts"]["lore_collection"] == 2
            assert summary["packaged_blob_count"] == 1
            assert summary["source_count"] == 2
            assert summary["uncompressed_size"] > 0 and summary["archive_size"] > 0
            assert summary["unresolved_references"] == ()
            with pytest.raises(TypeError):
                summary["source_count"] = 0
        finally:
            await database.close()

    asyncio.run(run())
    members = zip_members(LwContentAdapter().write(simple_package()))
    manifest = json.loads(members["manifest.json"])
    manifest.update(format_version=2, future_semantics={"unknown": True})
    members["manifest.json"] = stable_json(manifest).encode()
    with pytest.raises(PackageError, match="unsupported_newer_package_version"):
        LwContentAdapter().read(zip_bytes(members))


def test_false_central_directory_count_cannot_evade_entry_limit():
    payload = bytearray(LwContentAdapter().write(native_package()))
    end = payload.rfind(b"PK\x05\x06")
    payload[end + 8 : end + 12] = b"\x01\x00\x01\x00"
    with pytest.raises(PackageError, match="archive_entry_count_limit"):
        LwContentAdapter(PackageLimits(max_entries=2)).read(bytes(payload))


@pytest.mark.parametrize("state", list(ConflictState))
def test_persisted_three_way_conflict_classification_and_explicit_decisions(tmp_path, state):
    async def run():
        database = Database(tmp_path)
        package = simple_package()
        original = package.content.contents[0]
        try:
            await database.initialize()
            if state is ConflictState.DIFFERENT_NO_BASELINE:
                await local_edit_create(database, original)
            elif state is not ConflictState.NEW:
                await accept(database, package)
            if state in (ConflictState.LOCAL_MODIFIED, ConflictState.DIVERGED):
                await local_edit(database, original, description="local edit")
            if state in (
                ConflictState.INCOMING_DIFFERENT,
                ConflictState.DIVERGED,
                ConflictState.DIFFERENT_NO_BASELINE,
            ):
                package = update_member(
                    package,
                    replace(original, description="incoming edit", revision=ContentRevision(10)),
                )
            app = service(database)
            preview = await app.preview(app.parse(LwContentAdapter().write(package)))
            assert preview.conflicts[0].state is state
            if state not in (ConflictState.NEW, ConflictState.IDENTICAL):
                before = await database.package_repository().load(original.content_id)
                with pytest.raises(PackageError, match="conflict_decision_required"):
                    await app.commit(
                        preview,
                        reviewed_hash=preview.reviewed_hash,
                        decisions={},
                        accepted_at_utc=NOW,
                    )
                assert await database.package_repository().load(original.content_id) == before
        finally:
            await database.close()

    asyncio.run(run())


async def local_edit_create(database, root):
    content = ContentService(database.content_repository())
    preview = content.preview(ContentDraft(contents=(root,)))
    await content.commit(
        preview, reviewed_hash=preview.preview_hash, expected_revisions={root.content_id: None}
    )


def test_keep_preserves_baseline_replace_updates_it_and_revision_does_not_choose_winner(tmp_path):
    async def run():
        database = Database(tmp_path)
        package = simple_package()
        root = package.content.contents[0]
        try:
            await database.initialize()
            await accept(database, package)
            before = await database.package_repository().load_baseline(root.content_id)
            local = await local_edit(database, root, description="local")
            incoming = replace(root, description="incoming", revision=ContentRevision(0))
            package = update_member(package, incoming)
            app = service(database)
            preview = await app.preview(app.parse(LwContentAdapter().write(package)))
            await app.commit(
                preview,
                reviewed_hash=preview.reviewed_hash,
                decisions={root.content_id: ConflictDecision.KEEP_LOCAL},
                accepted_at_utc=NOW + timedelta(days=1),
            )
            assert await database.package_repository().load(root.content_id) == local
            assert await database.package_repository().load_baseline(root.content_id) == before
            preview = await app.preview(preview.package)
            await app.commit(
                preview,
                reviewed_hash=preview.reviewed_hash,
                decisions={root.content_id: ConflictDecision.REPLACE_WITH_INCOMING},
                accepted_at_utc=NOW + timedelta(days=2),
            )
            assert await database.package_repository().load(root.content_id) == incoming
            baseline = await database.package_repository().load_baseline(root.content_id)
            assert baseline.accepted_semantic_hash == semantic_hash(incoming)
            assert baseline.accepted_at_utc == NOW + timedelta(days=2)
        finally:
            await database.close()

    asyncio.run(run())


def test_identical_member_no_duplicate_and_missing_baseline_established(tmp_path):
    async def run():
        database = Database(tmp_path)
        package = simple_package()
        root = package.content.contents[0]
        try:
            await database.initialize()
            await local_edit_create(database, root)
            assert await database.package_repository().load_baseline(root.content_id) is None
            preview = await accept(database, package)
            assert preview.conflicts[0].state is ConflictState.IDENTICAL
            baseline = await database.package_repository().load_baseline(root.content_id)
            assert baseline.accepted_semantic_hash == semantic_hash(root)
            await accept(database, package)
            async with database.engine.connect() as connection:
                assert (
                    await connection.execute(
                        text("SELECT COUNT(*) FROM content_character_definitions")
                    )
                ).scalar_one() == 1
                assert (
                    await connection.execute(text("SELECT COUNT(*) FROM content_import_baselines"))
                ).scalar_one() == 1
        finally:
            await database.close()

    asyncio.run(run())


def test_baseline_identity_includes_kind_and_is_not_canonical_content(tmp_path):
    async def run():
        database = Database(tmp_path)
        package = simple_package()
        char = package.content.contents[0]
        world = WorldContent(
            content_id=WorldContentId(char.content_id.value),
            title="Same UUID distinct type",
            provenance=char.provenance,
        )
        package = replace(
            package,
            root_ids=(char.content_id, world.content_id),
            content=ContentDraft(contents=(char, world)),
        )
        try:
            await database.initialize()
            await accept(database, package)
            for root in package.content.contents:
                assert await database.package_repository().load(root.content_id) == root
                assert (
                    await database.package_repository().load_baseline(root.content_id)
                ).content_id == root.content_id
            async with database.engine.connect() as connection:
                assert (
                    await connection.execute(text("SELECT COUNT(*) FROM content_import_baselines"))
                ).scalar_one() == 2
            result = await service(database).export(
                package.root_ids, package_id=PackageId(uuid4()), created_at_utc=NOW
            )
            members = zip_members(result.package_bytes)
            assert package.package_id.value.hex.encode() not in b"".join(members.values())
            assert not any(
                b"accepted_at_utc" in data or b"accepted_semantic_hash" in data
                for data in members.values()
            )
        finally:
            await database.close()

    asyncio.run(run())


def test_replace_and_baseline_update_roll_back_together(tmp_path):
    async def run():
        database = Database(tmp_path)
        package = simple_package()
        original = package.content.contents[0]
        listener = None
        try:
            await database.initialize()
            await accept(database, package)
            baseline = await database.package_repository().load_baseline(original.content_id)
            incoming = update_member(
                package, replace(original, description="incoming", revision=ContentRevision(10))
            )
            app = service(database)
            preview = await app.preview(incoming)

            def fail(connection, cursor, statement, parameters, context, executemany):
                if statement.startswith("UPDATE content_import_baselines"):
                    raise RuntimeError("injected_baseline_update_failure")

            listener = fail
            event.listen(database.engine.sync_engine, "before_cursor_execute", listener)
            with pytest.raises(RuntimeError, match="injected_baseline_update_failure"):
                await app.commit(
                    preview,
                    reviewed_hash=preview.reviewed_hash,
                    decisions={original.content_id: ConflictDecision.REPLACE_WITH_INCOMING},
                    accepted_at_utc=NOW,
                )
            assert await database.package_repository().load(original.content_id) == original
            assert (
                await database.package_repository().load_baseline(original.content_id) == baseline
            )
        finally:
            if listener:
                event.remove(database.engine.sync_engine, "before_cursor_execute", listener)
            await database.close()

    asyncio.run(run())


def test_baseline_only_change_invalidates_preview_even_when_canonical_hash_is_unchanged(tmp_path):
    async def run():
        database = Database(tmp_path)
        package = simple_package()
        try:
            await database.initialize()
            await accept(database, package)
            app = service(database)
            old = await app.preview(package)
            fresh = await app.preview(package)
            await app.commit(
                fresh,
                reviewed_hash=fresh.reviewed_hash,
                decisions={},
                accepted_at_utc=NOW + timedelta(days=1),
            )
            with pytest.raises(ContentConflictError, match="preview is stale"):
                await app.commit(
                    old, reviewed_hash=old.reviewed_hash, decisions={}, accepted_at_utc=NOW
                )
        finally:
            await database.close()

    asyncio.run(run())


def test_unapproved_source_classification_and_absolute_card_asset_uri_fail_before_export():
    package = native_package()
    raw = package.content.raw_imports[0]
    changed_provenance = replace(raw.provenance, source_format="runtime_log")
    changed_source = replace(raw, provenance=changed_provenance)
    changed = replace(
        package.content,
        contents=tuple(
            replace(root, provenance=changed_provenance)
            if root.provenance.raw_import_id == raw.import_id
            else root
            for root in package.content.contents
        ),
        raw_imports=tuple(
            changed_source if value.import_id == raw.import_id else value
            for value in package.content.raw_imports
        ),
    )
    with pytest.raises(PackageError, match="source_not_classified_as_portable_content"):
        replace(package, content=changed)
    asset = package.content.assets[0]
    extensions = json_value(asset.extensions)
    extensions["character_card_descriptor"]["uri"] = "C:/private/session-token.env"
    changed = replace(
        package.content,
        assets=tuple(
            replace(value, extensions=extensions) if value.asset_id == asset.asset_id else value
            for value in package.content.assets
        ),
    )
    with pytest.raises(PackageError, match="nonportable_local_reference"):
        replace(package, content=changed)


def test_stale_preview_and_wrong_review_hash_fail_without_overwrite(tmp_path):
    async def run():
        database = Database(tmp_path)
        package = simple_package()
        root = package.content.contents[0]
        try:
            await database.initialize()
            await accept(database, package)
            incoming = update_member(
                package, replace(root, description="incoming", revision=ContentRevision(4))
            )
            app = service(database)
            preview = await app.preview(incoming)
            with pytest.raises(PackageError, match="package_review_required"):
                await app.commit(preview, reviewed_hash="bad", decisions={}, accepted_at_utc=NOW)
            local = await local_edit(database, root, description="edit after preview")
            baseline = await database.package_repository().load_baseline(root.content_id)
            with pytest.raises(ContentConflictError, match="preview is stale"):
                await app.commit(
                    preview,
                    reviewed_hash=preview.reviewed_hash,
                    decisions={root.content_id: ConflictDecision.REPLACE_WITH_INCOMING},
                    accepted_at_utc=NOW,
                )
            assert await database.package_repository().load(root.content_id) == local
            assert await database.package_repository().load_baseline(root.content_id) == baseline
        finally:
            await database.close()

    asyncio.run(run())


@pytest.mark.parametrize("point", ["asset", "database"])
def test_asset_and_database_failure_leave_no_reachable_content_or_baselines(
    tmp_path, monkeypatch, point
):
    async def run():
        database = Database(tmp_path)
        package = native_package()
        listener = None
        try:
            await database.initialize()
            app = service(database)
            preview = await app.preview(app.parse(LwContentAdapter().write(package)))
            if point == "asset":

                async def fail(blob):
                    raise RuntimeError("injected_asset_failure")

                monkeypatch.setattr(app._assets, "materialize", fail)
            else:

                def fail(connection, cursor, statement, parameters, context, executemany):
                    if statement.startswith("INSERT INTO content_import_baselines"):
                        raise RuntimeError("injected_database_failure")

                listener = fail
                event.listen(database.engine.sync_engine, "before_cursor_execute", listener)
            with pytest.raises(RuntimeError, match="injected_"):
                await app.commit(
                    preview, reviewed_hash=preview.reviewed_hash, decisions={}, accepted_at_utc=NOW
                )
            for root in package.content.contents:
                assert await database.package_repository().load(root.content_id) is None
                assert await database.package_repository().load_baseline(root.content_id) is None
            for blob in package.blobs:
                assert (
                    await database.package_repository().load_blob_binding(blob.binding.asset_id)
                    is None
                )
            async with database.engine.connect() as connection:
                for table in ("content_assets", "content_raw_imports"):
                    assert (
                        await connection.execute(text(f"SELECT COUNT(*) FROM {table}"))
                    ).scalar_one() == 0
            if point == "database":
                assert (
                    await database.content_asset_store().read(package.blobs[0].binding)
                    == LOCAL_ASSET
                )
        finally:
            if listener is not None:
                event.remove(database.engine.sync_engine, "before_cursor_execute", listener)
            await database.close()

    asyncio.run(run())


@pytest.mark.parametrize(
    "path",
    [
        "../bad",
        "/absolute",
        "C:/secret",
        "C:relative",
        "\\\\server\\share",
        "a\\..\\b",
        "a/./b",
        "a//b",
        "a/../b",
    ],
)
def test_unsafe_zip_paths_fail(path):
    members = zip_members(LwContentAdapter().write(simple_package()))
    members[path] = b"untrusted"
    with pytest.raises(PackageError, match="unsafe_archive_path"):
        LwContentAdapter().read(zip_bytes(members))


def test_nul_archive_name_rejected_using_original_untruncated_name():
    members = zip_members(LwContentAdapter().write(simple_package()))
    members["badXname"] = b"data"
    malicious = zip_bytes(members).replace(b"badXname", b"bad\x00name")
    with pytest.raises(PackageError, match="unsafe_archive_path"):
        LwContentAdapter().read(malicious)


@pytest.mark.parametrize("manifest", [True, False])
def test_duplicate_members_never_use_last_entry(manifest):
    members = zip_members(LwContentAdapter().write(simple_package()))
    name = (
        "manifest.json" if manifest else next(path for path in members if path != "manifest.json")
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        malicious = zip_bytes(members, extras=((name, b"replacement"),))
    with pytest.raises(PackageError, match="duplicate_archive_path"):
        LwContentAdapter().read(malicious)


@pytest.mark.parametrize("mode", [stat.S_IFLNK, stat.S_IFCHR, stat.S_IFIFO, stat.S_IFSOCK])
def test_symlink_and_special_archive_members_rejected(mode):
    members = zip_members(LwContentAdapter().write(simple_package()))
    info = zipfile.ZipInfo("special")
    info.create_system = 3
    info.external_attr = (mode | 0o600) << 16
    with pytest.raises(PackageError, match="unsupported_archive_member_type"):
        LwContentAdapter().read(zip_bytes(members, extras=((info, b"target"),)))


@pytest.mark.parametrize(
    "limit", ["manifest", "entries", "single", "total", "ratio", "archive", "depth"]
)
def test_centralized_limits_reject_controlled_bombs(limit):
    payload = LwContentAdapter().write(native_package())
    members = zip_members(payload)
    options = {}
    if limit == "manifest":
        options["max_manifest_bytes"] = len(members["manifest.json"]) - 1
    elif limit == "entries":
        options["max_entries"] = len(members) - 1
    elif limit == "single":
        options["max_entry_bytes"] = max(map(len, members.values())) - 1
    elif limit == "total":
        options["max_total_bytes"] = sum(map(len, members.values())) - 1
    elif limit == "ratio":
        members["bomb"] = b"a" * 10_000
        payload = zip_bytes(members, compression=zipfile.ZIP_DEFLATED)
        options["max_compression_ratio"] = 2
    elif limit == "archive":
        options["max_archive_bytes"] = len(payload) - 1
    else:
        options["max_json_depth"] = 2
    with pytest.raises(PackageError, match="limit"):
        LwContentAdapter(PackageLimits(**options)).read(payload)


def test_streaming_read_limit_enforced_even_when_metadata_is_small(monkeypatch):
    payload = LwContentAdapter().write(simple_package())
    members = zip_members(payload)
    cap = max(map(len, members.values())) + 100
    original = zipfile.ZipFile.open

    def fake(self, name, *args, **kwargs):
        filename = name.filename if isinstance(name, zipfile.ZipInfo) else name
        if filename.startswith("content/"):
            return BytesIO(b"a" * (cap + 1))
        return original(self, name, *args, **kwargs)

    monkeypatch.setattr(zipfile.ZipFile, "open", fake)
    with pytest.raises(PackageError, match="archive_streaming_size_limit"):
        LwContentAdapter(PackageLimits(max_entry_bytes=cap, read_chunk_bytes=17)).read(payload)


@pytest.mark.parametrize(
    "attack",
    [
        "hash",
        "missing",
        "unmanifested",
        "newer",
        "old",
        "identity",
        "binding",
        "duplicate_json",
        "content_version",
    ],
)
def test_integrity_manifest_and_membership_fail_closed(attack):
    members = zip_members(LwContentAdapter().write(simple_package()))
    manifest = json.loads(members["manifest.json"])
    content_path = manifest["members"][0]["path"]
    if attack == "hash":
        members[content_path] = members[content_path].replace(b"Character", b"Corrupted")
    elif attack == "missing":
        del members[content_path]
    elif attack == "unmanifested":
        members["content/extra.json"] = members[content_path]
    elif attack == "newer":
        manifest["format_version"] = 2
    elif attack == "old":
        manifest["format_version"] = 0
    elif attack == "identity":
        manifest["members"][0]["id"] = uuid4().hex
    elif attack == "binding":
        manifest["bindings"] = [{"from": {}, "to": {}, "relation": "forged"}]
    elif attack == "content_version":
        manifest["canonical_content_version"]["max"] = 2
    if attack == "duplicate_json":
        members["manifest.json"] = ('{"format":"forged",' + stable_json(manifest)[1:]).encode()
    else:
        members["manifest.json"] = stable_json(manifest).encode()
    with pytest.raises(PackageError) as error:
        LwContentAdapter().read(zip_bytes(members))
    if attack == "newer":
        assert error.value.code == "unsupported_newer_package_version"
    if attack == "hash":
        assert error.value.code == "package_integrity_mismatch"


def test_legacy_unbound_lore_and_local_absolute_resource_references_are_not_packaged():
    package = native_package()
    entry = next(root for root in package.content.contents if isinstance(root, LoreEntry))
    # Closed legacy draft is still valid for reads; package model refuses to invent ownership.
    world = next(root for root in package.content.contents if isinstance(root, WorldContent))
    legacy = replace(entry, collection_id=None)
    world = replace(world, lore_collection_ids=(), lore_entry_ids=(legacy.content_id,), assets=())
    with pytest.raises(PackageError, match="legacy_unbound_lore_not_portable"):
        PackageDraft(
            package_id=PackageId(uuid4()),
            created_at_utc=NOW,
            root_ids=(world.content_id,),
            content=ContentDraft(
                contents=(world, legacy),
                raw_imports=tuple(
                    raw
                    for raw in package.content.raw_imports
                    if raw.import_id == legacy.provenance.raw_import_id
                ),
            ),
        )
    asset = package.content.assets[-1]
    with pytest.raises(PackageError, match="nonportable_local_reference"):
        replace(
            package,
            content=replace(
                package.content,
                assets=tuple(
                    replace(value, resource_reference="D:/private/api.env")
                    if value.asset_id == asset.asset_id
                    else value
                    for value in package.content.assets
                ),
            ),
        )


def test_stage3_ecosystem_external_native_external_runtime_and_secret_isolation(
    environment, tmp_path, monkeypatch
):
    async def run():
        env, clean = environment, Database(tmp_path / "clean-import")
        package = native_package()
        canaries = (
            "C004D2_PRIVATE_BELIEF_CANARY",
            "C004D2_PLAYER_KNOWLEDGE_CANARY",
            "C004D2_CREDENTIAL_CANARY",
            "C004D2_RUNTIME_LOG_CANARY",
        )
        try:
            await env.initialize()
            await clean.initialize()
            truth = KnowledgeAssertionId(env.world, uuid4())
            await env.handler.execute(
                env.command(
                    AssertWorldTruth,
                    assertion_id=truth,
                    subject="private",
                    predicate="value",
                    value=canaries[1],
                )
            )
            await env.handler.execute(
                env.command(
                    FormCharacterBelief,
                    assertion_id=KnowledgeAssertionId(env.world, uuid4()),
                    character_id=env.alice,
                    subject="private",
                    predicate="value",
                    value=canaries[0],
                    epistemic_status="believed",
                    valid_from=WorldTime(123),
                )
            )
            await env.handler.execute(
                env.command(
                    AcquireKnowledge,
                    assertion_id=KnowledgeAssertionId(env.world, uuid4()),
                    receiver_id=env.player,
                    source_assertion_id=truth,
                    channel=ObservationChannel.TOLD,
                )
            )
            await env.handler.execute(
                env.command(
                    ChangeRelationship,
                    source_id=env.alice,
                    target_id=env.bob,
                    affinity_delta=3,
                    trust_delta=2,
                    familiarity_delta=1,
                    expected_relationship_revision=None,
                )
            )
            monkeypatch.setenv("LIVINGWORLD_TEST_CREDENTIAL", canaries[2])
            (env.path / "runtime-private.log").write_text(canaries[3], encoding="utf-8")
            await accept(env.database, package)
            before = await env.snapshot()
            await env.restart()
            app = service(env.database)

            def forbidden(*args, **kwargs):
                pytest.fail("Native packaging attempted network/shell access")

            with monkeypatch.context() as patch:
                patch.setattr(socket, "create_connection", forbidden)
                patch.setattr(subprocess, "Popen", forbidden)
                patch.setattr(urllib.request, "urlopen", forbidden)
                result = await app.export(
                    package.root_ids, package_id=package.package_id, created_at_utc=NOW
                )
                parsed = service(clean).parse(result.package_bytes)
                preview = await service(clean).preview(parsed)
                await service(clean).commit(
                    preview, reviewed_hash=preview.reviewed_hash, decisions={}, accepted_at_utc=NOW
                )
            assert await env.snapshot() == before
            members = zip_members(result.package_bytes)
            forbidden_fields = {
                "world_clock",
                "world_events",
                "command_receipts",
                "player_presence",
                "character_state",
                "world_truth",
                "character_belief",
                "player_knowledge",
                "observations",
                "runtime_memory",
                "director_plans",
                "api_keys",
                "session_tokens",
                "accepted_import_baseline",
            }
            for data in (result.package_bytes, *members.values()):
                assert not any(canary.encode() in data for canary in canaries)
            for path, data in members.items():
                if path.startswith("content/"):
                    root = json.loads(data)
                    assert root["kind"] in {
                        "world_content",
                        "character_definition",
                        "lore_collection",
                        "lore_entry",
                    }
                    assert not forbidden_fields & root["data"].keys()
            async with clean.engine.connect() as connection:
                for table in before:
                    assert (
                        await connection.execute(text(f"SELECT COUNT(*) FROM {table}"))
                    ).scalar_one() == 0
            # Full canonical snapshots are preserved, then understood external semantics round-trip.
            loaded = ContentDraft(
                contents=tuple(
                    [
                        await clean.content_repository().load(root.content_id)
                        for root in package.content.contents
                    ]
                ),
                assets=tuple(
                    [
                        await clean.content_repository().load_asset(asset.asset_id)
                        for asset in package.content.assets
                    ]
                ),
                raw_imports=tuple(
                    [
                        await clean.content_repository().load_raw_import(raw.import_id)
                        for raw in package.content.raw_imports
                    ]
                ),
            )
            assert loaded.preview_hash() == package.content.preview_hash()
            character = next(
                root
                for root in loaded.contents
                if isinstance(root, CharacterDefinition)
                and root.provenance.source_format == "chara_card_v3"
            )
            book = next(
                root
                for root in loaded.contents
                if isinstance(root, LoreCollection)
                and root.provenance.source_format == "chara_card_v3"
            )
            exporter = ExportService(JsonContentExporter())
            card = exporter.export(
                ExportRequest(
                    draft=loaded,
                    content_id=character.content_id,
                    target_format=ExportTarget.CHARACTER_CARD_V3,
                    embedded_collection_id=book.content_id,
                )
            )
            reimported = LorebookImporter().normalize_embedded(
                CharacterCardImporter().parse(card.serialized_bytes, imported_at=NOW)
            )
            assert (
                next(
                    root
                    for root in reimported.draft.contents
                    if isinstance(root, CharacterDefinition)
                ).description
                == character.description
            )
            old_card = exporter.export(
                ExportRequest(
                    draft=package.content,
                    content_id=character.content_id,
                    target_format=ExportTarget.CHARACTER_CARD_V3,
                    embedded_collection_id=book.content_id,
                )
            )
            assert json.loads(old_card.serialized_bytes) == json.loads(card.serialized_bytes)
            native_book = next(
                root
                for root in loaded.contents
                if isinstance(root, LoreCollection)
                and root.provenance.source_format == "sillytavern_world_info"
            )
            st = exporter.export(
                ExportRequest(
                    draft=loaded,
                    content_id=native_book.content_id,
                    target_format=ExportTarget.SILLYTAVERN_WORLD_INFO,
                )
            )
            old_st = exporter.export(
                ExportRequest(
                    draft=package.content,
                    content_id=native_book.content_id,
                    target_format=ExportTarget.SILLYTAVERN_WORLD_INFO,
                )
            )
            assert json.loads(st.serialized_bytes) == json.loads(old_st.serialized_bytes)
            reimported = LorebookImporter().parse(st.serialized_bytes, imported_at=NOW)
            assert sorted(
                root.content for root in reimported.draft.contents if isinstance(root, LoreEntry)
            ) == sorted(
                root.content
                for root in loaded.contents
                if isinstance(root, LoreEntry) and root.collection_id == native_book.content_id
            )
        finally:
            await env.database.close()
            await clean.close()

    asyncio.run(run())
