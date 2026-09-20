"""Content survives restart, edits are atomic, migration leaves Stage 2 intact."""

import asyncio
from dataclasses import replace
from uuid import uuid4

import pytest
from alembic import command
from alembic.operations import Operations
from livingworld.application.content import ContentConflictError, ContentService
from livingworld.domain.content.identifiers import ContentAssetId, RawImportId
from livingworld.domain.content.models import ContentRevision
from livingworld.domain.errors import DomainInvariantError
from livingworld.domain.identifiers import WorldId
from livingworld.domain.values import Revision
from livingworld.infrastructure.persistence import Database
from livingworld.infrastructure.persistence.errors import (
    MigrationCompatibilityError,
    PersistenceDataError,
)
from livingworld.infrastructure.persistence.migration import (
    ACTION_TABLES,
    HEAD_REVISION,
    LEDGER_REVISION,
    SIMULATION_TABLES,
    _alembic_config,
)
from livingworld.infrastructure.persistence.models import Base
from sqlalchemy import text

CONTENT_TABLES = (
    "content_character_definitions",
    "content_worlds",
    "content_lore_entries",
    "content_assets",
    "content_raw_imports",
    "content_lore_collections",
)


async def commit(repository, draft, expected=None):
    service = ContentService(repository)
    preview = service.preview(draft)
    await service.commit(
        preview,
        reviewed_hash=preview.preview_hash,
        expected_revisions=expected
        if expected is not None
        else {root.content_id: None for root in draft.contents},
    )


async def rows(database, tables):
    async with database.engine.connect() as connection:
        return {
            table: (await connection.execute(text(f"SELECT * FROM {table}"))).all()
            for table in tables
        }


async def table_columns(database, tables):
    async with database.engine.connect() as connection:
        return {
            table: tuple(
                row.name
                for row in (await connection.execute(text(f"PRAGMA table_info({table})"))).all()
            )
            for table in tables
        }


async def rows_for_columns(database, columns):
    async with database.engine.connect() as connection:
        return {
            table: (
                await connection.execute(text(f"SELECT {', '.join(table_columns)} FROM {table}"))
            ).all()
            for table, table_columns in columns.items()
        }


def test_content_roots_typed_ids_provenance_raw_and_assets_survive_restart(
    tmp_path, canonical_draft
):
    async def run():
        database = Database(tmp_path)
        try:
            await database.initialize()
            await commit(database.content_repository(), canonical_draft)
        finally:
            await database.close()
        restarted = Database(tmp_path)
        try:
            await restarted.initialize()
            await restarted.initialize()
            repository = restarted.content_repository()
            for content in canonical_draft.contents:
                loaded = await repository.load(content.content_id)
                assert loaded == content
                assert type(loaded.content_id) is type(content.content_id)
                assert type(loaded.revision) is ContentRevision
            assert (
                await repository.load_asset(canonical_draft.assets[0].asset_id)
                == canonical_draft.assets[0]
            )
            assert (
                await repository.load_raw_import(canonical_draft.raw_imports[0].import_id)
                == canonical_draft.raw_imports[0]
            )
            stored = await rows(restarted, CONTENT_TABLES)
            assert all(len(value) == 1 for value in stored.values())
            assert len((await rows(restarted, ["migration_history"]))["migration_history"]) == 1
            with pytest.raises(DomainInvariantError):
                await repository.load(WorldId(canonical_draft.contents[0].content_id.value))
        finally:
            await restarted.close()

    asyncio.run(run())


