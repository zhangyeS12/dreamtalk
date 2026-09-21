"""Owner-scoped EpisodicMemory persistence and evidence authorization."""

from sqlite3 import SQLITE_CONSTRAINT_PRIMARYKEY, SQLITE_CONSTRAINT_UNIQUE

from sqlalchemy import and_, asc, desc, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from livingworld.application.errors import EntityAlreadyExistsError
from livingworld.domain.errors import DomainInvariantError
from livingworld.domain.identifiers import CharacterId, MemoryId, ObservationId, WorldId
from livingworld.domain.knowledge import Observation
from livingworld.domain.memory import (
    EpisodicMemory,
    MemoryContentFormat,
    MemoryCursor,
    MemoryEvidence,
    MemoryKind,
    MemoryPage,
    MemoryProvenanceKind,
    MemorySalience,
)
from livingworld.domain.values import WorldTime, require_type, same_world
from livingworld.infrastructure.persistence.mapping import to_domain
from livingworld.infrastructure.persistence.models import (
    CharacterMemoryRecord,
    EpisodicMemoryObservationSourceRecord,
    ObservationRecord,
)

MAX_MEMORY_PAGE_SIZE = 100


def _to_memory(record: CharacterMemoryRecord) -> EpisodicMemory:
    world = WorldId(record.world_id)
    return EpisodicMemory(
        MemoryId(world, record.memory_id),
        world,
        CharacterId(world, record.owner_character_id),
        record.content,
        record.experienced_from,
        record.experienced_to,
        record.formed_at,
        record.created_at_utc,
        tuple(ObservationId(world, source.observation_id) for source in record.sources),
        MemorySalience(record.salience) if record.salience is not None else None,
        MemoryKind(record.kind),
        record.kind_version,
        MemoryContentFormat(record.content_format),
        record.content_version,
        MemoryProvenanceKind(record.provenance_kind),
        record.provenance_version,
    )


class SqlAlchemyMemoryMutationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def authorized_observations(
        self, owner_character_id: CharacterId, observation_ids: tuple[ObservationId, ...]
    ) -> tuple[Observation, ...]:
        if not observation_ids:
            return ()
        for identity in observation_ids:
            require_type(identity, ObservationId, "observation_id")
            same_world(owner_character_id.world_id, identity)
        records = (
            await self._session.scalars(
                select(ObservationRecord).where(
                    ObservationRecord.world_id == owner_character_id.world_id.value,
                    ObservationRecord.principal_kind == "character",
                    ObservationRecord.principal_id == owner_character_id.value,
                    ObservationRecord.principal_character_id == owner_character_id.value,
                    ObservationRecord.principal_player_id.is_(None),
                    ObservationRecord.observation_id.in_(
                        identity.value for identity in observation_ids
                    ),
                )
            )
        ).all()
        return tuple(to_domain(record) for record in records)

    async def add(self, memory: EpisodicMemory) -> None:
        record = CharacterMemoryRecord(
            world_id=memory.world_id.value,
            memory_id=memory.memory_id.value,
            owner_character_id=memory.owner_character_id.value,
            kind=memory.kind.value,
            kind_version=memory.kind_version,
            content=memory.content,
            content_format=memory.content_format.value,
            content_version=memory.content_version,
            experienced_from=memory.experienced_from,
            experienced_to=memory.experienced_to,
            formed_at=memory.formed_at,
            created_at_utc=memory.created_at_utc,
            salience=memory.salience.value if memory.salience is not None else None,
            provenance_kind=memory.provenance_kind.value,
            provenance_version=memory.provenance_version,
        )
        self._session.add(record)
        try:
            await self._session.flush()
        except IntegrityError as error:
            if getattr(error.orig, "sqlite_errorcode", None) in (
                SQLITE_CONSTRAINT_PRIMARYKEY,
                SQLITE_CONSTRAINT_UNIQUE,
            ):
                raise EntityAlreadyExistsError("EpisodicMemory already exists") from None
            raise
        await self._insert_sources(memory)

    async def _insert_sources(self, memory: EpisodicMemory) -> None:
        self._session.add_all(
            [
                EpisodicMemoryObservationSourceRecord(
                    world_id=memory.world_id.value,
                    memory_id=memory.memory_id.value,
                    position=position,
                    observation_id=observation_id.value,
                )
                for position, observation_id in enumerate(memory.source_observation_ids)
            ]
        )
        await self._session.flush()


