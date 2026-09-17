"""Content-only Lorebook adapters, review warnings and unchanged world evidence."""

import asyncio
import re
import socket
import subprocess
import urllib.request
from dataclasses import replace
from hashlib import sha256
from uuid import uuid4

import pytest
from card_fixtures import json_bytes
from livingworld.application.commands import AcquireKnowledge, AssertWorldTruth, FormCharacterBelief
from livingworld.application.content import ContentDraft, ContentService
from livingworld.application.imports import (
    LOREBOOK_METADATA_KEY,
    ContentImportError,
)
from livingworld.domain.content.identifiers import LoreCollectionId, LoreEntryId
from livingworld.domain.content.serialization import json_value
from livingworld.domain.errors import DomainInvariantError
from livingworld.domain.identifiers import KnowledgeAssertionId
from livingworld.domain.knowledge import ObservationChannel
from livingworld.domain.values import WorldTime
from livingworld.infrastructure.imports import character_cards
from livingworld.infrastructure.imports.lorebooks import LorebookImporter, LorebookLimits
from livingworld.infrastructure.persistence import Database
from lorebook_fixtures import (
    IMPORTED_AT,
    book_document,
    codes,
    commit,
    preserved_card,
    roots,
    standalone,
)


def test_native_collection_has_typed_library_identity_and_complete_provenance():
    imported = standalone()
    collection, entries, characters = roots(imported)
    assert type(collection.content_id) is LoreCollectionId
    assert all(type(entry.content_id) is LoreEntryId for entry in entries)
    assert all(entry.collection_id == collection.content_id for entry in entries)
    assert all(entry.content_id.value.int != 0 for entry in entries)
    assert not characters
    assert collection.name == "Hand-authored New Eridu"
    assert collection.description.startswith("Controlled fixture")
    assert collection.activation_metadata == {}  # No invented global settings.
    assert collection.provenance.original_name == "arbitrary-source-name.json"
    raw = imported.draft.raw_imports[0]
    assert collection.provenance.content_hash == sha256(raw.original_payload).hexdigest()
    assert raw.provenance == collection.provenance
    assert (
        json_value(collection.extensions[LOREBOOK_METADATA_KEY]["source_book"]) == book_document()
    )
    assert entries[0].extensions[LOREBOOK_METADATA_KEY]["source_map_key"] == "0"
    assert entries[0].extensions[LOREBOOK_METADATA_KEY]["source_entry"]["uid"] == 0
    summary = imported.preview().lorebooks[0]
    assert summary.collection_id == collection.content_id
    assert (summary.source_entry_count, summary.canonical_entry_count) == (3, 2)
    assert summary.provenance == raw.provenance


def test_keys_preserve_case_unicode_duplicates_spaces_and_inert_js_regex():
    _, entries, _ = roots(standalone())
    assert entries[0].keywords == (
        "New Eridu",
        "/Hollows (?<name>.*)/g",
        " New Eridu ",
        "New Eridu",
        "新艾利都",
    )
    assert entries[0].secondary_keywords == ("city",)
    assert "lore_blank_keys_omitted_from_canonical" in codes(standalone())
    assert entries[1].secondary_keywords == ()
    assert entries[1].extensions[LOREBOOK_METADATA_KEY]["source_entry"]["keysecondary"] == (
        "orphan",
    )
    assert not entries[1].enabled
    assert entries[1].content.startswith("@@activate\n")


@pytest.mark.parametrize(
    "mode,symbol", [(0, "AND_ANY"), (1, "NOT_ALL"), (2, "NOT_ANY"), (3, "AND_ALL")]
)
def test_selective_logic_has_symbolic_mapping_and_recoverable_raw_integer(mode, symbol):
    document = book_document()
    document["entries"]["0"]["selectiveLogic"] = mode
    _, entries, _ = roots(standalone(document))
    assert entries[0].activation_metadata["selective_logic"] == symbol
    assert entries[0].extensions[LOREBOOK_METADATA_KEY]["source_entry"]["selectiveLogic"] == mode


