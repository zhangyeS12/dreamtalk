"""Concurrent callers use separate real sessions, gated before transaction entry."""

import asyncio

from livingworld.application.command_handler import CommandHandler
from livingworld.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork


async def race_commands(environment, *commands):
    barrier = asyncio.Barrier(len(commands))
    sessions = []

    class GatedUnitOfWork(SqlAlchemyUnitOfWork):
        async def __aenter__(self):
            await barrier.wait()
            unit = await super().__aenter__()
            sessions.append(self._session)
            return unit

    def caller(command):
        first = True

        def factory():
            nonlocal first
            if first:
                first = False
                return GatedUnitOfWork(environment.database._sessions)
            # Collision resolution, if needed, gets one fresh, ungated transaction.
            return environment.database.unit_of_work()

        return CommandHandler(factory, environment.clock).execute(command)

    results = await asyncio.wait_for(
        asyncio.gather(*(caller(command) for command in commands), return_exceptions=True),
        timeout=15,
    )
    assert len(sessions) == len(commands)
    assert len({id(session) for session in sessions}) == len(commands)
    return results