def test_content_edit_version_and_unchanged_dependencies(tmp_path, canonical_draft):
    async def run():
        database = Database(tmp_path)
        try:
            await database.initialize()
            repository = database.content_repository()
            await commit(repository, canonical_draft)
            changed = replace(
                canonical_draft.contents[0],
                display_name="Edited Alice",
                revision=ContentRevision(1),
            )
            draft = replace(canonical_draft, contents=(changed,) + canonical_draft.contents[1:])
            expected = {root.content_id: ContentRevision() for root in draft.contents}
            await commit(repository, draft, expected)
            assert await repository.load(changed.content_id) == changed
            assert (
                await repository.load(canonical_draft.contents[1].content_id)
                == canonical_draft.contents[1]
            )
            before = await rows(database, CONTENT_TABLES)
            with pytest.raises(ContentConflictError, match="Stale"):
                await commit(repository, draft, expected)
            assert await rows(database, CONTENT_TABLES) == before
            await database.close()
            database = Database(tmp_path)
            await database.initialize()
            assert await database.content_repository().load(changed.content_id) == changed
        finally:
            await database.close()

    asyncio.run(run())


@pytest.mark.parametrize(
    "failure",
    [
        "late_version",
        "new_asset_collision",
        "raw_identity_collision",
        "revision_gap",
        "duplicate_create",
    ],
)
def test_content_save_failure_rolls_back_entire_draft(tmp_path, canonical_draft, failure):
    async def run():
        database = Database(tmp_path)
        try:
            await database.initialize()
            repository = database.content_repository()
            await commit(repository, canonical_draft)
            before = await rows(database, CONTENT_TABLES)
            expected = {root.content_id: ContentRevision() for root in canonical_draft.contents}
            changed = replace(
                canonical_draft.contents[0], display_name="Changed", revision=ContentRevision(1)
            )
            draft = replace(canonical_draft, contents=(changed,) + canonical_draft.contents[1:])
            if failure == "late_version":
                expected[canonical_draft.contents[1].content_id] = ContentRevision(99)
            elif failure == "new_asset_collision":
                fresh = replace(canonical_draft.assets[0], asset_id=ContentAssetId(uuid4()))
                colliding = replace(canonical_draft.assets[0], resource_reference="opaque:changed")
                draft = replace(draft, assets=(fresh, colliding))
            elif failure == "raw_identity_collision":
                raw = canonical_draft.raw_imports[0]
                new_id = RawImportId(uuid4())
                fresh_provenance = replace(raw.provenance, raw_import_id=new_id)
                fresh = replace(raw, import_id=new_id, provenance=fresh_provenance)
                colliding = replace(raw, unknown_extensions={"changed": "opaque"})
                draft = replace(draft, raw_imports=(fresh, colliding))
            elif failure == "revision_gap":
                draft = replace(
                    draft,
                    contents=(replace(changed, revision=ContentRevision(2)),) + draft.contents[1:],
                )
            else:
                expected = {root.content_id: None for root in canonical_draft.contents}
            with pytest.raises(ContentConflictError):
                await commit(repository, draft, expected)
            assert await rows(database, CONTENT_TABLES) == before
        finally:
            await database.close()

    asyncio.run(run())


@pytest.mark.parametrize("mode", ["missing", "runtime_revision", "nonzero_create"])
def test_repository_preconditions_are_explicit_and_typed(tmp_path, canonical_draft, mode):
    async def run():
        database = Database(tmp_path)
        try:
            await database.initialize()
            expected = {root.content_id: None for root in canonical_draft.contents}
            draft = canonical_draft
            if mode == "missing":
                expected.pop(draft.contents[0].content_id)
            elif mode == "runtime_revision":
                expected[draft.contents[0].content_id] = Revision()
            else:
                draft = replace(
                    draft,
                    contents=(replace(draft.contents[0], revision=ContentRevision(1)),)
                    + draft.contents[1:],
                )
            with pytest.raises((DomainInvariantError, ContentConflictError)):
                await commit(database.content_repository(), draft, expected)
            assert all(not value for value in (await rows(database, CONTENT_TABLES)).values())
        finally:
            await database.close()

    asyncio.run(run())


