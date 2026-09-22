"""Read-only world list for the local product surface."""

from sqlalchemy import select

from livingworld.application.world_settings import WorldListing
from livingworld.domain.identifiers import WorldId
from livingworld.infrastructure.persistence.models import WorldRecord


class SqlAlchemyWorldDirectory:
    def __init__(self, sessions) -> None:
        self._sessions = sessions

    async def list_worlds(self) -> tuple[WorldListing, ...]:
        async with self._sessions() as session:
            rows = (await session.scalars(select(WorldRecord).order_by(WorldRecord.name))).all()
            return tuple(WorldListing(WorldId(row.world_id), row.name) for row in rows)
