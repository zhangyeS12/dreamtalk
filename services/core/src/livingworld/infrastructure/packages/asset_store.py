"""Immutable hash-keyed blobs in app data. No arbitrary resource-path resolution."""

import asyncio
import os
import sys
import tempfile
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path

from livingworld.application.content_packages import AssetBlobBinding, PackagedBlob, PackageError
from livingworld.domain.content.models import require_hash
from livingworld.infrastructure.persistence.engine import _validate_data_dir


def _regular_path(path: Path) -> None:
    for part in (path, *path.parents):
        if part.is_symlink() or part.is_junction():
            raise PackageError("asset_store_link_not_allowed")


@contextmanager
def _android_publication_lock(path: Path):
    import fcntl

    _regular_path(path)
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)  # Closing releases the advisory file lock.


class FileContentAssetStore:
    def __init__(self, data_dir: Path) -> None:
        _regular_path(data_dir)
        self._root = _validate_data_dir(data_dir) / "content-assets"
        _regular_path(self._root)

    def _path(self, digest: str) -> Path:
        require_hash(digest)
        path = self._root / "sha256" / digest[:2] / digest
        _regular_path(path)
        return path

    def _read(self, binding: AssetBlobBinding) -> bytes:
        path = self._path(binding.digest)
        try:
            with path.open("rb") as source:
                data = source.read(binding.size + 1)
        except FileNotFoundError:
            raise PackageError("asset_blob_missing") from None
        if len(data) != binding.size or sha256(data).hexdigest() != binding.digest:
            raise PackageError("stored_asset_integrity_mismatch")
        return data

    async def read(self, binding: AssetBlobBinding) -> bytes:
        return await asyncio.to_thread(self._read, binding)

    async def remove_unreferenced(self, digest: str) -> None:
        # The caller proves this immutable hash is no longer referenced in its DB transaction.
        await asyncio.to_thread(self._path(digest).unlink, missing_ok=True)

    def _publish(self, staged: Path, target: Path, binding: AssetBlobBinding) -> None:
        if not hasattr(sys, "getandroidapilevel"):
            try:
                os.link(staged, target)
            except FileExistsError:
                self._read(binding)
            return

        # Android SELinux denies hard links inside app data. Serialize every
        # Android publisher across threads/processes, then rename the completed
        # sibling file. Readers see only complete blobs; existing bytes stay immutable.
        with _android_publication_lock(self._root / ".publish.lock"):
            _regular_path(target)
            if target.exists():
                self._read(binding)
            else:
                os.rename(staged, target)

    def _materialize(self, blob: PackagedBlob) -> None:
        target = self._path(blob.binding.digest)
        if target.exists():
            self._read(blob.binding)
            return
        staging = self._root / "staging"
        _regular_path(staging)
        staging.mkdir(parents=True, exist_ok=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        staged = None
        try:
            with tempfile.NamedTemporaryFile(dir=staging, delete=False) as file:
                staged = Path(file.name)
                file.write(blob.data)
                file.flush()
                os.fsync(file.fileno())
            _regular_path(target)
            self._publish(staged, target, blob.binding)
            self._read(blob.binding)
        finally:
            if staged is not None:
                staged.unlink(missing_ok=True)

    async def materialize(self, blob: PackagedBlob) -> None:
        await asyncio.to_thread(self._materialize, blob)
