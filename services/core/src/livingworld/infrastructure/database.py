"""Compatibility import for the application database lifecycle."""

from pathlib import Path

from livingworld.infrastructure.persistence import Database


async def bootstrap_database(data_dir: Path) -> Database:
    """Create and initialize the process-owned database."""

    database = Database(data_dir)
    try:
        await database.initialize()
    except BaseException:
        await database.close()
        raise
    return database
