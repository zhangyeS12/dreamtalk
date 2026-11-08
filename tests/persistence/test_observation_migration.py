"""Upgrade real historical schemas; compare all legacy semantic values."""

import asyncio
from importlib import import_module
from uuid import UUID

import pytest
from alembic import command
from alembic.operations.batch import ApplyBatchImpl
from livingworld.domain.identifiers import ObservationId, WorldId
from livingworld.infrastructure.persistence import Database
from livingworld.infrastructure.persistence.mapping import to_domain
from livingworld.infrastructure.persistence.migration import (
    COMMAND_REVISION,
    HEAD_REVISION,
    _alembic_config,
)
from livingworld.infrastructure.persistence.models import ObservationRecord
from sqlalchemy import select, text


async def seed_0003(database):
    async with database.engine.begin() as connection:
        await connection.run_sync(
            lambda sync: command.upgrade(_alembic_config(sync), COMMAND_REVISION)
        )
        await connection.execute(
            text("INSERT INTO worlds VALUES (:world, 'Legacy', 0)"), {"world": "a" * 32}
        )
        await connection.execute(
            text("INSERT INTO characters VALUES (:world, :id, 'Receiver', 0)"),
            {"world": "a" * 32, "id": "b" * 32},
        )
        await connection.execute(
            text(
                "INSERT INTO knowledge_assertions "
                "(world_id, assertion_id, scope, subject, predicate, value, "
                "epistemic_status, valid_from, revision) "
                "VALUES (:world, :id, 'truth', '门', 'state', "
                "'\"locked\"', 'asserted', -9, 0)"
            ),
            {"world": "a" * 32, "id": "c" * 32},
        )
        for channel, observed, created in (
            ("told", 2**53 + 17, "2026-01-02T03:04:05.123456+00:00"),
            ("news", -7, None),
        ):
            await connection.execute(
                text(
                    "INSERT INTO observations "
                    "(world_id, principal_kind, principal_id, target_kind, target_id, "
                    "channel, observed_at, principal_character_id, target_assertion_id, "
                    "created_at) "
                    "VALUES (:world, 'character', :receiver, 'assertion', :source, "
                    ":channel, :observed, "
                    ":receiver, :source, :created)"
                ),
                {
                    "world": "a" * 32,
                    "receiver": "b" * 32,
                    "source": "c" * 32,
                    "channel": channel,
                    "observed": observed,
                    "created": created,
                },
            )


async def observations(database):
    async with database.engine.connect() as connection:
        return [
            dict(row)
            for row in (
                await connection.execute(text("SELECT * FROM observations ORDER BY channel"))
            ).mappings()
        ]


def test_legacy_observations_preserved_and_backfill_deterministic(tmp_path):
    async def run():
        migrated = []
        for directory in (tmp_path / "first", tmp_path / "second"):
            database = Database(directory)
            try:
                await seed_0003(database)
                before = await observations(database)
                await database.initialize()
                await database.initialize()
                after = await observations(database)
                assert [
                    {
                        key: value
                        for key, value in row.items()
                        if key not in {"observation_id", "basis"}
                    }
                    for row in after
                ] == before
                assert all(row["basis"] is None for row in after)
                migration = import_module(
                    "livingworld.infrastructure.persistence.migrations.versions.0004_observation_identity"
                )
                assert [row["observation_id"] for row in after] == [
                    migration.legacy_observation_uuid(row).hex for row in before
                ]
                async with database._sessions() as session:
                    records = (await session.scalars(select(ObservationRecord))).all()
                    for record in records:
                        value = to_domain(record)
                        assert type(value.observation_id) is ObservationId
                        assert value.observation_id.world_id == WorldId(UUID("a" * 32))
                        assert value.observation_id.value.hex == record.observation_id.hex
                async with database.engine.connect() as connection:
                    assert (
                        await connection.execute(text("SELECT version_num FROM alembic_version"))
                    ).scalar_one() == HEAD_REVISION
                    assert not (await connection.execute(text("PRAGMA foreign_key_check"))).all()
                migrated.append(after)
            finally:
                await database.close()
        assert migrated[0] == migrated[1]

    asyncio.run(run())


def test_observation_migration_failure_rolls_back_rows_and_cursor(tmp_path, monkeypatch):
    async def run():
        database = Database(tmp_path)
        try:
            await seed_0003(database)
            before = await observations(database)
            original = ApplyBatchImpl._create

            def fail(self, *args, **kwargs):
                original(self, *args, **kwargs)
                if self.table.name == "observations":
                    raise RuntimeError("injected_observation_migration_failure")

            with monkeypatch.context() as patch:
                patch.setattr(ApplyBatchImpl, "_create", fail)
                with pytest.raises(RuntimeError, match="injected_observation"):
                    await database.initialize()
            assert await observations(database) == before
            async with database.engine.connect() as connection:
                assert (
                    await connection.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar_one() == COMMAND_REVISION
            await database.initialize()
        finally:
            await database.close()

    asyncio.run(run())
