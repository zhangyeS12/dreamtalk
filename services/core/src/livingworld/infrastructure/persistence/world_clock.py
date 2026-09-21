"""Crash-safe WorldClock anchor persistence with revision checking."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from livingworld.application.errors import EntityNotFoundError
from livingworld.domain.errors import ConcurrencyConflictError, DomainInvariantError
from livingworld.domain.identifiers import WorldId
from livingworld.domain.values import Revision
from livingworld.domain.world import WorldClock
from livingworld.infrastructure.persistence.mapping import to_domain
from livingworld.infrastructure.persistence.models import WorldClockRecord


async def _begin_write(session: AsyncSession) -> None:
    await session.begin()
    await session.connection(execution_options={"livingworld_write_intent": True})


class SqlAlchemyWorldClockStore:
    """The only persistence adapter allowed to replace durable clock anchors."""

    def __init__(self, sessions: async_sessionmaker) -> None:
        self._sessions = sessions

    async def list(self) -> tuple[WorldClock, ...]:
        async with self._sessions() as session:
            records = (
                await session.scalars(select(WorldClockRecord).order_by(WorldClockRecord.world_id))
            ).all()
            return tuple(to_domain(record) for record in records)

    async def get(self, world_id: WorldId) -> WorldClock | None:
        async with self._sessions() as session:
            record = await session.get(WorldClockRecord, world_id.value)
            return to_domain(record) if record is not None else None

    async def replace(self, clock: WorldClock, expected_revision: Revision) -> WorldClock:
        if clock.revision != Revision(expected_revision.value + 1):
            raise DomainInvariantError("WorldClock replacement must advance exactly one revision")
        async with self._sessions() as session:
            await _begin_write(session)
            try:
                record = await session.get(WorldClockRecord, clock.world_id.value)
                if record is None:
                    raise EntityNotFoundError("WorldClock does not exist")
                if record.revision != expected_revision.value:
                    raise ConcurrencyConflictError(
                        "WorldClock does not match expected revision",
                        resource_kind="WorldClock",
                        resource_identity=clock.world_id,
                        expected_revision=expected_revision,
                        actual_revision=Revision(record.revision),
                    )
                record.logical_time = clock.logical_time
                record.observed_wall_time_utc = clock.observed_wall_time_utc
                record.time_scale = clock.time_scale
                record.state = clock.state.value
                record.revision = clock.revision.value
                await session.commit()
                return clock
            except BaseException:
                await session.rollback()
                raise
