import asyncio
from uuid import uuid4

from alembic import command
from livingworld.application.command_handler import CommandHandler
from livingworld.application.commands import CreateWorld
from livingworld.application.simulation_clock import EffectiveWorldTimeSource, SystemMonotonicClock
from livingworld.domain.contracts import RequestId
from livingworld.domain.identifiers import WorldId
from livingworld.infrastructure.clock import SystemWallClock
from livingworld.infrastructure.persistence import Database
from livingworld.infrastructure.persistence.migration import (
    HEAD_REVISION,
    WORLD_CONTENT_REVISION,
    _alembic_config,
)
from livingworld.infrastructure.persistence.models import WorldRecord
from sqlalchemy import text


def test_existing_world_content_database_upgrades_without_recreating_world(tmp_path):
    async def run():
        db = Database(tmp_path)
        world = WorldId(uuid4())
        try:
            async with db.engine.begin() as connection:
                await connection.run_sync(
                    lambda sync: command.upgrade(_alembic_config(sync), WORLD_CONTENT_REVISION)
                )
            clock = SystemWallClock()
            handler = CommandHandler(
                db.unit_of_work,
                clock,
                world_time_source=EffectiveWorldTimeSource(clock, SystemMonotonicClock()),
            )
            await handler.execute(
                CreateWorld(request_id=RequestId(uuid4()), world_id=world, name="保留的世界")
            )
            await db.initialize()
            async with db._sessions() as session:
                assert (await session.get(WorldRecord, world.value)).name == "保留的世界"
                assert (
                    await session.scalar(text("SELECT version_num FROM alembic_version"))
                    == HEAD_REVISION
                )
            await db.initialize()
        finally:
            await db.close()

    asyncio.run(run())