@pytest.mark.parametrize(
    "position,symbol",
    [
        (0, "before_char"),
        (1, "after_char"),
        (2, "before_author_note"),
        (3, "after_author_note"),
        (4, "at_depth"),
        (5, "before_examples"),
        (6, "after_examples"),
        (7, "outlet"),
    ],
)
def test_explicit_known_native_position_maps_without_placement(position, symbol):
    document = book_document()
    document["entries"]["0"]["position"] = position
    _, entries, _ = roots(standalone(document))
    assert entries[0].insertion_metadata["position"] == symbol
    assert entries[0].extensions[LOREBOOK_METADATA_KEY]["source_entry"]["position"] == position


@pytest.mark.parametrize("position", [99, "future-position"])
def test_unknown_position_and_selective_logic_do_not_guess_semantics(position):
    document = book_document()
    document["entries"]["0"].update(position=position, selectiveLogic=99)
    imported = standalone(document)
    _, entries, _ = roots(imported)
    assert "position" not in entries[0].insertion_metadata
    assert "selective_logic" not in entries[0].activation_metadata
    assert "lore_unknown_position_preserved" in codes(imported)
    assert "lore_unknown_selective_logic_preserved" in codes(imported)


@pytest.mark.parametrize("probability,use", [(100, False), (0, True), (37.5, False)])
def test_probability_value_and_switch_remain_independent(probability, use):
    document = book_document()
    document["entries"]["0"].update(probability=probability, useProbability=use)
    _, entries, _ = roots(standalone(document))
    assert entries[0].activation_metadata["probability"] == probability
    assert entries[0].activation_metadata["useProbability"] is use


def test_advanced_metadata_unknown_fields_and_extensions_remain_complete():
    collection, entries, _ = roots(standalone())
    source = book_document()["entries"]["0"]
    for name in (
        "group",
        "groupOverride",
        "groupWeight",
        "useGroupScoring",
        "sticky",
        "cooldown",
        "delay",
        "vectorized",
        "automationId",
        "triggers",
        "ignoreBudget",
        "characterFilter",
        "excludeRecursion",
        "preventRecursion",
        "delayUntilRecursion",
        "scanDepth",
        "caseSensitive",
        "matchWholeWords",
    ):
        assert json_value(entries[0].activation_metadata[name]) == source[name]
    assert entries[0].group == "cities"
    assert entries[0].insertion_metadata["depth"] == 4
    assert entries[0].insertion_metadata["role"] == 0
    assert json_value(entries[0].extensions[LOREBOOK_METADATA_KEY]["source_entry"]) == source
    assert json_value(collection.extensions[LOREBOOK_METADATA_KEY]["unknown_fields"]) == {
        "future_book": book_document()["future_book"],
    }
    assert (
        json_value(collection.extensions[LOREBOOK_METADATA_KEY]["external_extensions"])
        == book_document()["extensions"]
    )
    assert "lore_unknown_entry_fields_preserved" in codes(standalone())
    assert "lore_activation_metadata_preserved_inert" in codes(standalone())


