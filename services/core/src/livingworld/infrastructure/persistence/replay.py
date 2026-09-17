"""SQLite adapter for ordered reads and atomic world-local projection replacement."""

from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from livingworld.application.errors import ReplayError
from livingworld.application.ledger import CanonicalEvent
from livingworld.application.projections import ProjectionSnapshot
from livingworld.domain.identifiers import WorldId
from livingworld.domain.values import require_type
from livingworld.infrastructure.persistence.errors import PersistenceDataError
from livingworld.infrastructure.persistence.mapping import to_domain, to_record
from livingworld.infrastructure.persistence.models import (
    Base,
    CharacterRecord,
    CharacterStateRecord,
    KnowledgeAssertionRecord,
    LocationRecord,
    ObservationRecord,
    PlayerPresenceRecord,
    PlayerRecord,
    RelationshipRecord,
    WorldClockRecord,
    WorldEventRecord,
    WorldRecord,
)


async def _read(session: AsyncSession, world_id: WorldId) -> tuple[CanonicalEvent, ...]:
    try:
        records = (
            await session.scalars(
                select(WorldEventRecord)
                .where(WorldEventRecord.world_id == world_id.value)
                .order_by(WorldEventRecord.ledger_position)
            )
        ).all()
        return tuple(
            CanonicalEvent(to_domain(record), record.ledger_position) for record in records
        )
    except (PersistenceDataError, ValueError, TypeError):
        raise ReplayError("Invalid canonical ledger record") from None


class CanonicalEventReader:
    """Internal capability; never supplied to principal knowledge contexts."""

    def __init__(self, sessions: async_sessionmaker, world_id: WorldId):
        require_type(world_id, WorldId, "world_id")
        self._sessions, self._world_id = sessions, world_id

    async def read(self) -> tuple[CanonicalEvent, ...]:
        async with self._sessions() as session:
            return await _read(session, self._world_id)


class _TransactionLedgerReader:
    def __init__(self, session: AsyncSession, world_id: WorldId):
        self._session, self._world_id = session, world_id

    async def read(self) -> tuple[CanonicalEvent, ...]:
        return await _read(self._session, self._world_id)


class SqlAlchemyProjectionRebuildUnitOfWork:
    """Keep canonical anchors; all replayable writes share the ledger read transaction."""

    def __init__(self, sessions: async_sessionmaker, world_id: WorldId):
        require_type(world_id, WorldId, "world_id")
        self._sessions, self._world_id = sessions, world_id

    async def __aenter__(self):
        self._session = self._sessions()
        await self._session.begin()
        # Temporary missing parents are restored before validation/commit. FK checking
        # stays enabled; append-only ledger triggers are never removed or disabled.
        await self._session.execute(text("PRAGMA defer_foreign_keys = ON"))
        self.ledger = _TransactionLedgerReader(self._session, self._world_id)
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        try:
            await self._session.rollback()
        finally:
            await self._session.close()
        if exc_type is not None and issubclass(exc_type, IntegrityError):
            raise ReplayError("Projection constraint validation failed") from None

    async def clear(self) -> None:
        for record in (
            ObservationRecord,
            KnowledgeAssertionRecord,
            RelationshipRecord,
            CharacterStateRecord,
            PlayerPresenceRecord,
            CharacterRecord,
            PlayerRecord,
            LocationRecord,
            WorldClockRecord,
        ):
            await self._session.execute(
                delete(record).where(record.world_id == self._world_id.value)
            )

    async def replace(self, snapshot: ProjectionSnapshot) -> None:
        if snapshot.world.world_id != self._world_id:
            raise ReplayError("Projection snapshot belongs to another world")
        # World identity remains as the FK anchor of immutable events/receipts/cursor.
        # Its complete replayable state is overwritten from the fold, not read here.
        result = await self._session.execute(
            update(WorldRecord)
            .where(WorldRecord.world_id == self._world_id.value)
            .values(name=snapshot.world.name, revision=snapshot.world.revision.value)
        )
        if result.rowcount != 1:
            raise ReplayError("Canonical world anchor is missing")
        self._session.add(to_record(snapshot.world.clock))
        await self._session.flush()
        for group in (
            snapshot.locations,
            snapshot.players,
            snapshot.characters,
            snapshot.presences,
            snapshot.character_states,
            snapshot.relationships,
            snapshot.knowledge,
            snapshot.observations,
        ):
            for entity in group:
                self._session.add(to_record(entity))
            await self._session.flush()

    async def validate(self) -> None:
        await self._session.flush()
        # Check this world's rebuilt constraints, including preserved receipt/source
        # and connection references. A different world's rows are never rewritten.
        violations = (await self._session.execute(text("PRAGMA foreign_key_check"))).all()
        for table_name, rowid, _parent, _fk in violations:
            table = Base.metadata.tables.get(table_name)
            if table is None or "world_id" not in table.c:
                raise ReplayError("Database foreign key validation failed")
            affected_world = await self._session.scalar(
                select(table.c.world_id).where(text("rowid = :row_id")).params(row_id=rowid)
            )
            if affected_world == self._world_id.value:
                raise ReplayError("Rebuilt world foreign key validation failed")

    async def commit(self) -> None:
        await self._session.commit()
