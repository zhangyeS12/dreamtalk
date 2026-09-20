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
    ACTION_REVISION,
    BUDGET_REVISION,
    HEAD_REVISION,
    _alembic_config,
)
from sqlalchemy import text

SIMULATION_TABLES = {
    "simulation_queue_cursors",
    "simulation_scheduled_triggers",
    "simulation_activations",
    "simulation_activation_causes",
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
            assert {
                "ix_simulation_trigger_due",
                "uq_simulation_schedule_request",
                "ix_simulation_activation_due",
                "ix_simulation_activation_target",
                "uq_simulation_activation_pending_coalescing",
                "ix_simulation_activation_cause_order",
                "ix_simulation_activation_cause_identity",
            } <= indexes
        finally:
            await database.close()

    asyncio.run(run())


def test_0013_upgrade_preserves_legacy_activation_and_backfills_typed_provenance(tmp_path):
    async def run():
        database = Database(tmp_path)
        world_id = WorldId(uuid4())
        trigger_id = uuid4()
        activation_id = uuid4()
        try:
            async with database.engine.begin() as connection:
                await connection.run_sync(
                    lambda sync: command.upgrade(_alembic_config(sync), ACTION_REVISION)
                )
            handler = CommandHandler(database.unit_of_work, SystemWallClock())
            await handler.execute(
                CreateWorld(
                    request_id=RequestId(uuid4()), world_id=world_id, name="Legacy Scheduler World"
                )
            )
            async with database.engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO simulation_queue_cursors(world_id,last_position) "
                        "VALUES (:world,1)"
                    ),
                    {"world": world_id.value.hex},
                )
                await connection.execute(
                    text(
                        "INSERT INTO simulation_scheduled_triggers("
                        "world_id,trigger_id,due_at,priority,enqueue_position,kind,"
                        "payload_version,payload,status,created_at_utc,fired_at_utc,"
                        "cancelled_at_utc,revision,causation_request_id,correlation_id) "
                        "VALUES (:world,:trigger,42,-1,1,'legacy.kind',1,:payload,'fired',"
                        ":created,:created,NULL,1,NULL,NULL)"
                    ),
                    {
                        "world": world_id.value.hex,
                        "trigger": trigger_id.hex,
                        "payload": '{"legacy":"kept"}',
                        "created": "2026-09-19T12:00:00.000000Z",
                    },
                )
                await connection.execute(
                    text(
                        "INSERT INTO simulation_activations("
                        "world_id,activation_id,source_trigger_id,kind,payload_version,"
                        "due_at,payload,status,materialized_at_utc) "
                        "VALUES (:world,:activation,:trigger,'legacy.kind',1,42,:payload,"
                        "'pending',:created)"
                    ),
                    {
                        "world": world_id.value.hex,
                        "activation": activation_id.hex,
                        "trigger": trigger_id.hex,
                        "payload": '{"legacy":"kept"}',
                        "created": "2026-09-19T12:00:00.000000Z",
                    },
                )

            await database.initialize()
            async with database.engine.connect() as connection:
                trigger = (
                    await connection.execute(
                        text(
                            "SELECT * FROM simulation_scheduled_triggers "
                            "WHERE world_id=:world AND trigger_id=:trigger"
                        ),
                        {"world": world_id.value.hex, "trigger": trigger_id.hex},
                    )
                ).one()
                activation = (
                    await connection.execute(
                        text(
                            "SELECT * FROM simulation_activations "
                            "WHERE world_id=:world AND activation_id=:activation"
                        ),
                        {"world": world_id.value.hex, "activation": activation_id.hex},
                    )
                ).one()
                causes = (
                    await connection.execute(
                        text(
                            "SELECT * FROM simulation_activation_causes "
                            "WHERE world_id=:world AND activation_id=:activation"
                        ),
                        {"world": world_id.value.hex, "activation": activation_id.hex},
                    )
                ).all()
            assert trigger.activation_target_kind == "world"
            assert trigger.activation_target_id == world_id.value.hex
            assert trigger.activation_kind == "world_orchestration"
            assert trigger.activation_attention == "none"
            assert activation.source_trigger_id == trigger_id.hex
            assert activation.target_kind == "world"
            assert activation.target_id == world_id.value.hex
            assert activation.activation_kind == "world_orchestration"
            assert activation.priority == -1
            assert activation.enqueue_position == 1
            assert activation.payload == '{"legacy":"kept"}'
            assert len(causes) == 1
            assert causes[0].cause_identity == f"scheduled_trigger:{trigger_id.hex}"
            assert causes[0].source_trigger_id == trigger_id.hex
            assert causes[0].request_fingerprint == trigger_id.hex.encode().hex()

            before = causes
            await database.initialize()
            async with database.engine.connect() as connection:
                after = (
                    await connection.execute(
                        text(
                            "SELECT * FROM simulation_activation_causes "
                            "WHERE world_id=:world AND activation_id=:activation"
                        ),
                        {"world": world_id.value.hex, "activation": activation_id.hex},
                    )
                ).all()
            assert after == before
        finally:
            await database.close()

    asyncio.run(run())
