"""CAS-protected styles; snapshot helpers also run within background delivery transactions."""

from sqlalchemy import update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from livingworld.application.errors import EntityNotFoundError
from livingworld.application.world_style import WorldStyle
from livingworld.domain.errors import ConcurrencyConflictError
from livingworld.domain.identifiers import WorldId
from livingworld.infrastructure.persistence.models import WorldRecord, WorldStyleRecord


async def style_snapshot(session: AsyncSession, world_id) -> dict:
    row = await session.get(WorldStyleRecord, world_id)
    # Preserve the exact shape of legacy snapshots while no style has been saved.
    return {"world_style": row.instructions, "world_style_revision": row.revision} if row else {}


async def style_is_current(session: AsyncSession, world_id, snapshot: dict) -> bool:
    current = await style_snapshot(session, world_id)
    return current.get("world_style_revision", 0) == snapshot.get("world_style_revision", 0)


class SqlAlchemyWorldStyleStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def _check_world(self, session: AsyncSession, world: WorldId) -> None:
        if await session.get(WorldRecord, world.value) is None:
            raise EntityNotFoundError("world_not_found")

    async def load(self, world: WorldId) -> WorldStyle:
        async with self.sessions() as session:
            await self._check_world(session, world)
            row = await session.get(WorldStyleRecord, world.value)
            return WorldStyle(row.instructions, row.revision) if row else WorldStyle()

    async def save(self, world: WorldId, style: WorldStyle) -> WorldStyle:
        async with self.sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            await self._check_world(session, world)
            values = {"instructions": style.instructions, "revision": style.revision + 1}
            if style.revision == 0:
                result = await session.execute(
                    sqlite_insert(WorldStyleRecord)
                    .values(world_id=world.value, **values)
                    .on_conflict_do_nothing(index_elements=[WorldStyleRecord.world_id])
                    .returning(WorldStyleRecord.revision)
                )
            else:
                result = await session.execute(
                    update(WorldStyleRecord)
                    .where(
                        WorldStyleRecord.world_id == world.value,
                        WorldStyleRecord.revision == style.revision,
                    )
                    .values(**values)
                    .returning(WorldStyleRecord.revision)
                )
            if result.scalar_one_or_none() != style.revision + 1:
                raise ConcurrencyConflictError("world_style_conflict")
        return WorldStyle(style.instructions, style.revision + 1)
