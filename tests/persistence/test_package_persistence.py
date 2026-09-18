"""0008 additive compatibility and the controlled immutable asset store."""

import asyncio
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.operations import Operations
from livingworld.application.content_packages import AssetBlobBinding, PackagedBlob, PackageError
from livingworld.domain.content.identifiers import ContentAssetId
from livingworld.domain.content.models import WorldContent
from livingworld.domain.content.serialization import semantic_hash, serialize_content
from livingworld.infrastructure.packages.asset_store import FileContentAssetStore
from livingworld.infrastructure.persistence import Database
from livingworld.infrastructure.persistence.errors import MigrationCompatibilityError
from livingworld.infrastructure.persistence.migration import (
    HEAD_REVISION,
    LORE_REVISION,
    _alembic_config,
)
from package_fixtures import LOCAL_ASSET, native_package
from sqlalchemy import text


@pytest.mark.parametrize("injected_failure", [False, True])
def test_0008_preserves_old_world_encoding_audit_and_rolls_back_atomically(
    tmp_path, monkeypatch, injected_failure
):
    async def run():
        database = Database(tmp_path)
        world = next(
            root for root in native_package().content.contents if isinstance(root, WorldContent)
        )
        world = replace(world, assets=(), lore_collection_ids=())
        original = Operations.create_table
        try:
            async with database.engine.begin() as connection:
                await connection.run_sync(
                    lambda sync: command.upgrade(_alembic_config(sync), LORE_REVISION)
                )
                await connection.execute(
                    text(
                        "INSERT INTO content_worlds "
                        "(content_id,title,content_version,revision,semantic_hash,canonical_json) "
                        "VALUES (:id,:title,1,:revision,:hash,:json)"
                    ),
                    {
                        "id": world.content_id.value.hex,
                        "title": world.title,
                        "revision": world.revision.value,
                        "hash": semantic_hash(world),
                        "json": serialize_content(world),
                    },
                )

            async def snapshot():
                async with database.engine.connect() as connection:
                    return {
                        table: (await connection.execute(text(f"SELECT * FROM {table}"))).all()
                        for table in (
                            "content_worlds",
                            "migration_history",
                            "schema_version",
                            "alembic_version",
                        )
                    }

            before = await snapshot()
            if injected_failure:

                def fail(self, name, *args, **kwargs):
                    if name == "content_asset_blob_bindings":
                        raise RuntimeError("injected_package_migration_failure")
                    return original(self, name, *args, **kwargs)

                monkeypatch.setattr(Operations, "create_table", fail)
                with pytest.raises(RuntimeError, match="injected_package_migration_failure"):
                    await database.initialize()
                assert await snapshot() == before
                async with database.engine.connect() as connection:
                    assert not (
                        await connection.execute(
                            text(
                                "SELECT name FROM sqlite_master WHERE name IN "
                                "('content_import_baselines','content_asset_blob_bindings')"
                            )
                        )
                    ).all()
                monkeypatch.setattr(Operations, "create_table", original)
            await database.initialize()
            await database.initialize()
            after = await snapshot()
            for table in before:
                assert after[table] == (
                    [(HEAD_REVISION,)] if table == "alembic_version" else before[table]
                )
            assert await database.content_repository().load(world.content_id) == world
            async with database.engine.connect() as connection:
                assert (
                    await connection.execute(text("SELECT * FROM content_import_baselines"))
                ).all() == []
        finally:
            await database.close()

    asyncio.run(run())


@pytest.mark.parametrize(
    "revision,mutation",
    [
        (LORE_REVISION, "CREATE TABLE content_import_baselines (unexpected TEXT)"),
        (HEAD_REVISION, "ALTER TABLE content_import_baselines ADD COLUMN unexpected TEXT"),
        (HEAD_REVISION, "DROP TABLE content_asset_blob_bindings"),
    ],
)
def test_cursor_driven_package_shape_validation_fails_closed(tmp_path, revision, mutation):
    async def run():
        database = Database(tmp_path)
        try:
            async with database.engine.begin() as connection:
                await connection.run_sync(
                    lambda sync: command.upgrade(_alembic_config(sync), revision)
                )
                await connection.execute(text(mutation))
            with pytest.raises(MigrationCompatibilityError, match="alembic_schema_"):
                await database.initialize()
            async with database.engine.connect() as connection:
                assert (
                    await connection.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar_one() == revision
        finally:
            await database.close()

    asyncio.run(run())


def test_hash_store_deduplicates_concurrently_and_separates_different_bytes(tmp_path):
    async def run():
        store = FileContentAssetStore(tmp_path)
        binding = AssetBlobBinding(
            ContentAssetId(uuid4()), sha256(LOCAL_ASSET).hexdigest(), len(LOCAL_ASSET)
        )
        blob = PackagedBlob(binding, LOCAL_ASSET)
        await asyncio.gather(*(store.materialize(blob) for _ in range(4)))
        second_data = LOCAL_ASSET + b"different"
        second = PackagedBlob(
            AssetBlobBinding(
                ContentAssetId(uuid4()), sha256(second_data).hexdigest(), len(second_data)
            ),
            second_data,
        )
        await store.materialize(second)
        assert await store.read(binding) == LOCAL_ASSET
        assert await store.read(second.binding) == second_data
        assert sum(path.is_file() for path in (tmp_path / "content-assets/sha256").rglob("*")) == 2
        assert not list((tmp_path / "content-assets/staging").iterdir())

    asyncio.run(run())


def test_missing_corrupt_blob_and_replacement_are_rejected(tmp_path):
    async def run():
        store = FileContentAssetStore(tmp_path)
        binding = AssetBlobBinding(
            ContentAssetId(uuid4()), sha256(LOCAL_ASSET).hexdigest(), len(LOCAL_ASSET)
        )
        blob = PackagedBlob(binding, LOCAL_ASSET)
        with pytest.raises(PackageError, match="asset_blob_missing"):
            await store.read(binding)
        await store.materialize(blob)
        path = tmp_path / "content-assets/sha256" / binding.digest[:2] / binding.digest
        path.write_bytes(b"corrupt")
        with pytest.raises(PackageError, match="stored_asset_integrity_mismatch"):
            await store.read(binding)
        with pytest.raises(PackageError, match="stored_asset_integrity_mismatch"):
            await store.materialize(blob)
        assert path.read_bytes() == b"corrupt"  # Never silently repair/overwrite a stored blob.

    asyncio.run(run())


def test_asset_store_rejects_source_checkout_and_linked_paths(tmp_path, monkeypatch):
    checkout = Path(__file__).resolve().parents[2]
    with pytest.raises(ValueError, match="inside_source_tree"):
        FileContentAssetStore(checkout / "writable-assets")
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda path: path == tmp_path or original(path))
    with pytest.raises(PackageError, match="asset_store_link_not_allowed"):
        FileContentAssetStore(tmp_path)
