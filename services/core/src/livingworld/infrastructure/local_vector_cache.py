"""Rebuildable vector bytes only; DiskCache owns persistence and eviction."""

from pathlib import Path


class LocalVectorCache:
    def __init__(self, directory: Path | None):
        self.directory = directory
        self.cache = None
        self.failed = False

    def open(self):
        if self.directory is None or self.failed:
            return
        try:
            from diskcache import Cache, Disk
            from diskcache.core import MODE_RAW

            class RawVectorDisk(Disk):
                # No pickled objects or cache-provided file paths may be read.
                def fetch(self, mode, filename, value, read):
                    if mode != MODE_RAW or filename is not None or read:
                        raise ValueError("vector_cache_value_invalid")
                    return super().fetch(mode, filename, value, read)

                def get(self, key, raw):
                    if not raw:
                        raise ValueError("vector_cache_key_invalid")
                    return super().get(key, raw)

            class BoundedCache(Cache):
                # DiskCache 5.6.3 retries constructor SQL for up to 60 seconds.
                # A derived cache must instead respect SQLite's short busy timeout.
                @property
                def _sql_retry(self):
                    return self._sql

            if (
                self.directory.is_symlink()
                or self.directory.parent.is_symlink()
                or any(
                    (self.directory / name).is_symlink()
                    for name in ("cache.db", "cache.db-wal", "cache.db-shm")
                )
            ):
                raise ValueError("vector_cache_path_invalid")
            if self.cache is not None:
                return
            self.cache = BoundedCache(
                str(self.directory),
                disk=RawVectorDisk,
                timeout=0.05,
                size_limit=256 * 1024 * 1024,
                # A history scan must not write a transaction for every read.
                # The small in-memory cache supplies LRU; disk eviction follows writes.
                eviction_policy="least-recently-stored",
                disk_min_file_size=32768,
            )
        except Exception:
            self.failed = True
            self.close()

    def get(self, key: bytes) -> bytes | None:
        if self.cache is None or self.failed:
            return None
        try:
            value = self.cache.get(key, retry=False)
            return value if type(value) is bytes and len(value) == 2080 else None
        except Exception:
            self.failed = True
            self.close()
            return None

    def set(self, key: bytes, value: bytes):
        if self.cache is None or self.failed or len(key) != 32 or len(value) != 2080:
            return
        try:
            self.cache.set(key, value, retry=False)
        except Exception:
            self.failed = True
            self.close()

    def close(self):
        if self.cache is not None:
            try:
                self.cache.close()
            except Exception:
                pass
            finally:
                # The pinned library reopens its per-thread connection on demand.
                # Keep validated settings to avoid constructor writes every lookup.
                if self.failed:
                    self.cache = None

    def clear(self):
        self.open()
        if self.failed:
            raise RuntimeError("world_delete_cache_unavailable")
        if self.cache is not None:
            self.cache.clear(retry=False)
