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
LEGACY_PRIVACY = '[{"start":0,"end":6,"character_id":"bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"}]'

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


@pytest.mark.parametrize("private", [False, True])
def test_privacy_upgrade_preserves_existing_audience_without_guessing_fallback(tmp_path, private):
    async def run():
        database = Database(tmp_path)
        try:
            await _upgrade_to(
                database, "0065_chat_privacy" if private else "0064_character_evolution_kind"
            )
            async with database.engine.begin() as connection:
                await connection.execute(
                    text("INSERT INTO worlds VALUES (:world, 'Legacy', 9)"), {"world": WORLD}
                )
                await connection.execute(
                    text(
                        "INSERT INTO players (world_id, player_id, name, revision) "
                        "VALUES (:world, :player, 'Player', 0)"
                    ),
                    {"world": WORLD, "player": "d" * 32},
                )
                await connection.execute(
                    text(
                        "INSERT INTO chat_conversations "
                        "(world_id, conversation_id, player_id, kind, created_at_utc) "
                        "VALUES (:world, :conversation, :player, 'group', '2026-01-01T00:00:00Z')"
                    ),
                    {"world": WORLD, "conversation": "e" * 32, "player": "d" * 32},
                )
                await connection.execute(
                    text(
                        "INSERT INTO chat_turns (world_id, turn_id, conversation_id, request_id, "
                        "fingerprint, token_ceiling, status, created_at_utc) "
                        "VALUES (:world, :turn, :conversation, :request, :fingerprint, "
                        "50000, 'pending', '2026-01-01T00:00:00Z')"
                    ),
                    {
                        "world": WORLD,
                        "turn": "1" * 32,
                        "conversation": "e" * 32,
                        "request": "2" * 32,
                        "fingerprint": "3" * 64,
                    },
                )
                await connection.execute(
                    text(
                        "INSERT INTO chat_messages "
                        "(world_id, message_id, conversation_id, turn_id, "
                        "position, sender_player_id, text, created_at_utc) "
                        "VALUES (:world, :message, :conversation, :turn, 1, :player, "
                        "'PUBLIC_LEGACY', '2026-01-01T00:00:00Z')"
                    ),
                    {
                        "world": WORLD,
                        "message": "4" * 32,
                        "conversation": "e" * 32,
                        "turn": "1" * 32,
                        "player": "d" * 32,
                    },
                )
                if private:
                    await connection.execute(
                        text("UPDATE chat_messages SET privacy_json = :privacy"),
                        {"privacy": LEGACY_PRIVACY},
                    )
            await database.initialize()
            await database.initialize()
            async with database.engine.connect() as connection:
                row = (
                    await connection.execute(
                        text("SELECT text, privacy_json, privacy_fallback FROM chat_messages")
                    )
                ).one()
                assert row[0] == "PUBLIC_LEGACY" and row[2] is None
                assert row[1] == (LEGACY_PRIVACY if private else None)
                assert (
                    await connection.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar_one() == HEAD_REVISION
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


def test_evolution_upgrade_preserves_active_locked_and_inactive_draft_versions(tmp_path):
    async def run():
        database = Database(tmp_path)
        try:
            await _upgrade_to(database, "0063_card_packs")
            async with database.engine.begin() as connection:
                await connection.execute(
                    text("INSERT INTO worlds VALUES (:world, 'Legacy', 9)"), {"world": WORLD}
                )
                await connection.execute(
                    text(
                        "INSERT INTO world_content_imports "
                        "(import_id,replaces_import_id,world_id,reviewed_hash,kind,"
                        "snapshot_json,accepted_at,removed_at) "
                        "VALUES (:root,NULL,:world,:hash,'character','{}',"
                        "'2026-11-01T12:00:00Z',NULL)"
                    ),
                    dict(root="d" * 32, world=WORLD, hash="e" * 64),
                )
                for identity, source, state, selected, locked in [
                    ("1" * 32, "user", "active", 1, 1),
                    ("2" * 32, "model", "inactive", 0, 0),
                ]:
                    await connection.execute(
                        text(
                            "INSERT INTO character_card_evolution "
                            "(entry_id,world_id,root_import_id,field,scope,text,state,"
                            "selected,locked,source,created_at_utc,quote,confidence) "
                            "VALUES (:id,:world,:root,'personality','global',:content,"
                            ":state,:selected,:locked,:source,"
                            "'2026-11-01T12:00:00Z','Evidence',0.9)"
                        ),
                        dict(
                            id=identity,
                            world=WORLD,
                            root="d" * 32,
                            content="Preserved " + source,
                            state=state,
                            selected=selected,
                            locked=locked,
                            source=source,
                        ),
                    )
                before = (
                    (
                        await connection.execute(
                            text("SELECT * FROM character_card_evolution ORDER BY entry_id")
                        )
                    )
                    .mappings()
                    .all()
                )
            await database.initialize()
            async with database.engine.connect() as connection:
                after = (
                    (
                        await connection.execute(
                            text("SELECT * FROM character_card_evolution ORDER BY entry_id")
                        )
                    )
                    .mappings()
                    .all()
                )
                assert [{key: row[key] for key in before[0]} for row in after] == [
                    dict(row) for row in before
                ]
                assert [row["change_kind"] for row in after] == [None, None]
            await database.initialize()
        finally:
            await database.close()

    asyncio.run(run())


def test_card_pack_upgrade_preserves_existing_library_payload_and_images(tmp_path):
    """0063 adds empty containers; it must not rewrite or auto-enrol existing cards."""

    async def run():
        database = Database(tmp_path)
        try:
            await _upgrade_to(database, "0062_card_library")
            async with database.engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO card_library VALUES (:id, 'Existing card', 7, :digest, "
                        ":draft, :design, '2026-11-01T12:00:00Z')"
                    ),
                    dict(
                        id="d" * 32,
                        digest="e" * 64,
                        draft='{"original":"synthetic preserved payload"}',
                        design='{"original":"synthetic independent faces"}',
                    ),
                )
                await connection.execute(
                    text(
                        "INSERT INTO card_library_images VALUES "
                        "(:id, :digest, 10, 'image/png', 2, 3)"
                    ),
                    dict(id="d" * 32, digest="e" * 64),
                )
                before = (await connection.execute(text("SELECT * FROM card_library"))).all()
                images = (await connection.execute(text("SELECT * FROM card_library_images"))).all()
            await database.initialize()
            async with database.engine.connect() as connection:
                assert (
                    await connection.execute(text("SELECT * FROM card_library"))
                ).all() == before
                assert (
                    await connection.execute(text("SELECT * FROM card_library_images"))
                ).all() == images
                for table in ["card_packs", "card_pack_members", "card_pack_images"]:
                    assert (
                        await connection.execute(text(f"SELECT count(*) FROM {table}"))
                    ).scalar_one() == 0
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
