"""Additive 0007 takeover preserves legacy identities, shared references and hashes."""

import asyncio
from dataclasses import replace
from uuid import uuid4

import pytest
from alembic import command
from alembic.operations import Operations
from livingworld.application.content import ContentConflictError, ContentDraft, ContentService
from livingworld.application.imports import ImportDraft
from livingworld.domain.content.identifiers import LoreCollectionId
from livingworld.domain.content.models import (
    ContentProvenance,
    ContentRevision,
    ContentSourceKind,
)
from livingworld.domain.content.serialization import semantic_hash, serialize_content
from livingworld.infrastructure.persistence import Database
from livingworld.infrastructure.persistence.errors import MigrationCompatibilityError
from livingworld.infrastructure.persistence.migration import (
    CONTENT_REVISION,
    HEAD_REVISION,
    _alembic_config,
)
from lorebook_fixtures import commit, roots, standalone
from sqlalchemy import text


async def snapshot(database):
    async with database.engine.connect() as connection:
        return {
            table: (await connection.execute(text(f"SELECT * FROM {table}"))).all()
            for table in (
                "content_character_definitions",
                "content_worlds",
                "content_lore_entries",
                "migration_history",
                "schema_version",
                "alembic_version",
            )
        }


@pytest.mark.parametrize("injected_failure", [False, True])
def test_legacy_unbound_rows_shared_references_json_and_hashes_survive_0007(
    tmp_path,
    canonical_draft,
    monkeypatch,
    injected_failure,
):
    async def run():
        database = Database(tmp_path)
        provenance = ContentProvenance(
            source_kind=ContentSourceKind.NATIVE, source_format="legacy-fixture"
        )
        char, world, lore, _ = canonical_draft.contents
        legacy = (
            replace(char, provenance=provenance, assets=()),
            replace(world, provenance=provenance, assets=()),
            replace(lore, provenance=provenance, collection_id=None),
        )
        try:
            async with database.engine.begin() as connection:
                await connection.run_sync(
                    lambda sync: command.upgrade(_alembic_config(sync), CONTENT_REVISION)
                )
                for root, table, title in (
                    (legacy[0], "content_character_definitions", legacy[0].display_name),
                    (legacy[1], "content_worlds", legacy[1].title),
                    (legacy[2], "content_lore_entries", legacy[2].title),
                ):
                    await connection.execute(
                        text(
                            f"INSERT INTO {table} "
                            "(content_id,title,content_version,revision,"
                            "semantic_hash,canonical_json) "
                            "VALUES (:id,:title,1,0,:hash,:json)"
                        ),
                        {
                            "id": root.content_id.value.hex,
                            "title": title,
                            "hash": semantic_hash(root),
                            "json": serialize_content(root),
                        },
                    )
            before = await snapshot(database)
            original = Operations.execute
            if injected_failure:

                def fail(self, sql, *args, **kwargs):
                    if str(sql).startswith("ALTER TABLE content_lore_entries"):
                        raise RuntimeError("injected_lore_ownership_failure")
                    return original(self, sql, *args, **kwargs)

                monkeypatch.setattr(Operations, "execute", fail)
                with pytest.raises(RuntimeError, match="injected_lore"):
                    await database.initialize()
                assert await snapshot(database) == before
                async with database.engine.connect() as connection:
                    assert not (
                        await connection.execute(
                            text(
                                "SELECT name FROM sqlite_master "
                                "WHERE name = 'content_lore_collections'"
                            )
                        )
                    ).all()
                monkeypatch.setattr(Operations, "execute", original)
            await database.initialize()
            await database.initialize()
            after = await snapshot(database)
            for table in before:
                if table == "alembic_version":
                    assert after[table] == [(HEAD_REVISION,)]
                elif table == "content_lore_entries":
                    assert [tuple(row[:-1]) for row in after[table]] == [
                        tuple(row) for row in before[table]
                    ]
                    assert all(row[-1] is None for row in after[table])
                else:
                    assert after[table] == before[table]
            async with database.engine.connect() as connection:
                assert (
                    await connection.execute(text("SELECT * FROM content_lore_collections"))
                ).all() == []
                assert (await connection.execute(text("PRAGMA foreign_key_check"))).all() == []
            repository = database.content_repository()
            for root in legacy:
                assert await repository.load(root.content_id) == root
            assert legacy[0].lore_entry_ids == legacy[1].lore_entry_ids == (legacy[2].content_id,)
            # Explicit legacy edits remain possible without a lazy ownership rewrite.
            edited = replace(legacy[0], display_name="Legacy edited", revision=ContentRevision(1))
            preview = ContentService(repository).preview(
                ContentDraft(contents=(edited, *legacy[1:]))
            )
            await ContentService(repository).commit(
                preview,
                reviewed_hash=preview.preview_hash,
                expected_revisions={root.content_id: ContentRevision() for root in legacy},
            )
            assert await repository.load(legacy[2].content_id) == legacy[2]
            await database.close()
            database = Database(tmp_path)
            await database.initialize()
            assert await database.content_repository().load(legacy[2].content_id) == legacy[2]
        finally:
            await database.close()

    asyncio.run(run())


