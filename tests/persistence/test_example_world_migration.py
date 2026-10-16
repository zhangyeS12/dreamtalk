import asyncio

from alembic import command
from livingworld.infrastructure.persistence import Database
from livingworld.infrastructure.persistence.migration import (
    EXAMPLE_WORLD_REVISION,
    STICKER_DESCRIPTION_REVISION,
    _alembic_config,
)
from sqlalchemy import text


def test_0052_upgrade_only_adds_example_receipts_and_preserves_existing_rows(tmp_path):
    async def run():
        database = Database(tmp_path)
        try:
            async with database.engine.begin() as connection:
                await connection.run_sync(
                    lambda sync: command.upgrade(
                        _alembic_config(sync), STICKER_DESCRIPTION_REVISION
                    )
                )
                await connection.execute(
                    text("INSERT INTO worlds VALUES (:world, 'Synthetic legacy world', 9)"),
                    {"world": "a" * 32},
                )
                tables = (
                    (
                        await connection.execute(
                            text(
                                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                before = {
                    name: (await connection.execute(text(f'SELECT * FROM "{name}"'))).all()
                    for name in tables
                    if name != "alembic_version"
                }
            await database.initialize()
            await database.initialize()
            async with database.engine.connect() as connection:
                assert (
                    await connection.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar_one() == EXAMPLE_WORLD_REVISION
                assert (
                    await connection.execute(text("SELECT COUNT(*) FROM example_world_setups"))
                ).scalar_one() == 0
                for name, rows in before.items():
                    assert (await connection.execute(text(f'SELECT * FROM "{name}"'))).all() == rows
        finally:
            await database.close()

    asyncio.run(run())