class SqlAlchemyCharacterMemoryReader:
    """Read-only capability permanently bound to one Character principal."""

    def __init__(self, sessions: async_sessionmaker, owner_character_id: CharacterId) -> None:
        require_type(owner_character_id, CharacterId, "owner_character_id")
        self._sessions = sessions
        self._owner = owner_character_id

    def _owned(self):
        return (
            CharacterMemoryRecord.world_id == self._owner.world_id.value,
            CharacterMemoryRecord.owner_character_id == self._owner.value,
        )

    async def get(self, memory_id: MemoryId) -> EpisodicMemory | None:
        require_type(memory_id, MemoryId, "memory_id")
        same_world(self._owner.world_id, memory_id)
        async with self._sessions() as session:
            record = (
                await session.scalars(
                    select(CharacterMemoryRecord)
                    .options(selectinload(CharacterMemoryRecord.sources))
                    .where(*self._owned(), CharacterMemoryRecord.memory_id == memory_id.value)
                )
            ).one_or_none()
            return _to_memory(record) if record is not None else None

    async def evidence(self, memory_id: MemoryId) -> tuple[MemoryEvidence, ...]:
        require_type(memory_id, MemoryId, "memory_id")
        same_world(self._owner.world_id, memory_id)
        async with self._sessions() as session:
            rows = (
                await session.execute(
                    select(
                        EpisodicMemoryObservationSourceRecord.observation_id,
                        ObservationRecord.observed_at,
                        EpisodicMemoryObservationSourceRecord.position,
                    )
                    .join(
                        CharacterMemoryRecord,
                        and_(
                            CharacterMemoryRecord.world_id
                            == EpisodicMemoryObservationSourceRecord.world_id,
                            CharacterMemoryRecord.memory_id
                            == EpisodicMemoryObservationSourceRecord.memory_id,
                        ),
                    )
                    .join(
                        ObservationRecord,
                        and_(
                            ObservationRecord.world_id
                            == EpisodicMemoryObservationSourceRecord.world_id,
                            ObservationRecord.observation_id
                            == EpisodicMemoryObservationSourceRecord.observation_id,
                        ),
                    )
                    .where(
                        *self._owned(),
                        CharacterMemoryRecord.memory_id == memory_id.value,
                    )
                    .order_by(EpisodicMemoryObservationSourceRecord.position)
                )
            ).all()
            return tuple(
                MemoryEvidence(
                    ObservationId(self._owner.world_id, observation_id),
                    observed_at,
                    position,
                )
                for observation_id, observed_at, position in rows
            )

    async def list(
        self,
        *,
        experienced_from: WorldTime | None = None,
        experienced_to: WorldTime | None = None,
        limit: int = 50,
        after: MemoryCursor | None = None,
    ) -> MemoryPage:
        if type(limit) is not int or not 1 <= limit <= MAX_MEMORY_PAGE_SIZE:
            raise DomainInvariantError("Memory page limit must be from 1 through 100")
        if experienced_from is not None:
            require_type(experienced_from, WorldTime, "experienced_from")
        if experienced_to is not None:
            require_type(experienced_to, WorldTime, "experienced_to")
        if (
            experienced_from is not None
            and experienced_to is not None
            and experienced_to < experienced_from
        ):
            raise DomainInvariantError("Memory list time bounds are reversed")
        if after is not None:
            require_type(after, MemoryCursor, "after")
            same_world(self._owner.world_id, after.memory_id)

        statement = (
            select(CharacterMemoryRecord)
            .options(selectinload(CharacterMemoryRecord.sources))
            .where(*self._owned())
        )
        if experienced_from is not None:
            statement = statement.where(CharacterMemoryRecord.experienced_to >= experienced_from)
        if experienced_to is not None:
            statement = statement.where(CharacterMemoryRecord.experienced_from <= experienced_to)
        if after is not None:
            statement = statement.where(
                or_(
                    CharacterMemoryRecord.experienced_to < after.experienced_to,
                    and_(
                        CharacterMemoryRecord.experienced_to == after.experienced_to,
                        CharacterMemoryRecord.formed_at < after.formed_at,
                    ),
                    and_(
                        CharacterMemoryRecord.experienced_to == after.experienced_to,
                        CharacterMemoryRecord.formed_at == after.formed_at,
                        CharacterMemoryRecord.memory_id > after.memory_id.value,
                    ),
                )
            )
        statement = statement.order_by(
            desc(CharacterMemoryRecord.experienced_to),
            desc(CharacterMemoryRecord.formed_at),
            asc(CharacterMemoryRecord.memory_id),
        ).limit(limit + 1)
        async with self._sessions() as session:
            records = (await session.scalars(statement)).all()
        has_more = len(records) > limit
        items = tuple(_to_memory(record) for record in records[:limit])
        next_cursor = None
        if has_more and items:
            last = items[-1]
            next_cursor = MemoryCursor(last.experienced_to, last.formed_at, last.memory_id)
        return MemoryPage(items, next_cursor)
