"""Test-only raw snapshot writer for C-003B mapping/constraint regressions.

Never imported by production. It deliberately bypasses commands to probe the DB.
"""

from livingworld.infrastructure.persistence.errors import PersistenceConflictError
from livingworld.infrastructure.persistence.mapping import to_record
from livingworld.infrastructure.persistence.store import PersistenceStore
from sqlalchemy.exc import IntegrityError


class SnapshotFixtureStore(PersistenceStore):
    async def add(self, entity):
        try:
            async with self._sessions.begin() as session:
                session.add(to_record(entity))
        except IntegrityError:
            raise PersistenceConflictError("persistence_insert_conflict") from None


def snapshot_store(database):
    return SnapshotFixtureStore(database._sessions)
