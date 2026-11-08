"""Scope-isolated local profile persistence with optimistic edit protection."""

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from livingworld.application.errors import EntityNotFoundError
from livingworld.application.local_profile import LocalProfile
from livingworld.domain.errors import ConcurrencyConflictError
from livingworld.domain.identifiers import WorldId
from livingworld.domain.values import Revision
from livingworld.infrastructure.persistence.models import (
    LocalUserProfileRecord,
    LocalWorldProfileRecord,
    WorldRecord,
)


class SqlAlchemyLocalProfileStore:
    def __init__(self, sessions) -> None:
        self._sessions = sessions

    async def _check_world(self, session, world_id: WorldId | None) -> None:
        if world_id is not None:
            exists = await session.scalar(
                select(WorldRecord.world_id).where(WorldRecord.world_id == world_id.value)
            )
            if exists is None:
                raise EntityNotFoundError("world_not_found")

    async def load(self, world_id: WorldId | None = None) -> LocalProfile:
        model = LocalWorldProfileRecord if world_id is not None else LocalUserProfileRecord
        identity = world_id.value if world_id is not None else 1
        async with self._sessions() as session:
            await self._check_world(session, world_id)
            row = await session.get(model, identity)
            if row is None:
                return LocalProfile()
            return LocalProfile(row.name, row.description, Revision(row.revision))

    async def save(self, profile: LocalProfile, world_id: WorldId | None = None) -> LocalProfile:
        model = LocalWorldProfileRecord if world_id is not None else LocalUserProfileRecord
        key = model.world_id if world_id is not None else model.singleton
        identity = world_id.value if world_id is not None else 1
        values = {
            "name": profile.name,
            "description": profile.description,
            "revision": profile.revision.value + 1,
        }
        async with self._sessions() as session, session.begin():
            await self._check_world(session, world_id)
            if profile.revision.value == 0:
                result = await session.execute(
                    sqlite_insert(model)
                    .values({key.key: identity, **values})
                    .on_conflict_do_nothing(index_elements=[key])
                )
            else:
                result = await session.execute(
                    update(model)
                    .where(key == identity, model.revision == profile.revision.value)
                    .values(**values)
                )
            if result.rowcount != 1:
                raise ConcurrencyConflictError("profile_edit_conflict")
        return LocalProfile(profile.name, profile.description, Revision(values["revision"]))
