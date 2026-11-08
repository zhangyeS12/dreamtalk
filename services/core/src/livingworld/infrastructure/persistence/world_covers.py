"""World-scoped presentation records and optimistic cover edits."""

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from livingworld.application.errors import EntityNotFoundError
from livingworld.domain.errors import ConcurrencyConflictError
from livingworld.infrastructure.persistence.models import WorldRecord
from livingworld.infrastructure.persistence.world_cover_models import (
    WorldCoverImageRecord,
    WorldCoverRecord,
)


class SqlAlchemyWorldCoverRepository:
    def __init__(self, sessions):
        self._sessions = sessions

    async def world_name(self, world):
        async with self._sessions() as session:
            name = await session.scalar(
                select(WorldRecord.name).where(WorldRecord.world_id == world.value)
            )
            if name is None:
                raise EntityNotFoundError("world_not_found")
            return name

    def _value(self, row):
        return {**row.payload, "world_id": str(row.world_id), "revision": row.revision}

    async def list_covers(self):
        async with self._sessions() as session:
            rows = await session.scalars(
                select(WorldCoverRecord).order_by(WorldCoverRecord.world_id)
            )
            return [self._value(row) for row in rows]

    async def load(self, world):
        async with self._sessions() as session:
            row = await session.get(WorldCoverRecord, world.value)
            return self._value(row) if row else None

    async def image(self, world, digest):
        async with self._sessions() as session:
            row = await session.get(WorldCoverImageRecord, (world.value, digest))
            if row is None:
                raise EntityNotFoundError("cover_image_not_found")
            return {
                "digest": row.digest,
                "size": row.size,
                "media_type": row.media_type,
                "width": row.width,
                "height": row.height,
            }

    async def add_image(self, world, image):
        async with self._sessions() as session, session.begin():
            await session.execute(
                sqlite_insert(WorldCoverImageRecord)
                .values(world_id=world.value, **image)
                .on_conflict_do_nothing()
            )

    async def save(self, world, value, revision):
        async with self._sessions() as session, session.begin():
            if revision == 0:
                result = await session.execute(
                    sqlite_insert(WorldCoverRecord)
                    .values(world_id=world.value, payload=value, revision=1)
                    .on_conflict_do_nothing()
                )
            else:
                result = await session.execute(
                    update(WorldCoverRecord)
                    .where(
                        WorldCoverRecord.world_id == world.value,
                        WorldCoverRecord.revision == revision,
                    )
                    .values(payload=value, revision=revision + 1)
                )
            if result.rowcount != 1:
                raise ConcurrencyConflictError("cover_edit_conflict")
        return {**value, "world_id": str(world.value), "revision": revision + 1}
