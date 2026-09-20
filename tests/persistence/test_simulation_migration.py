import asyncio
from uuid import uuid4

import pytest
from alembic import command
from alembic.operations import Operations
from livingworld.application.command_handler import CommandHandler
from livingworld.application.commands import CreateWorld
from livingworld.domain.contracts import RequestId
from livingworld.domain.identifiers import WorldId
from livingworld.infrastructure.clock import SystemWallClock
from livingworld.infrastructure.persistence import Database
from livingworld.infrastructure.persistence.migration import (
    BUDGET_REVISION,
    HEAD_REVISION,
    _alembic_config,
)
from sqlalchemy import text

SIMULATION_TABLES = {
    "simulation_queue_cursors",
    "simulation_scheduled_triggers",
    "simulation_activations",
    "simulation_schedule_receipts",
}


@pytest.mark.parametrize("inject_failure", [False, True])
def test_0011_upgrade_preserves_0010_world_and_rolls_back_ddl(
    tmp_path, monkeypatch, inject_failure
):
    async def run():
        database = Database(tmp_path)
        try:
            async with database.engine.begin() as connection:
                await connection.run_sync(
                    lambda sync: command.upgrade(_alembic_config(sync), BUDGET_REVISION)
                )
            world_id = WorldId(uuid4())
            handler = CommandHandler(database.unit_of_work, SystemWallClock())
            await handler.execute(
                CreateWorld(
                    request_id=RequestId(uuid4()), world_id=world_id, name="Preserved World"
                )
            )
            async with database.engine.connect() as connection:
                audit = (await connection.execute(text("SELECT * FROM migration_history"))).all()
            if inject_failure:
                original = Operations.create_index

                def fail(self, name, *args, **kwargs):
                    if name == "ix_simulation_trigger_due":
                        raise RuntimeError("controlled_simulation_ddl_failure")
                    return original(self, name, *args, **kwargs)

                monkeypatch.setattr(Operations, "create_index", fail)
                with pytest.raises(RuntimeError, match="controlled_simulation_ddl_failure"):
                    await database.initialize()
            else:
                await database.initialize()
                await database.initialize()
            async with database.engine.connect() as connection:
                revision = (
                    await connection.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar_one()
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
                assert (
                    await connection.execute(
                        text("SELECT name FROM worlds WHERE world_id=:world"),
                        {"world": world_id.value.hex},
                    )
                ).scalar_one() == "Preserved World"
                assert (
                    await connection.execute(text("SELECT * FROM migration_history"))
                ).all() == audit
            assert revision == (BUDGET_REVISION if inject_failure else HEAD_REVISION)
            assert (
                SIMULATION_TABLES.isdisjoint(tables)
                if inject_failure
                else SIMULATION_TABLES <= tables
            )
        finally:
            await database.close()

    asyncio.run(run())


def test_fresh_database_has_scheduler_indexes_and_restart_is_stable(tmp_path):
    async def run():
        database = Database(tmp_path)
        try:
            await database.initialize()
            async with database.engine.connect() as connection:
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
                before = {
                    table: (
                        await connection.execute(text(f"SELECT count(*) FROM {table}"))
                    ).scalar_one()
                    for table in SIMULATION_TABLES
                }
            await database.initialize()
            async with database.engine.connect() as connection:
                after = {
                    table: (
                        await connection.execute(text(f"SELECT count(*) FROM {table}"))
                    ).scalar_one()
                    for table in SIMULATION_TABLES
                }
                revision = (
                    await connection.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar_one()
            assert revision == HEAD_REVISION
            assert before == after == {table: 0 for table in SIMULATION_TABLES}
            assert {"ix_simulation_trigger_due", "uq_simulation_schedule_request"} <= indexes
        finally:
            await database.close()

    asyncio.run(run())