@pytest.mark.parametrize(
    "mutation",
    [
        "UPDATE content_character_definitions SET semantic_hash = '" + "0" * 64 + "'",
        "UPDATE content_character_definitions SET title = 'corrupt independent metadata'",
    ],
)
def test_stored_semantic_hash_corruption_fails_closed(tmp_path, canonical_draft, mutation):
    async def run():
        database = Database(tmp_path)
        try:
            await database.initialize()
            repository = database.content_repository()
            await commit(repository, canonical_draft)
            async with database.engine.begin() as connection:
                await connection.execute(text(mutation))
            with pytest.raises(PersistenceDataError, match="metadata_mismatch"):
                await repository.load(canonical_draft.contents[0].content_id)
            before = await rows(database, CONTENT_TABLES)
            expected = {root.content_id: root.revision for root in canonical_draft.contents}
            with pytest.raises(PersistenceDataError, match="metadata_mismatch"):
                await commit(repository, canonical_draft, expected)
            assert await rows(database, CONTENT_TABLES) == before
        finally:
            await database.close()

    asyncio.run(run())


@pytest.mark.parametrize("fail", [False, True])
def test_0005_takeover_preserves_every_runtime_and_audit_row(tmp_path, populate, monkeypatch, fail):
    async def run():
        database = Database(tmp_path)
        tables = tuple(
            table
            for table in Base.metadata.tables
            if table not in SIMULATION_TABLES | ACTION_TABLES
        ) + ("schema_version", "migration_history")
        try:
            async with database.engine.begin() as connection:
                await connection.run_sync(
                    lambda sync: command.upgrade(_alembic_config(sync), LEDGER_REVISION)
                )
            await populate(database)
            preserved_columns = await table_columns(database, tables)
            before = await rows_for_columns(database, preserved_columns)
            original = Operations.create_table
            if fail:

                def injected(self, name, *args, **kwargs):
                    if name == "content_assets":
                        raise RuntimeError("injected_content_migration_failure")
                    return original(self, name, *args, **kwargs)

                monkeypatch.setattr(Operations, "create_table", injected)
                with pytest.raises(RuntimeError, match="injected_content"):
                    await database.initialize()
                async with database.engine.connect() as connection:
                    assert (
                        await connection.execute(text("SELECT version_num FROM alembic_version"))
                    ).scalar_one() == LEDGER_REVISION
                    assert not (
                        await connection.execute(
                            text("SELECT name FROM sqlite_master WHERE name LIKE 'content_%'")
                        )
                    ).all()
                assert await rows_for_columns(database, preserved_columns) == before
                monkeypatch.setattr(Operations, "create_table", original)
            await database.initialize()
            await database.initialize()
            assert await rows_for_columns(database, preserved_columns) == before
            async with database.engine.connect() as connection:
                assert (
                    await connection.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar_one() == HEAD_REVISION
                assert (await connection.execute(text("PRAGMA foreign_key_check"))).all() == []
        finally:
            await database.close()

    asyncio.run(run())


@pytest.mark.parametrize(
    "revision,mutation,error",
    [
        (LEDGER_REVISION, "CREATE TABLE content_worlds (unexpected TEXT)", "schema_state_mismatch"),
        (
            HEAD_REVISION,
            "ALTER TABLE content_worlds ADD COLUMN unexpected TEXT",
            "schema_shape_mismatch",
        ),
    ],
)
def test_partial_or_unknown_content_schema_rejected(tmp_path, revision, mutation, error):
    async def run():
        database = Database(tmp_path)
        try:
            async with database.engine.begin() as connection:
                await connection.run_sync(
                    lambda sync: command.upgrade(_alembic_config(sync), revision)
                )
                await connection.execute(text(mutation))
            before = await rows(database, ("alembic_version", "migration_history"))
            with pytest.raises(MigrationCompatibilityError, match=error):
                await database.initialize()
            assert await rows(database, ("alembic_version", "migration_history")) == before
        finally:
            await database.close()

    asyncio.run(run())