@pytest.mark.parametrize("version", [2, 3])
@pytest.mark.parametrize("container", ["json", "png"])
def test_embedded_book_uses_preserved_boundary_and_typed_content_binding(
    version, container, monkeypatch
):
    preserved = preserved_card(version, container=container)
    original_character = preserved.draft.contents[0]

    def forbidden(*args, **kwargs):
        pytest.fail("Normalizer reparsed the card or PNG")

    monkeypatch.setattr(character_cards, "_json", forbidden)
    monkeypatch.setattr(character_cards, "read_png", forbidden)
    imported = LorebookImporter().normalize_embedded(preserved)
    collection, entries, characters = roots(imported)
    assert characters[0].content_id == original_character.content_id
    assert characters[0].lore_collection_ids == (collection.content_id,)
    assert characters[0].lore_entry_ids == ()
    assert collection.provenance == original_character.provenance
    assert imported.draft.raw_imports == preserved.draft.raw_imports
    assert imported.draft.assets == preserved.draft.assets
    assert collection.activation_metadata == {
        "scan_depth": 3,
        "token_budget": 512,
        "recursive_scanning": False,
    }
    assert entries[0].secondary_keywords == ("city", "archive")
    assert entries[0].insertion_metadata["position"] == "before_char"
    assert entries[1].insertion_metadata["position"] == "after_char"
    assert not entries[1].enabled
    if version == 3:
        assert entries[1].activation_metadata["use_regex"] is True
    else:
        assert "use_regex" not in entries[1].activation_metadata
        assert entries[1].extensions[LOREBOOK_METADATA_KEY]["unknown_fields"]["use_regex"] is True
    assert entries[1].content == book_document(True)["entries"][1]["content"]
    assert "character_card_embedded_lore_deferred" not in codes(imported)
    assert imported.preview().lorebooks[0].source_entry_count == 3


@pytest.mark.parametrize("empty", ["", "   ", "\n\t"])
def test_empty_content_is_omitted_with_source_identity_warning_and_survives_commit(tmp_path, empty):
    async def run():
        document = book_document()
        document["entries"]["0"]["content"] = empty
        imported = standalone(document)
        collection, entries, _ = roots(imported)
        assert len(entries) == 1
        assert all(
            entry.extensions[LOREBOOK_METADATA_KEY]["source_entry"]["uid"] != 0 for entry in entries
        )
        warnings = [
            warning
            for warning in imported.preview().warnings
            if warning.code == "lore_entry_empty_content_omitted_from_canonical"
        ]
        assert any(
            warning.path == "book.entries[0]" and "identity 0" in warning.message
            for warning in warnings
        )
        database = Database(tmp_path)
        try:
            await database.initialize()
            await commit(database.content_repository(), imported)
            await database.close()
            database = Database(tmp_path)
            await database.initialize()
            loaded = await database.content_repository().load(collection.content_id)
            assert loaded == collection
            assert (
                loaded.extensions[LOREBOOK_METADATA_KEY]["source_book"]["entries"]["0"]["content"]
                == empty
            )
            raw = await database.content_repository().load_raw_import(
                collection.provenance.raw_import_id
            )
            assert raw.original_payload == json_bytes(document)
            assert (
                json_value(raw.unknown_extensions[LOREBOOK_METADATA_KEY]["source_book"]) == document
            )
        finally:
            await database.close()

    asyncio.run(run())


def test_nonblank_content_is_never_trimmed():
    document = book_document()
    document["entries"]["0"]["content"] = " \nAuthored content.\t "
    assert roots(standalone(document))[1][0].content == " \nAuthored content.\t "


def test_all_source_entries_blank_can_commit_zero_canonical_entries(tmp_path):
    async def run():
        document = {
            "entries": {
                "0": {"uid": 0, "key": [], "content": ""},
                "1": {"uid": 1, "key": [], "content": " \n "},
            }
        }
        imported = standalone(document)
        collection, entries, _ = roots(imported)
        assert not entries and collection.lore_entry_ids == ()
        summary = imported.preview().lorebooks[0]
        assert (summary.source_entry_count, summary.canonical_entry_count) == (2, 0)
        assert len(imported.preview().warnings) == 2
        database = Database(tmp_path)
        try:
            await database.initialize()
            await commit(database.content_repository(), imported)
            loaded = await database.content_repository().load(collection.content_id)
            assert loaded == collection
            assert json_value(loaded.extensions[LOREBOOK_METADATA_KEY]["source_book"]) == document
        finally:
            await database.close()

    asyncio.run(run())


