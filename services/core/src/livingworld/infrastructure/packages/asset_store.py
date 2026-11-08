"""Immutable hash-keyed blobs in app data. No arbitrary resource-path resolution."""

import asyncio
import os
import tempfile
from hashlib import sha256
from pathlib import Path

from livingworld.application.content_packages import AssetBlobBinding, PackagedBlob, PackageError
from livingworld.domain.content.models import require_hash
from livingworld.infrastructure.persistence.engine import _validate_data_dir


def _regular_path(path: Path) -> None:
    for part in (path, *path.parents):
        if part.is_symlink() or part.is_junction():
            raise PackageError("asset_store_link_not_allowed")


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
            try:
                # Exclusive link publishes a completed regular file; never replaces a blob.
                # Both locations are under the same store/filesystem. Staging link is removed.
                os.link(staged, target)
            except FileExistsError:
                self._read(blob.binding)
            self._read(blob.binding)
        finally:
            if staged is not None:
                staged.unlink(missing_ok=True)

    async def materialize(self, blob: PackagedBlob) -> None:
        await asyncio.to_thread(self._materialize, blob)
