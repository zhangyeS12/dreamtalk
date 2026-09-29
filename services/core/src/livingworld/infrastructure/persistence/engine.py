"""Central SQLite AsyncEngine, session factory, and database bootstrap."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import URL, Connection
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from livingworld.application import ports
from livingworld.application.content import ContentRepository
from livingworld.application.content_packages import ContentAssetStore, PackageRepository
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

    def llm_usage_ledger(self, *, catalog=None):
        """Operational accounting capability, isolated from world/content writes."""
        from livingworld.infrastructure.persistence.llm_repository import SqlAlchemyUsageLedger

        return SqlAlchemyUsageLedger(self._sessions, catalog=catalog)

    def llm_budget_guard(self, *, bounder, diagnostics, catalog=None, envelopes=()):
        """Atomic budget/START capability; composition must inject trusted reference data."""
        from livingworld.infrastructure.persistence.llm_budget_repository import (
            SqlAlchemyBudgetGuard,
        )

        return SqlAlchemyBudgetGuard(
            self._sessions,
            bounder=bounder,
            diagnostics=diagnostics,
            catalog=catalog,
            envelopes=envelopes,
        )

    def package_repository(self) -> PackageRepository:
        """Native authored snapshot acceptance; no runtime command capability."""
        from livingworld.infrastructure.persistence.package_repository import (
            SqlAlchemyPackageRepository,
        )

        return SqlAlchemyPackageRepository(self._sessions)

    def content_asset_store(self) -> ContentAssetStore:
        from livingworld.infrastructure.packages.asset_store import FileContentAssetStore

        return FileContentAssetStore(self.data_dir)

    def unit_of_work(self) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(self._sessions)

    def simulation_scheduler_store(self, registry):
        """Durable scheduler capability, isolated from canonical WorldEvent append."""
        from livingworld.infrastructure.persistence.scheduler import (
            SqlAlchemySimulationSchedulerStore,
        )

        return SqlAlchemySimulationSchedulerStore(self._sessions, registry)

    def world_clock_store(self):
        """Durable logical/UTC clock anchors; process monotonic values never persist."""
        from livingworld.infrastructure.persistence.world_clock import (
            SqlAlchemyWorldClockStore,
        )

        return SqlAlchemyWorldClockStore(self._sessions)

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

    def character_memory_reader(self, character_id: CharacterId) -> ports.CharacterMemoryReader:
        """Bind private memory access to one verified Character principal."""
        from livingworld.infrastructure.persistence.memory_repository import (
            SqlAlchemyCharacterMemoryReader,
        )

        return SqlAlchemyCharacterMemoryReader(self._sessions, character_id)

    def character_observed_event_reader(self, character_id: CharacterId):
        """Bind event-time access to the verified speaker; no global truth reader."""
        from livingworld.infrastructure.persistence.observed_events import (
            SqlAlchemyCharacterObservedEventReader,
        )

        return SqlAlchemyCharacterObservedEventReader(self._sessions, character_id)

    def developer_inspector_store(self):
        """Developer-only read projection; it has no mutation capability."""
        from livingworld.infrastructure.persistence.developer_inspector import (
            SqlAlchemyDeveloperInspectorStore,
        )

        return SqlAlchemyDeveloperInspectorStore(self._sessions)

    def world_directory(self):
        """Read-only catalog for the ordinary local-user surface."""
        from livingworld.infrastructure.persistence.world_directory import (
            SqlAlchemyWorldDirectory,
        )

        return SqlAlchemyWorldDirectory(self._sessions)

    def player_event_feed_store(self):
        from livingworld.infrastructure.persistence.player_event_feed import (
            SqlAlchemyPlayerEventFeedStore,
        )

        return SqlAlchemyPlayerEventFeedStore(self._sessions)

    def conversation_memory_store(self):
        from livingworld.infrastructure.persistence.conversation_memory import (
            SqlAlchemyConversationMemoryStore,
        )

        return SqlAlchemyConversationMemoryStore(self._sessions)

    def content_builder_store(self):
        from livingworld.infrastructure.persistence.content_builder import SqlAlchemyBuilderStore

        return SqlAlchemyBuilderStore(self._sessions)

    def world_content_service(self):
        from livingworld.application.world_content import WorldContentService
        from livingworld.infrastructure.clock import SystemWallClock
        from livingworld.infrastructure.imports.character_cards import CharacterCardImporter
        from livingworld.infrastructure.imports.lorebooks import LorebookImporter
        from livingworld.infrastructure.persistence.world_content import SqlAlchemyWorldContentStore

        lorebook = LorebookImporter()
        return WorldContentService(
            SqlAlchemyWorldContentStore(self._sessions),
            CharacterCardImporter(),
            lorebook,
            lorebook.normalize_embedded,
            SystemWallClock(),
        )

    def chat_conversation_store(self):
        from livingworld.infrastructure.persistence.chat_conversations import (
            SqlAlchemyChatConversationStore,
        )

        return SqlAlchemyChatConversationStore(self._sessions)

    def chat_message_store(self):
        from livingworld.infrastructure.persistence.chat_messages import SqlAlchemyChatMessageStore

        return SqlAlchemyChatMessageStore(self._sessions)

    def local_profile_store(self):
        from livingworld.infrastructure.persistence.local_profile import SqlAlchemyLocalProfileStore

        return SqlAlchemyLocalProfileStore(self._sessions)

    async def close(self) -> None:
        await self.engine.dispose()
