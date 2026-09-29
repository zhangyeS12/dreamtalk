"""World-scoped creator directory; other runtime locations are never enumerated."""

from uuid import uuid5

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from livingworld.application.director import MAX_LOCATIONS
from livingworld.application.errors import EntityNotFoundError
from livingworld.application.world_locations import (
    LocalLocation,
    LocationCatalogError,
    location_name_key,
)
from livingworld.domain.identifiers import LocationId, WorldId
from livingworld.infrastructure.persistence.models import (
    LocalLocationCatalogRecord,
    LocationRecord,
    WorldRecord,
)


def _home_id(world_id: WorldId):
    return uuid5(world_id.value, "livingworld:local-home:v1")


class SqlAlchemyLocalLocationDirectory:
    def __init__(self, sessions) -> None:
        self._sessions = sessions

    async def list_locations(self, world_id: WorldId) -> tuple[LocalLocation, ...]:
        async with self._sessions() as session:
            if (
                await session.scalar(
                    select(WorldRecord.world_id).where(WorldRecord.world_id == world_id.value)
                )
                is None
            ):
                raise EntityNotFoundError("World does not exist")
            # Authorize using creator catalog BEFORE projecting any location name.
            statement = (
                select(LocationRecord.location_id, LocationRecord.name)
                .join(
                    LocalLocationCatalogRecord,
                    (LocalLocationCatalogRecord.world_id == LocationRecord.world_id)
                    & (LocalLocationCatalogRecord.location_id == LocationRecord.location_id),
                )
                .where(LocalLocationCatalogRecord.world_id == world_id.value)
                .order_by(LocationRecord.name, LocationRecord.location_id)
                .limit(MAX_LOCATIONS + 1)
            )
            rows = (await session.execute(statement)).all()
            if len(rows) > MAX_LOCATIONS:
                raise LocationCatalogError("location_catalog_capacity")
            locations = [
                LocalLocation(LocationId(world_id, row.location_id), row.name) for row in rows
            ]
            home_name = await session.scalar(
                select(LocationRecord.name).where(
                    LocationRecord.world_id == world_id.value,
                    LocationRecord.location_id == _home_id(world_id),
                    LocationRecord.name == "家",
                )
            )
            if home_name is not None:
                locations.insert(
                    0, LocalLocation(LocationId(world_id, _home_id(world_id)), "家", True)
                )
            return tuple(locations)


class SqlAlchemyLocalLocationCatalog:
    def __init__(self, session) -> None:
        self._session = session

    async def check_new(self, world_id: WorldId, name: str) -> None:
        key = location_name_key(name)
        duplicate = await self._session.scalar(
            select(LocalLocationCatalogRecord.location_id).where(
                LocalLocationCatalogRecord.world_id == world_id.value,
                LocalLocationCatalogRecord.name_key == key,
            )
        )
        if duplicate is not None:
            raise LocationCatalogError("location_name_exists")
        # The Kernel has already reserved SQLite's writer. Count + create + receipt
        # therefore share one transaction, including a slot for future onboarding.
        count = await self._session.scalar(
            select(func.count())
            .select_from(LocationRecord)
            .where(LocationRecord.world_id == world_id.value)
        )
        home = await self._session.scalar(
            select(LocationRecord.location_id).where(
                LocationRecord.world_id == world_id.value,
                LocationRecord.location_id == _home_id(world_id),
            )
        )
        capacity = MAX_LOCATIONS if home is not None else MAX_LOCATIONS - 1
        if count is None or count >= capacity:
            raise LocationCatalogError("location_catalog_capacity")

    async def add(self, location_id: LocationId, name: str) -> None:
        self._session.add(
            LocalLocationCatalogRecord(
                world_id=location_id.world_id.value,
                location_id=location_id.value,
                name_key=location_name_key(name),
            )
        )
        try:
            await self._session.flush()
        except IntegrityError:
            raise LocationCatalogError("location_creation_conflict") from None
