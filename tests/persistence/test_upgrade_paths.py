"""Old-save upgrade regressions.

Every released Alembic revision must still open and upgrade to head with its
rows intact, and physical column order must never be part of the schema
contract (0.1.91 failed to start because of exactly that).
"""

import asyncio

import pytest
from alembic import command
from livingworld.infrastructure.persistence import Database
from livingworld.infrastructure.persistence.errors import MigrationCompatibilityError
from livingworld.infrastructure.persistence.migration import (
    _SUPPORTED_REVISIONS,
    DOMAIN_BASELINE_REVISION,
    HEAD_REVISION,
    LEGACY_TABLES,
    _alembic_config,
)
from sqlalchemy import text
from sqlalchemy.engine.reflection import Inspector

WORLD = "a" * 32
CHARACTERS = ("b" * 32, "c" * 32)

# Revisions from the first one that has domain tables up to (excluding) head.
UPGRADE_SOURCES = _SUPPORTED_REVISIONS[_SUPPORTED_REVISIONS.index(DOMAIN_BASELINE_REVISION) : -1]


async def _upgrade_to(database, revision):
    async with database.engine.begin() as connection:
        await connection.run_sync(lambda sync: command.upgrade(_alembic_config(sync), revision))


async def _seed_baseline_rows(database):
    """Write rows with the 0002 baseline layout, the oldest managed save shape."""
    async with database.engine.begin() as connection:
        await connection.execute(
            text("INSERT INTO worlds VALUES (:world, 'Legacy', 9)"), {"world": WORLD}
        )
        for identity in CHARACTERS:
            await connection.execute(
                text("INSERT INTO characters VALUES (:world, :id, 'Character', 2)"),
                {"world": WORLD, "id": identity},
            )
        await connection.execute(
            text(
                "INSERT INTO relationships VALUES "
                "(:world, 'character', :source, 'character', :target, "
                ":source, NULL, :target, NULL, 9)"
            ),
            {"world": WORLD, "source": CHARACTERS[0], "target": CHARACTERS[1]},
        )


async def _current_revision(database):
    async with database.engine.connect() as connection:
        return (
            await connection.execute(text("SELECT version_num FROM alembic_version"))
        ).scalar_one()


@pytest.mark.parametrize("revision", UPGRADE_SOURCES)
def test_every_released_revision_upgrades_to_head_with_rows(tmp_path, revision):
    async def run():
        database = Database(tmp_path)
        try:
            await _upgrade_to(database, DOMAIN_BASELINE_REVISION)
            await _seed_baseline_rows(database)
            await _upgrade_to(database, revision)
            # Startup validates the old revision as-is, upgrades, then validates head.
            await database.initialize()
            assert await _current_revision(database) == HEAD_REVISION
            # A second start on the upgraded save must also pass.
            await database.initialize()
            async with database.engine.connect() as connection:
                worlds = (await connection.execute(text("SELECT world_id, name FROM worlds"))).all()
                characters = (
                    await connection.execute(
                        text("SELECT character_id FROM characters ORDER BY character_id")
                    )
                ).all()
                relationships = (
                    await connection.execute(text("SELECT revision FROM relationships"))
                ).all()
            assert [tuple(row) for row in worlds] == [(WORLD, "Legacy")]
            assert [row[0] for row in characters] == list(CHARACTERS)
            assert [row[0] for row in relationships] == [9]
        finally:
            await database.close()

    asyncio.run(run())


def test_physical_column_order_is_not_part_of_schema_contract(tmp_path, monkeypatch):
    """SQLite appends added columns; ORM declaration order must not matter.

    The frozen pre-Alembic tables keep their exact DDL check and are excluded.
    """
    original = Inspector.get_columns

    def reversed_columns(self, table_name, *args, **kwargs):
        columns = original(self, table_name, *args, **kwargs)
        if table_name in LEGACY_TABLES or table_name == "alembic_version":
            return columns
        return list(reversed(columns))

    async def run():
        database = Database(tmp_path)
        try:
            await database.initialize()
            monkeypatch.setattr(Inspector, "get_columns", reversed_columns)
            await database.initialize()
            assert await _current_revision(database) == HEAD_REVISION
        finally:
            await database.close()

    asyncio.run(run())


@pytest.mark.parametrize(
    "mutation",
    [
        "ALTER TABLE character_card_evolution ADD COLUMN unexpected TEXT",
        "ALTER TABLE worlds ADD COLUMN unexpected INTEGER",
    ],
)
def test_unexpected_column_still_fails_closed(tmp_path, mutation):
    async def run():
        database = Database(tmp_path)
        try:
            await database.initialize()
            async with database.engine.begin() as connection:
                await connection.execute(text(mutation))
            with pytest.raises(MigrationCompatibilityError, match="alembic_schema_shape_mismatch"):
                await database.initialize()
        finally:
            await database.close()

    asyncio.run(run())
