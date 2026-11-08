import asyncio

import pytest
from alembic import command
from alembic.operations import Operations
from livingworld.application.errors import IdempotencyConflictError
from livingworld.domain.contracts import RequestId
from livingworld.infrastructure.persistence import Database
from livingworld.infrastructure.persistence.errors import MigrationCompatibilityError
from livingworld.infrastructure.persistence.migration import (
    DOMAIN_BASELINE_REVISION,
    HEAD_REVISION,
    _alembic_config,
)
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


async def seed_0002(database):
    async with database.engine.begin() as connection:
        await connection.run_sync(
            lambda sync: command.upgrade(_alembic_config(sync), DOMAIN_BASELINE_REVISION)
        )
        await connection.execute(
            text("INSERT INTO worlds VALUES (:world, 'Legacy', 9)"), {"world": "a" * 32}
        )
        for identity in ("b" * 32, "c" * 32):
            await connection.execute(
                text("INSERT INTO characters VALUES (:world, :id, 'Character', 2)"),
                {"world": "a" * 32, "id": identity},
            )
        await connection.execute(
            text(
                "INSERT INTO relationships VALUES "
                "(:world, 'character', :source, 'character', :target, "
                ":source, NULL, :target, NULL, 9)"
            ),
            {"world": "a" * 32, "source": "b" * 32, "target": "c" * 32},
        )
        await connection.execute(
            text(
                "INSERT INTO command_receipts "
                "(world_id, request_id, command_type, status, created_at, revision) "
                "VALUES (:world, :request, 'legacy', 'stored', "
                "'2026-01-01T00:00:00.000000+00:00', 2)"
            ),
            {"world": "a" * 32, "request": "d" * 32},
        )


def test_0002_rows_preserved_and_metrics_zeroed_on_alembic_upgrade(tmp_path):
    async def run():
        database = Database(tmp_path)
        try:
            await seed_0002(database)
            async with database.engine.connect() as connection:
                audit = (await connection.execute(text("SELECT * FROM migration_history"))).all()
                old_receipt = (
                    await connection.execute(text("SELECT * FROM command_receipts"))
                ).one()
            await database.initialize()
            await database.initialize()
            async with database.engine.connect() as connection:
                assert (
                    await connection.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar_one() == HEAD_REVISION
                relationship = (await connection.execute(text("SELECT * FROM relationships"))).one()
                assert relationship.revision == 9
                assert (relationship.affinity, relationship.trust, relationship.familiarity) == (
                    0,
                    0,
                    0,
                )
                receipt = (await connection.execute(text("SELECT * FROM command_receipts"))).one()
                assert tuple(receipt[: len(old_receipt)]) == tuple(old_receipt)
                assert receipt.command_fingerprint is receipt.result_payload is None
                assert (
                    await connection.execute(text("SELECT * FROM migration_history"))
                ).all() == audit
            # Legacy proof receipts lack semantic identity: fail closed, never report success.
            async with database.unit_of_work() as uow:
                with pytest.raises(IdempotencyConflictError, match="unverifiable"):
                    await uow.receipts.existing(RequestId.parse("d" * 32), "e" * 64)
        finally:
            await database.close()

    asyncio.run(run())


def test_0003_failure_rolls_back_alter_columns_and_cursor(tmp_path, monkeypatch):
    async def run():
        database = Database(tmp_path)
        try:
            await seed_0002(database)
            original = Operations.add_column

            def fail(self, table_name, column, *args, **kwargs):
                original(self, table_name, column, *args, **kwargs)
                if column.name == "trust":
                    raise RuntimeError("injected_migration_failure")

            with monkeypatch.context() as patch:
                patch.setattr(Operations, "add_column", fail)
                with pytest.raises(RuntimeError, match="injected_migration_failure"):
                    await database.initialize()
            async with database.engine.connect() as connection:
                assert (
                    await connection.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar_one() == DOMAIN_BASELINE_REVISION
                assert "affinity" not in [
                    row.name
                    for row in (
                        await connection.execute(text("PRAGMA table_info(relationships)"))
                    ).all()
                ]
            await database.initialize()
        finally:
            await database.close()

    asyncio.run(run())


def test_0002_partial_schema_is_not_repaired(tmp_path):
    async def run():
        database = Database(tmp_path)
        try:
            await seed_0002(database)
            async with database.engine.begin() as connection:
                await connection.execute(
                    text("ALTER TABLE relationships ADD COLUMN affinity INTEGER")
                )
            with pytest.raises(MigrationCompatibilityError, match="schema_shape_mismatch"):
                await database.initialize()
        finally:
            await database.close()

    asyncio.run(run())


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("affinity", -101),
        ("affinity", 101),
        ("trust", -101),
        ("trust", 101),
        ("familiarity", -1),
        ("familiarity", 101),
        ("affinity", 0.5),
    ],
)
def test_metric_database_constraints(tmp_path, column, value):
    async def run():
        database = Database(tmp_path)
        try:
            await seed_0002(database)
            await database.initialize()
            with pytest.raises(IntegrityError, match=f"ck_relationship_{column}"):
                async with database.engine.begin() as connection:
                    await connection.execute(
                        text(f"UPDATE relationships SET {column} = :value"), {"value": value}
                    )
        finally:
            await database.close()

    asyncio.run(run())
