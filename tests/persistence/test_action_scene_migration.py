import asyncio
from uuid import uuid4

from alembic import command
from livingworld.application.command_handler import CommandHandler
from livingworld.application.commands import CreateLocation, CreatePlayer, CreateWorld
from livingworld.application.simulation_clock import EffectiveWorldTimeSource, SystemMonotonicClock
from livingworld.domain.contracts import RequestId
from livingworld.domain.identifiers import LocationId, PlayerId, WorldId
from livingworld.infrastructure.clock import SystemWallClock
from livingworld.infrastructure.persistence import Database
from livingworld.infrastructure.persistence.migration import (
    HEAD_REVISION,
    SIMULATION_REVISION,
    _alembic_config,
)
from sqlalchemy import text


def test_0012_upgrade_preserves_0011_state_and_adds_scene_perception_constraints(tmp_path):
    async def run():
        database = Database(tmp_path)
        try:
            async with database.engine.begin() as connection:
                await connection.run_sync(
                    lambda sync: command.upgrade(_alembic_config(sync), SIMULATION_REVISION)
                )
            world = WorldId(uuid4())
            location = LocationId(world, uuid4())
            player = PlayerId(world, uuid4())
            clock = SystemWallClock()
            handler = CommandHandler(
                database.unit_of_work,
                clock,
                world_time_source=EffectiveWorldTimeSource(clock, SystemMonotonicClock()),
            )
            await handler.execute(
                CreateWorld(request_id=RequestId(uuid4()), world_id=world, name="Preserved")
            )
            await handler.execute(
                CreateLocation(
                    request_id=RequestId(uuid4()),
                    world_id=world,
                    location_id=location,
                    name="Place",
                )
            )
            await handler.execute(
                CreatePlayer(
                    request_id=RequestId(uuid4()),
                    world_id=world,
                    player_id=player,
                    name="Player",
                    initial_location_id=location,
                )
            )
            async with database.engine.connect() as connection:
                audit = (await connection.execute(text("SELECT * FROM migration_history"))).all()
                events = (await connection.execute(text("SELECT * FROM world_events"))).all()
                receipts = (await connection.execute(text("SELECT * FROM command_receipts"))).all()
            await database.initialize()
            await database.initialize()
            async with database.engine.connect() as connection:
                assert (
                    await connection.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar_one() == HEAD_REVISION
                assert (
                    await connection.execute(text("SELECT * FROM migration_history"))
                ).all() == audit
                assert (
                    await connection.execute(text("SELECT * FROM world_events"))
                ).all() == events
                assert (
                    await connection.execute(text("SELECT * FROM command_receipts"))
                ).all() == receipts
                tables = set(
                    (
                        await connection.execute(
                            text(
                                "SELECT name FROM sqlite_master "
                                "WHERE type='table' AND name NOT GLOB 'sqlite_*'"
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                indexes = set(
                    (
                        await connection.execute(
                            text(
                                "SELECT name FROM sqlite_master "
                                "WHERE type='index' AND name NOT LIKE 'sqlite_%'"
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                observation_columns = {
                    row.name
                    for row in (
                        await connection.execute(text("PRAGMA table_info(observations)"))
                    ).all()
                }
            assert {"scenes", "scene_participants"} <= tables
            assert "basis" in observation_columns
            assert {
                "uq_scene_active_principal",
                "ix_scene_active_participants",
                "ix_player_presence_active_location",
                "ix_character_state_location",
                "uq_observation_event_principal",
                "ix_observation_principal_history",
            } <= indexes
        finally:
            await database.close()

    asyncio.run(run())
