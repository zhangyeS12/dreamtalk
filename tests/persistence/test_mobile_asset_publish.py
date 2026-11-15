"""Portable publication semantics; real Android flock is checked in the AVD."""

import asyncio
from contextlib import contextmanager
from hashlib import sha256
from threading import Lock
from uuid import uuid4

import pytest
from livingworld.application.content_packages import AssetBlobBinding, PackagedBlob, PackageError
from livingworld.domain.content.identifiers import ContentAssetId
from livingworld.infrastructure.packages import asset_store


@pytest.fixture
def android_publisher(monkeypatch):
    # Windows has no fcntl. Exercise the Android branch with a process-local
    # lock here; the isolated Android regression checks the real flock/SELinux path.
    lock = Lock()

    @contextmanager
    def portable_lock(_path):
        with lock:
            yield

    monkeypatch.setattr(asset_store.sys, "getandroidapilevel", lambda: 35, raising=False)
    monkeypatch.setattr(asset_store, "_android_publication_lock", portable_lock)

    def forbidden_link(*_args, **_kwargs):
        raise PermissionError("synthetic_android_hardlink_denied")

    monkeypatch.setattr(asset_store.os, "link", forbidden_link)


def blob(data):
    return PackagedBlob(
        AssetBlobBinding(ContentAssetId(uuid4()), sha256(data).hexdigest(), len(data)), data
    )


def test_android_publish_deduplicates_across_store_instances(tmp_path, android_publisher):
    async def run():
        stores = [asset_store.FileContentAssetStore(tmp_path) for _ in range(3)]
        first, second = blob(b"synthetic-one"), blob(b"synthetic-two")
        await asyncio.gather(
            *(stores[i % len(stores)].materialize(first if i % 2 else second) for i in range(48))
        )
        assert await stores[0].read(first.binding) == first.data
        assert await stores[1].read(second.binding) == second.data
        root = tmp_path / "content-assets"
        assert len([p for p in (root / "sha256").rglob("*") if p.is_file()]) == 2
        assert not list((root / "staging").iterdir())

    asyncio.run(run())


def test_android_publish_never_repairs_over_corrupt_existing_bytes(tmp_path, android_publisher):
    async def run():
        store = asset_store.FileContentAssetStore(tmp_path)
        value = blob(b"synthetic-original")
        await store.materialize(value)
        target = store._path(value.binding.digest)
        target.write_bytes(b"synthetic-corrupt")
        with pytest.raises(PackageError, match="stored_asset_integrity_mismatch"):
            await store.materialize(value)
        assert target.read_bytes() == b"synthetic-corrupt"

    asyncio.run(run())


def test_android_failed_publication_cleans_staging_and_can_be_retried(
    tmp_path, android_publisher, monkeypatch
):
    async def run():
        store = asset_store.FileContentAssetStore(tmp_path)
        value = blob(b"synthetic-interrupted")
        rename = asset_store.os.rename

        def fail(*_args):
            raise PermissionError("synthetic_publish_interrupted")

        monkeypatch.setattr(asset_store.os, "rename", fail)
        with pytest.raises(PermissionError):
            await store.materialize(value)
        assert not store._path(value.binding.digest).exists()
        assert not list((tmp_path / "content-assets/staging").iterdir())
        monkeypatch.setattr(asset_store.os, "rename", rename)
        await store.materialize(value)
        assert await store.read(value.binding) == value.data

    asyncio.run(run())