def test_unknown_native_priority_and_v2_use_regex_are_not_interpreted():
    document = book_document()
    document["entries"]["0"]["priority"] = {"future": "opaque"}
    _, entries, _ = roots(standalone(document))
    assert entries[0].priority == 0
    assert (
        entries[0].extensions[LOREBOOK_METADATA_KEY]["unknown_fields"]["priority"]["future"]
        == "opaque"
    )
    book = book_document(True)
    book["entries"][0]["use_regex"] = {"future": "opaque"}
    imported = LorebookImporter().normalize_embedded(preserved_card(2, book))
    assert "use_regex" not in roots(imported)[1][0].activation_metadata
    assert "lore_unknown_entry_fields_preserved" in codes(imported)


@pytest.mark.parametrize("origin", ["native", "embedded"])
def test_fractional_source_order_is_preserved_without_rounding(origin):
    if origin == "native":
        document = book_document()
        document["entries"]["0"]["order"] = 2.5
        imported = standalone(document)
        field = "order"
    else:
        document = book_document(True)
        document["entries"][0]["insertion_order"] = 2.5
        imported = LorebookImporter().normalize_embedded(preserved_card(3, document))
        field = "insertion_order"
    entry = roots(imported)[1][0]
    assert entry.order == 0
    assert entry.extensions[LOREBOOK_METADATA_KEY]["source_entry"][field] == 2.5
    assert "lore_fractional_order_preserved" in codes(imported)


def test_v3_ambiguous_secondary_string_is_not_split_and_commit_restart_preserves_it(tmp_path):
    async def run():
        book = book_document(True)
        book["entries"][0]["secondary_keys"] = "a,b"
        imported = LorebookImporter().normalize_embedded(preserved_card(3, book))
        collection, entries, characters = roots(imported)
        assert entries[0].secondary_keywords == ()
        assert (
            entries[0].extensions[LOREBOOK_METADATA_KEY]["source_entry"]["secondary_keys"] == "a,b"
        )
        assert "lore_secondary_keys_ambiguous_string_preserved" in codes(imported)
        database = Database(tmp_path)
        try:
            await database.initialize()
            await commit(database.content_repository(), imported)
            await database.close()
            database = Database(tmp_path)
            await database.initialize()
            for root in (collection, *entries, *characters):
                loaded = await database.content_repository().load(root.content_id)
                assert loaded == root
                assert type(loaded.content_id) is type(root.content_id)
            loaded = await database.content_repository().load(entries[0].content_id)
            assert loaded.secondary_keywords == ()
            assert (
                loaded.extensions[LOREBOOK_METADATA_KEY]["source_entry"]["secondary_keys"] == "a,b"
            )
        finally:
            await database.close()

    asyncio.run(run())


def test_same_source_and_uid_in_two_books_do_not_overwrite_on_commit(tmp_path):
    async def run():
        first, second = standalone(), standalone()
        first_collection, first_entries, _ = roots(first)
        second_collection, second_entries, _ = roots(second)
        assert first_collection.content_id != second_collection.content_id
        assert first_entries[0].content_id != second_entries[0].content_id
        assert first_collection.provenance.content_hash == second_collection.provenance.content_hash
        database = Database(tmp_path)
        try:
            await database.initialize()
            repository = database.content_repository()
            await commit(repository, first)
            await commit(repository, second)
            await database.close()
            database = Database(tmp_path)
            await database.initialize()
            repository = database.content_repository()
            for root in (*first.draft.contents, *second.draft.contents):
                assert await repository.load(root.content_id) == root
        finally:
            await database.close()

    asyncio.run(run())