def test_owned_entry_cannot_be_reassigned_and_collection_cannot_orphan_persisted_entries(tmp_path):
    async def run():
        imported = standalone()
        collection, entries, _ = roots(imported)
        database = Database(tmp_path)
        try:
            await database.initialize()
            repository = database.content_repository()
            await commit(repository, imported)
            before = await snapshot(database)
            replacement_collection = replace(collection, content_id=LoreCollectionId(uuid4()))
            reassigned = tuple(
                replace(
                    entry,
                    collection_id=replacement_collection.content_id,
                    revision=ContentRevision(1),
                )
                for entry in entries
            )
            changed = ImportDraft(
                replace(imported.draft, contents=(replacement_collection, *reassigned))
            )
            with pytest.raises(ContentConflictError, match="reassigned"):
                await commit(
                    repository,
                    changed,
                    {
                        replacement_collection.content_id: None,
                        **{entry.content_id: ContentRevision() for entry in entries},
                    },
                )
            assert await snapshot(database) == before
            orphaning = replace(collection, lore_entry_ids=(), revision=ContentRevision(1))
            changed = ImportDraft(replace(imported.draft, contents=(orphaning,)))
            with pytest.raises(ContentConflictError, match="ownership mismatch"):
                await commit(repository, changed, {collection.content_id: ContentRevision()})
            assert await snapshot(database) == before
        finally:
            await database.close()

    asyncio.run(run())


def test_non_destructive_shared_collection_references_and_edit_roundtrip(tmp_path, canonical_draft):
    async def run():
        imported = standalone()
        collection, _, _ = roots(imported)
        native = ContentProvenance(
            source_kind=ContentSourceKind.NATIVE, source_format="test-authored"
        )
        base = canonical_draft.contents[0]
        first = replace(
            base,
            provenance=native,
            assets=(),
            lore_entry_ids=(),
            lore_collection_ids=(collection.content_id,),
        )
        second = replace(first, content_id=type(first.content_id)(uuid4()), display_name="Second")
        draft = ImportDraft(
            replace(imported.draft, contents=(*imported.draft.contents, first, second))
        )
        database = Database(tmp_path)
        try:
            await database.initialize()
            await commit(database.content_repository(), draft)
            edited = replace(
                collection, description="Edited authored book", revision=ContentRevision(1)
            )
            edited_draft = ImportDraft(
                replace(draft.draft, contents=(edited, *draft.draft.contents[1:]))
            )
            await commit(
                database.content_repository(),
                edited_draft,
                {root.content_id: root.revision for root in draft.draft.contents},
            )
            await database.close()
            database = Database(tmp_path)
            await database.initialize()
            assert await database.content_repository().load(first.content_id) == first
            assert await database.content_repository().load(second.content_id) == second
            assert await database.content_repository().load(edited.content_id) == edited
        finally:
            await database.close()

    asyncio.run(run())


@pytest.mark.parametrize(
    "mutation",
    [
        "ALTER TABLE content_lore_collections ADD COLUMN unexpected TEXT",
        "ALTER TABLE content_lore_entries ADD COLUMN unexpected TEXT",
    ],
)
def test_lore_schema_drift_fails_closed(tmp_path, mutation):
    async def run():
        database = Database(tmp_path)
        try:
            await database.initialize()
            async with database.engine.begin() as connection:
                await connection.execute(text(mutation))
            with pytest.raises(MigrationCompatibilityError, match="shape_mismatch"):
                await database.initialize()
        finally:
            await database.close()

    asyncio.run(run())
