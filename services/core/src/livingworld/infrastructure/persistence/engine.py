"""Central SQLite AsyncEngine, session factory, and database bootstrap."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import URL, Connection
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from livingworld.application import ports
from livingworld.application.content import ContentRepository
from livingworld.domain.identifiers import CharacterId, PlayerId, WorldId
from livingworld.infrastructure.persistence import knowledge_readers, replay
from livingworld.infrastructure.persistence.content_repository import SqlAlchemyContentRepository
from livingworld.infrastructure.persistence.migration import upgrade
from livingworld.infrastructure.persistence.store import PersistenceStore
from livingworld.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork


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
        def begin_transaction(connection: Connection) -> None:
            statement = (
                "BEGIN IMMEDIATE"
                if connection.get_execution_options().get("livingworld_write_intent")
                else "BEGIN"
            )
            connection.exec_driver_sql(statement)

        self._sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def initialize(self) -> None:
        async with self.engine.begin() as connection:
            await connection.exec_driver_sql(
                "CREATE VIRTUAL TABLE IF NOT EXISTS temp.fts5_probe USING fts5(value)"
            )
            await connection.run_sync(upgrade)

    def store(self) -> PersistenceStore:
        return PersistenceStore(self._sessions)

    def content_repository(self) -> ContentRepository:
        """Content library capability; grants no canonical runtime write access."""
        return SqlAlchemyContentRepository(self._sessions)

    def unit_of_work(self) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(self._sessions)

    def canonical_event_reader(self, world_id: WorldId) -> ports.CanonicalEventReader:
        return replay.CanonicalEventReader(self._sessions, world_id)

    def projection_rebuild_unit_of_work(
        self, world_id: WorldId
    ) -> ports.ProjectionRebuildUnitOfWork:
        return replay.SqlAlchemyProjectionRebuildUnitOfWork(self._sessions, world_id)

    def world_truth_reader(self, world_id: WorldId) -> ports.WorldTruthReader:
        """Trusted composition only; never supplied to principal contexts."""
        return knowledge_readers.WorldTruthReader(self._sessions, world_id)

    def character_knowledge_reader(
        self, character_id: CharacterId
    ) -> ports.CharacterKnowledgeReader:
        """Bind a verified principal at the trusted composition boundary."""
        return knowledge_readers.CharacterKnowledgeReader(self._sessions, character_id)

    def player_knowledge_reader(self, player_id: PlayerId) -> ports.PlayerKnowledgeReader:
        return knowledge_readers.PlayerKnowledgeReader(self._sessions, player_id)

    async def close(self) -> None:
        await self.engine.dispose()