@pytest.mark.parametrize("origin", ["native", "embedded"])
def test_import_cannot_change_truth_principal_knowledge_or_canonical_world_ledger(
    environment, origin
):
    async def run():
        env = environment
        try:
            await env.initialize()
            truth_id = KnowledgeAssertionId(env.world, uuid4())
            for command_type, values in (
                (AssertWorldTruth, {"assertion_id": truth_id}),
                (
                    FormCharacterBelief,
                    {
                        "assertion_id": KnowledgeAssertionId(env.world, uuid4()),
                        "character_id": env.alice,
                        "epistemic_status": "believed",
                        "valid_from": WorldTime(123),
                    },
                ),
            ):
                await env.handler.execute(
                    env.command(
                        command_type,
                        subject="unrelated",
                        predicate="state",
                        value="protected",
                        **values,
                    )
                )
            await env.handler.execute(
                env.command(
                    AcquireKnowledge,
                    assertion_id=KnowledgeAssertionId(env.world, uuid4()),
                    receiver_id=env.player,
                    source_assertion_id=truth_id,
                    channel=ObservationChannel.TOLD,
                )
            )
            before = await env.snapshot()
            readers = (
                env.database.world_truth_reader(env.world),
                env.database.character_knowledge_reader(env.alice),
                env.database.player_knowledge_reader(env.player),
            )
            known = [await reader.list() for reader in readers]
            assert all(known)
            imported = (
                standalone()
                if origin == "native"
                else LorebookImporter().normalize_embedded(preserved_card())
            )
            await commit(env.database.content_repository(), imported)
            assert await env.snapshot() == before
            assert [await reader.list() for reader in readers] == known
            assert roots(imported)[1][0].content == "New Eridu is surrounded by Hollows."
            await env.restart()
            assert await env.snapshot() == before
        finally:
            await env.database.close()

    asyncio.run(run())


def test_untrusted_regex_vector_automation_and_prompt_text_have_no_effects(monkeypatch):
    keys = set(book_document()["entries"]["0"]["key"])
    keys.update(book_document(True)["entries"][1]["keys"])

    def forbidden(*args, **kwargs):
        pytest.fail("Importer attempted a shell, automation or network action")

    for name in ("compile", "search", "match", "fullmatch"):
        original = getattr(re, name)

        def guarded(pattern, *args, _original=original, **kwargs):
            if isinstance(pattern, str) and pattern in keys:
                pytest.fail("External trigger expression reached the Python regex engine")
            return _original(pattern, *args, **kwargs)

        monkeypatch.setattr(re, name, guarded)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    imported = standalone()
    embedded = LorebookImporter().normalize_embedded(preserved_card())
    assert roots(imported)[1][0].activation_metadata["vectorized"] is True
    assert roots(embedded)[1][1].keywords == ("/(?<name>.*),Hollows/gi",)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda book: book.update(entries=[]),
        lambda book: book.update(entries="wrong"),
        lambda book: book["entries"].update({"0": []}),
        lambda book: book["entries"]["0"].update(key="not an array"),
        lambda book: book["entries"]["0"].update(key=[1]),
        lambda book: book["entries"]["0"].update(content=7),
        lambda book: book["entries"]["0"].update(keysecondary="a,b"),
        lambda book: book["entries"]["0"].update(probability=-1),
        lambda book: book["entries"]["0"].update(probability=101),
        lambda book: book["entries"]["0"].update(sticky=-1),
        lambda book: book["entries"]["0"].update(groupWeight=-1),
        lambda book: book["entries"]["0"].update(disable=1),
        lambda book: book["entries"]["0"].update(extensions=[]),
        lambda book: book.update(token_budget=-1),
        lambda book: book.update(recursive_scanning=1),
    ],
)
def test_native_malformed_structure_and_known_ranges_fail_explicitly(mutation):
    document = book_document()
    mutation(document)
    with pytest.raises(ContentImportError):
        standalone(document)


@pytest.mark.parametrize(
    "payload",
    [
        b'{"entries":{},"entries":{}}',
        b'{"entries":{"0":{"key":[],"key":[],"content":"x"}}}',
        b'{"entries":{},"unknown":NaN}',
        b'{"entries":{},"unknown":"\\ud800"}',
        b"\xff",
        b"[]",
    ],
)
def test_strict_json_rejects_duplicate_keys_nonfinite_surrogates_and_nonobject_root(payload):
    with pytest.raises(ContentImportError):
        LorebookImporter().parse(payload, imported_at=IMPORTED_AT)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda book: book["entries"][0].update(enabled=1),
        lambda book: book["entries"][0].pop("keys"),
        lambda book: book["entries"][0].pop("use_regex"),
        lambda book: book["entries"][0].update(secondary_keys=[1]),
        lambda book: book["entries"][0].update(content=None),
    ],
)
def test_embedded_known_structure_validation_does_not_guess(mutation):
    document = book_document(True)
    mutation(document)
    with pytest.raises(ContentImportError):
        LorebookImporter().normalize_embedded(preserved_card(3, document))


