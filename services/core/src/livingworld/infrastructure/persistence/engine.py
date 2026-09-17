"""Central SQLite AsyncEngine, session factory, and database bootstrap."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from livingworld.infrastructure.persistence.migration import upgrade
from livingworld.infrastructure.persistence.store import PersistenceStore


def _source_root() -> Path:
    package_root = Path(__file__).resolve().parents[2]
    for parent in package_root.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return package_root.parent


def _validate_data_dir(data_dir: Path) -> Path:
    if not data_dir.is_absolute():
        raise ValueError("data_dir_must_be_absolute")
    resolved = data_dir.resolve()
    source = _source_root().resolve()
    if resolved == source or source in resolved.parents:
        raise ValueError("data_dir_must_not_be_inside_source_tree")
    return resolved


class Database:
    """Own one engine and session factory for a Core process."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = _validate_data_dir(data_dir)
        self.path = self.data_dir / "runtime.sqlite3"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        url = URL.create("sqlite+aiosqlite", database=str(self.path))
        self.engine: AsyncEngine = create_async_engine(url, hide_parameters=True)

        @event.listens_for(self.engine.sync_engine, "connect")
        def configure_sqlite(dbapi_connection: object, _record: object) -> None:
            dbapi_connection.isolation_level = None  # type: ignore[attr-defined]
            cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
            cursor.execute("PRAGMA busy_timeout = 5000")
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.execute("PRAGMA recursive_triggers = ON")
            cursor.execute("PRAGMA journal_mode = WAL")
            mode = cursor.fetchone()[0]
            cursor.close()
            if str(mode).lower() != "wal":
                raise RuntimeError("wal_unavailable")

        @event.listens_for(self.engine.sync_engine, "begin")
        def begin_transaction(connection: object) -> None:
            connection.exec_driver_sql("BEGIN")  # type: ignore[attr-defined]

        self._sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def initialize(self) -> None:
        async with self.engine.begin() as connection:
            await connection.exec_driver_sql(
                "CREATE VIRTUAL TABLE IF NOT EXISTS temp.fts5_probe USING fts5(value)"
            )
            await connection.run_sync(upgrade)

    def store(self) -> PersistenceStore:
        return PersistenceStore(self._sessions)

    async def close(self) -> None:
        await self.engine.dispose()
