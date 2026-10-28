"""Build synthetic stores at older Alembic revisions for upgrade tests.

Tests used to fake an old save by dropping today's tables and rewriting
``alembic_version``. That silently broke every time a later revision added a
column. These helpers instead run the real migration chain up to the old
revision, so the schema is exactly what that release shipped.
"""

import sqlite3
from pathlib import Path

from alembic import command
from livingworld.infrastructure.persistence.migration import _alembic_config
from sqlalchemy import create_engine


def _remove(path: Path) -> None:
    for suffix in ("", "-wal", "-shm"):
        path.with_name(path.name + suffix).unlink(missing_ok=True)


def database_at(path: Path, revision: str) -> None:
    """Replace ``path`` with an empty store migrated exactly to ``revision``."""
    _remove(path)
    engine = create_engine(f"sqlite:///{path}")
    try:
        with engine.begin() as connection:
            command.upgrade(_alembic_config(connection), revision)
    finally:
        engine.dispose()


def _tables(connection: sqlite3.Connection, schema: str) -> list[str]:
    # Virtual tables and their shadow tables are rebuilt by the triggers that
    # fire while the base rows are copied, so only plain tables are copied.
    rows = connection.execute(
        f"SELECT name, sql FROM {schema}.sqlite_master WHERE type = 'table'"
    ).fetchall()
    virtual = {name for name, sql in rows if sql and sql.upper().startswith("CREATE VIRTUAL")}
    return [
        name
        for name, _ in rows
        if name != "alembic_version"
        and not name.startswith("sqlite_")
        and not any(name.startswith(f"{table}_") for table in virtual)
        and name not in virtual
    ]


def _columns(connection: sqlite3.Connection, schema: str, table: str) -> list[str]:
    return [row[1] for row in connection.execute(f'PRAGMA {schema}.table_info("{table}")')]


def rewind_store(path: Path, revision: str) -> None:
    """Rewrite the current store at ``path`` as a store at ``revision``.

    Rows of every table that already existed at ``revision`` are copied over,
    limited to the columns that revision had. Tables added later are dropped
    with their rows, which is what an old release would have saved.
    """
    legacy = path.with_name(path.name + ".legacy")
    database_at(legacy, revision)
    connection = sqlite3.connect(legacy)
    try:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("ATTACH DATABASE ? AS current", (str(path),))
        with connection:
            for table in _tables(connection, "main"):
                if table not in _tables(connection, "current"):
                    continue
                shared = set(_columns(connection, "current", table))
                columns = [name for name in _columns(connection, "main", table) if name in shared]
                selected = ", ".join(f'"{name}"' for name in columns)
                # Migrations seed some rows (schema_version); the store's own win.
                connection.execute(f'DELETE FROM main."{table}"')
                connection.execute(
                    f'INSERT INTO main."{table}" ({selected}) '
                    f'SELECT {selected} FROM current."{table}"'
                )
        connection.execute("DETACH DATABASE current")
    finally:
        connection.close()
    _remove(path)
    legacy.rename(path)