def test_v2_secondary_string_is_structurally_invalid():
    book = book_document(True)
    book["entries"][0]["secondary_keys"] = "a,b"
    with pytest.raises(ContentImportError):
        LorebookImporter().normalize_embedded(preserved_card(2, book))


def test_empty_collection_unnamed_book_and_explicit_settings_are_preserved(tmp_path):
    async def run():
        imported = standalone(
            {"entries": {}, "scan_depth": 0, "token_budget": 0, "recursive_scanning": False}
        )
        collection, entries, _ = roots(imported)
        assert collection.name == "" and not entries
        assert collection.activation_metadata == {
            "scan_depth": 0,
            "token_budget": 0,
            "recursive_scanning": False,
        }
        database = Database(tmp_path)
        try:
            await database.initialize()
            await commit(database.content_repository(), imported)
            assert await database.content_repository().load(collection.content_id) == collection
        finally:
            await database.close()

    asyncio.run(run())


def test_new_entry_without_owner_and_duplicate_or_unresolved_ownership_are_rejected(tmp_path):
    async def run():
        imported = standalone()
        collection, entries, _ = roots(imported)
        unbound = replace(entries[0], collection_id=None)
        draft = ContentDraft(contents=(unbound,), raw_imports=imported.draft.raw_imports)
        database = Database(tmp_path)
        try:
            await database.initialize()
            service = ContentService(database.content_repository())
            preview = service.preview(draft)
            with pytest.raises(DomainInvariantError, match="requires one LoreCollection"):
                await service.commit(
                    preview,
                    reviewed_hash=preview.preview_hash,
                    expected_revisions={unbound.content_id: None},
                )
            assert await database.content_repository().load(unbound.content_id) is None
            with pytest.raises(DomainInvariantError, match="requires one LoreCollection"):
                await database.content_repository().save(draft, {unbound.content_id: None})
        finally:
            await database.close()
        with pytest.raises(DomainInvariantError, match="Unresolved"):
            replace(imported.draft, contents=entries)
        with pytest.raises(DomainInvariantError, match="ownership"):
            replace(imported.draft, contents=(replace(collection, lore_entry_ids=()), *entries))
        with pytest.raises(DomainInvariantError):
            replace(collection, lore_entry_ids=(entries[0].content_id,) * 2)
        with pytest.raises(DomainInvariantError):
            replace(entries[0], collection_id=entries[0].content_id)

    asyncio.run(run())


def test_resource_limits_apply_before_normalization():
    for limits, document in (
        (LorebookLimits(max_json_bytes=5), {"entries": {}}),
        (LorebookLimits(max_json_depth=2), {"entries": {}, "unknown": [[[0]]]}),
        (LorebookLimits(max_entries=1), book_document()),
    ):
        with pytest.raises(ContentImportError, match="limit"):
            LorebookImporter(limits).parse(json_bytes(document), imported_at=IMPORTED_AT)


def test_normalizer_without_embedded_book_is_identity_and_repeat_is_explicit_error():
    from card_fixtures import card_document
    from livingworld.infrastructure.imports.character_cards import CharacterCardImporter

    no_book = CharacterCardImporter().parse(json_bytes(card_document(2)), imported_at=IMPORTED_AT)
    assert LorebookImporter().normalize_embedded(no_book) is no_book
    normalized = LorebookImporter().normalize_embedded(preserved_card())
    with pytest.raises(ContentImportError, match="already_normalized"):
        LorebookImporter().normalize_embedded(normalized)
