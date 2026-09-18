"""External semantic round trips, reviewed loss decisions and pure content export."""

import asyncio
import builtins
import json
import re
import socket
import subprocess
import urllib.request
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pytest
from card_fixtures import card_document, json_bytes
from livingworld.application.commands import AcquireKnowledge, AssertWorldTruth, FormCharacterBelief
from livingworld.application.content import ContentDraft
from livingworld.application.exports import (
    CharacterBookVersion,
    ContentExportError,
    ExportDecisionRequiredError,
    ExportRequest,
    ExportService,
    ExportTarget,
    V3CharacterBookOptions,
)
from livingworld.application.imports import LOREBOOK_METADATA_KEY
from livingworld.domain.content.identifiers import LoreEntryId
from livingworld.domain.content.models import ContentRevision
from livingworld.domain.content.serialization import json_value, serialize_content
from livingworld.domain.identifiers import KnowledgeAssertionId
from livingworld.domain.knowledge import ObservationChannel
from livingworld.domain.values import WorldTime
from livingworld.infrastructure.exports.json_content import JsonContentExporter
from livingworld.infrastructure.imports.character_cards import (
    CARD_METADATA_KEY,
    CharacterCardImporter,
)
from livingworld.infrastructure.imports.lorebooks import LorebookImporter
from lorebook_fixtures import IMPORTED_AT, book_document, commit, preserved_card, roots, standalone
from sqlalchemy import text


def export(draft, target, content_id=None, **options):
    return ExportService(JsonContentExporter()).export(
        ExportRequest(
            draft=draft,
            content_id=content_id or draft.contents[0].content_id,
            target_format=target,
            **options,
        )
    )


def document(result):
    return json.loads(result.serialized_bytes)


def warning_codes(result):
    return {warning.code for warning in result.warnings}


def edit_root(draft, edited):
    return replace(
        draft,
        contents=tuple(
            edited if root.content_id == edited.content_id else root for root in draft.contents
        ),
    )


def character_semantics(character):
    return {
        field: json_value(getattr(character, field))
        for field in (
            "display_name",
            "description",
            "personality",
            "scenario",
            "creator_notes",
            "example_dialogue",
            "authored_instructions",
            "tags",
        )
    }


def lore_semantics(imported):
    collection, entries, _ = roots(imported)
    return (
        collection.name,
        collection.description,
        json_value(collection.activation_metadata),
        [
            {
                field: json_value(getattr(entry, field))
                for field in (
                    "title",
                    "comment",
                    "content",
                    "keywords",
                    "secondary_keywords",
                    "enabled",
                    "priority",
                    "order",
                    "group",
                    "activation_metadata",
                    "insertion_metadata",
                )
            }
            for entry in entries
        ],
    )


@pytest.mark.parametrize(
    "version,target", [(2, ExportTarget.CHARACTER_CARD_V2), (3, ExportTarget.CHARACTER_CARD_V3)]
)
def test_character_json_semantic_round_trip_and_deterministic_result(version, target):
    imported = CharacterCardImporter().parse(
        json_bytes(card_document(version)), imported_at=IMPORTED_AT
    )
    before = imported.draft.preview_hash()
    result = export(imported.draft, target)
    assert result == export(imported.draft, target)
    assert result.content_type == "application/json" and result.suggested_extension == ".json"
    assert result.semantic_hash == sha256(result.serialized_bytes).hexdigest()
    assert document(result)["spec_version"] == ("2.0" if version == 2 else "3.0")
    reimported = CharacterCardImporter().parse(result.serialized_bytes, imported_at=IMPORTED_AT)
    first, second = imported.draft.contents[0], reimported.draft.contents[0]
    assert character_semantics(first) == character_semantics(second)
    keys = (
        "creator",
        "character_version",
        "external_extensions",
        "unknown_top_level",
        "unknown_data",
        "nickname",
        "creator_notes_multilingual",
        "source",
        "group_only_greetings",
        "creation_date",
        "modification_date",
    )
    for key in keys:
        assert first.extensions[CARD_METADATA_KEY].get(key) == second.extensions[
            CARD_METADATA_KEY
        ].get(key)
    assert [asset.extensions["character_card_descriptor"] for asset in imported.draft.assets] == [
        asset.extensions["character_card_descriptor"] for asset in reimported.draft.assets
    ]
    assert imported.draft.preview_hash() == before


def test_world_info_semantic_round_trip_does_not_resurrect_omitted_entries():
    imported = standalone()
    result = export(imported.draft, ExportTarget.SILLYTAVERN_WORLD_INFO)
    output = document(result)
    assert len(output["entries"]) == 2
    assert all(entry["content"].strip() for entry in output["entries"].values())
    assert output["entries"]["0"]["uid"] == 0
    assert output["entries"]["0"]["key"] == list(roots(imported)[1][0].keywords)
    assert output["entries"]["0"]["future_entry"] == book_document()["entries"]["0"]["future_entry"]
    reimported = LorebookImporter().parse(result.serialized_bytes, imported_at=IMPORTED_AT)
    assert lore_semantics(imported) == lore_semantics(reimported)
    assert imported.draft.raw_imports[0].original_payload != result.serialized_bytes


@pytest.mark.parametrize("version", [2, 3])
def test_character_book_export_and_embedded_semantic_round_trip(version):
    imported = LorebookImporter().normalize_embedded(preserved_card(version))
    collection, _, characters = roots(imported)
    target = ExportTarget.CHARACTER_CARD_V2 if version == 2 else ExportTarget.CHARACTER_CARD_V3
    card = export(imported.draft, target, characters[0].content_id)
    book = export(
        imported.draft,
        ExportTarget.CHARACTER_BOOK,
        collection.content_id,
        character_book_version=CharacterBookVersion.V2 if version == 2 else CharacterBookVersion.V3,
    )
    assert document(card)["data"]["character_book"] == document(book)
    assert len(document(book)["entries"]) == 2
    reimported = LorebookImporter().normalize_embedded(
        CharacterCardImporter().parse(card.serialized_bytes, imported_at=IMPORTED_AT)
    )
    assert lore_semantics(imported) == lore_semantics(reimported)
    assert character_semantics(characters[0]) == character_semantics(roots(reimported)[2][0])


@pytest.mark.parametrize("version", [2, 3])
def test_edited_known_fields_override_stale_and_forged_unknown_paths(version):
    source = card_document(version)
    source["future_top"] = {"retain": [1, False]}
    source["data"]["future_data"] = {"nested": {"name": "opaque"}}
    imported = CharacterCardImporter().parse(json_bytes(source), imported_at=IMPORTED_AT)
    character = imported.draft.contents[0]
    extensions = json_value(character.extensions)
    metadata = extensions[CARD_METADATA_KEY]
    metadata["unknown_top_level"].update(spec="forged", spec_version="0", data={"name": "forged"})
    metadata["unknown_data"].update(
        name="forged", tags=[""], nickname="forged", character_book={"entries": []}
    )
    edited = replace(
        character,
        display_name="Current Name",
        description="Current Description",
        example_dialogue=("Current Example",),
        tags=(" Current Tag ", "Current Tag"),
        extensions=extensions,
        revision=ContentRevision(1),
    )
    target = ExportTarget.CHARACTER_CARD_V2 if version == 2 else ExportTarget.CHARACTER_CARD_V3
    output = document(export(edit_root(imported.draft, edited), target))
    assert output["spec"] == f"chara_card_v{version}"
    assert output["spec_version"] == ("2.0" if version == 2 else "3.0")
    assert output["data"]["name"] == "Current Name"
    assert output["data"]["description"] == "Current Description"
    assert output["data"]["mes_example"] == "Current Example"
    assert output["data"]["tags"] == [" Current Tag ", "Current Tag"]
    assert "character_book" not in output["data"]
    assert output["future_top"] == source["future_top"]
    assert output["data"]["future_data"] == source["data"]["future_data"]
    assert output["data"]["extensions"] == source["data"]["extensions"]
    assert output["data"].get("nickname") == ("Billy" if version == 3 else None)


def test_explicit_cross_format_export_warns_and_does_not_inject_opaque_data():
    source = card_document(3)
    source["data"]["extensions"] = {"vendor": {"opaque": "retained only internally"}}
    imported = CharacterCardImporter().parse(json_bytes(source), imported_at=IMPORTED_AT)
    result = export(imported.draft, ExportTarget.CHARACTER_CARD_V2)
    output = document(result)
    assert "future_top" not in output and "future_data" not in output["data"]
    assert output["data"]["extensions"] == {}
    for field in (
        "nickname",
        "source",
        "group_only_greetings",
        "creator_notes_multilingual",
        "assets",
        "creation_date",
        "modification_date",
    ):
        assert field not in output["data"]
        assert any(
            w.code == "v3_field_not_representable_in_v2" and w.path == f"data.{field}"
            for w in result.warnings
        )
    assert "target_format_does_not_preserve_source_extension" in warning_codes(result)
    assert CharacterCardImporter().parse(result.serialized_bytes, imported_at=IMPORTED_AT)
    assert imported.draft.contents[0].extensions[CARD_METADATA_KEY]["external_extensions"]


def test_v2_to_v3_has_required_empty_greetings_without_invented_optional_content():
    imported = preserved_card(2, book={"entries": []})
    result = export(imported.draft, ExportTarget.CHARACTER_CARD_V3)
    data = document(result)["data"]
    assert data["group_only_greetings"] == [] and data["assets"] == []
    for field in (
        "nickname",
        "source",
        "creator_notes_multilingual",
        "creation_date",
        "modification_date",
    ):
        assert field not in data
    assert "character_book" not in data
    assert "unnormalized_source_character_book_not_exported" in warning_codes(result)
    assert CharacterCardImporter().parse(result.serialized_bytes, imported_at=IMPORTED_AT)


@pytest.mark.parametrize("explicit", [True, False])
def test_explicit_v3_regex_value_wins_over_caller_policy(explicit):
    imported = LorebookImporter().normalize_embedded(preserved_card(3))
    collection, entries, _ = roots(imported)
    edited = replace(
        entries[0], activation_metadata={**entries[0].activation_metadata, "use_regex": explicit}
    )
    result = export(
        edit_root(imported.draft, edited),
        ExportTarget.CHARACTER_BOOK,
        collection.content_id,
        character_book_version=CharacterBookVersion.V3,
        v3_book_options=V3CharacterBookOptions(not explicit),
    )
    assert document(result)["entries"][0]["use_regex"] is explicit
    assert "v3_use_regex_supplied_by_export_policy" not in warning_codes(result)


@pytest.mark.parametrize("policy", [True, False])
def test_unspecified_v3_regex_uses_only_explicit_book_policy_with_warning(policy):
    imported = standalone()
    result = export(
        imported.draft,
        ExportTarget.CHARACTER_BOOK,
        character_book_version=CharacterBookVersion.V3,
        v3_book_options=V3CharacterBookOptions(policy),
    )
    assert all(entry["use_regex"] is policy for entry in document(result)["entries"])
    assert sum(w.code == "v3_use_regex_supplied_by_export_policy" for w in result.warnings) == 2
    assert "use_regex" not in roots(imported)[1][0].activation_metadata


@pytest.mark.parametrize("source", ["native", "v2", "edited_v3"])
def test_unspecified_regex_is_never_inferred_from_source_keys_or_old_source_value(source):
    if source == "native":
        imported = standalone()
    else:
        imported = LorebookImporter().normalize_embedded(preserved_card(2 if source == "v2" else 3))
        if source == "edited_v3":
            entry = roots(imported)[1][0]
            activation = json_value(entry.activation_metadata)
            del activation["use_regex"]
            imported = replace(
                imported,
                draft=edit_root(imported.draft, replace(entry, activation_metadata=activation)),
            )
    collection = roots(imported)[0]
    with pytest.raises(ExportDecisionRequiredError) as error:
        export(
            imported.draft,
            ExportTarget.CHARACTER_BOOK,
            collection.content_id,
            character_book_version=CharacterBookVersion.V3,
        )
    assert error.value.code == "v3_use_regex_decision_required"
    assert error.value.path == "book.entries[0].use_regex"


def test_v3_secondary_arrays_are_authoritative_over_ambiguous_or_stale_raw_values():
    book = book_document(True)
    book["entries"][0]["secondary_keys"] = "a,b"
    imported = LorebookImporter().normalize_embedded(preserved_card(3, book))
    collection, entries, characters = roots(imported)
    result = export(imported.draft, ExportTarget.CHARACTER_CARD_V3, characters[0].content_id)
    assert document(result)["data"]["character_book"]["entries"][0]["secondary_keys"] == []
    edited = replace(entries[0], secondary_keywords=("b", " a ", "b"))
    result = export(
        edit_root(imported.draft, edited), ExportTarget.CHARACTER_CARD_V3, characters[0].content_id
    )
    assert document(result)["data"]["character_book"]["entries"][0]["secondary_keys"] == [
        "b",
        " a ",
        "b",
    ]
    reimported = LorebookImporter().normalize_embedded(
        CharacterCardImporter().parse(result.serialized_bytes, imported_at=IMPORTED_AT)
    )
    assert roots(reimported)[1][0].secondary_keywords == edited.secondary_keywords
    assert entries[0].extensions[LOREBOOK_METADATA_KEY]["source_entry"]["secondary_keys"] == "a,b"
    assert collection.lore_entry_ids == tuple(entry.content_id for entry in entries)


@pytest.mark.parametrize(
    "title,comment,loss", [("Same", "Same", False), ("Title", "Comment", True), ("Title", "", True)]
)
def test_world_info_comment_is_canonical_comment_and_independent_title_is_warned(
    title, comment, loss
):
    imported = standalone()
    entry = roots(imported)[1][0]
    result = export(
        edit_root(imported.draft, replace(entry, title=title, comment=comment)),
        ExportTarget.SILLYTAVERN_WORLD_INFO,
    )
    output = document(result)["entries"]["0"]
    assert output["comment"] == comment
    assert not {"title", "name", "livingworld_title"} & output.keys()
    assert output["extensions"] == book_document()["entries"]["0"]["extensions"]
    warnings = [w for w in result.warnings if w.path == "book.entries[0].title"]
    assert bool(warnings) is loss
    if loss:
        assert warnings[0].code == "lore_title_not_representable_in_st_world_info"


def test_multiple_lore_collections_require_selection_and_never_merge():
    first, second = (
        standalone(),
        standalone({"name": "Second", "entries": {"0": {"key": [], "content": "Second only"}}}),
    )
    card = CharacterCardImporter().parse(json_bytes(card_document(2)), imported_at=IMPORTED_AT)
    character = replace(
        card.draft.contents[0],
        lore_collection_ids=(roots(first)[0].content_id, roots(second)[0].content_id),
    )
    draft = ContentDraft(
        contents=(character, *first.draft.contents, *second.draft.contents),
        raw_imports=(*card.draft.raw_imports, *first.draft.raw_imports, *second.draft.raw_imports),
    )
    result = export(draft, ExportTarget.CHARACTER_CARD_V2)
    assert "character_book" not in document(result)["data"]
    assert "multiple_lore_collections_require_selection" in warning_codes(result)
    result = export(
        draft, ExportTarget.CHARACTER_CARD_V2, embedded_collection_id=roots(second)[0].content_id
    )
    book = document(result)["data"]["character_book"]
    assert book["name"] == "Second" and [entry["content"] for entry in book["entries"]] == [
        "Second only"
    ]
    with pytest.raises(ContentExportError, match="invalid_lore_selection"):
        export(
            draft,
            ExportTarget.CHARACTER_CARD_V2,
            embedded_collection_id=roots(standalone())[0].content_id,
        )


def test_uid_collision_invalid_uid_and_future_reserved_uid_allocate_without_overwrite():
    imported = standalone()
    collection, entries, _ = roots(imported)
    changed = []
    for index, entry in enumerate((*entries, replace(entries[0], content_id=LoreEntryId(uuid4())))):
        extensions = json_value(entry.extensions)
        extensions[LOREBOOK_METADATA_KEY]["source_entry"]["uid"] = (9, 9, 0)[index]
        changed.append(replace(entry, extensions=extensions))
    updated_collection = replace(
        collection, lore_entry_ids=tuple(entry.content_id for entry in changed)
    )
    draft = replace(imported.draft, contents=(updated_collection, *changed))
    result = export(draft, ExportTarget.SILLYTAVERN_WORLD_INFO)
    output = document(result)["entries"]
    assert len(output) == 3
    assert [entry["uid"] for entry in output.values()] == [0, 1, 9]  # JSON keys are sorted.
    assert output["9"]["content"] == changed[0].content
    assert output["1"]["content"] == changed[1].content
    assert "source_uid_reassigned" in warning_codes(result)
    assert result == export(draft, ExportTarget.SILLYTAVERN_WORLD_INFO)
    extensions = json_value(changed[0].extensions)
    extensions[LOREBOOK_METADATA_KEY]["source_entry"]["uid"] = "not a UID"
    invalid = edit_root(draft, replace(changed[0], extensions=extensions))
    result = export(invalid, ExportTarget.SILLYTAVERN_WORLD_INFO)
    assert len(document(result)["entries"]) == 3
    assert "source_uid_reassigned" in warning_codes(result)


def test_fresh_export_local_uids_are_deterministic_and_legacy_unbound_rows_are_not_attached():
    imported = standalone()
    collection, entries, _ = roots(imported)
    stripped = tuple(replace(entry, extensions={}) for entry in entries)
    legacy = replace(
        entries[0],
        content_id=LoreEntryId(uuid4()),
        collection_id=None,
        content="Legacy must stay separate",
    )
    draft = replace(
        imported.draft, contents=(replace(collection, extensions={}), *stripped, legacy)
    )
    result = export(draft, ExportTarget.SILLYTAVERN_WORLD_INFO)
    output = document(result)["entries"]
    assert list(output) == ["0", "1"]
    assert [entry["uid"] for entry in output.values()] == [0, 1]
    assert "Legacy must stay separate" not in result.serialized_bytes.decode("utf-8")
    assert all(type(entry["uid"]) is int for entry in output.values())


def test_v3_asset_data_url_is_restored_without_reading_a_resource():
    source = card_document(3)
    source["data"]["assets"][0]["uri"] = "data:image/png;base64,AA=="
    source["data"]["assets"][0]["future_descriptor"] = {"opaque": 1}
    imported = CharacterCardImporter().parse(json_bytes(source), imported_at=IMPORTED_AT)
    output = document(export(imported.draft, ExportTarget.CHARACTER_CARD_V3))
    assert output["data"]["assets"] == source["data"]["assets"]
    asset = imported.draft.assets[0]
    extensions = json_value(asset.extensions)
    extensions["character_card_descriptor"]["uri"] = "https://example.invalid/current.png"
    edited = replace(
        imported.draft, assets=(replace(asset, extensions=extensions), *imported.draft.assets[1:])
    )
    assert (
        document(export(edited, ExportTarget.CHARACTER_CARD_V3))["data"]["assets"][0]["uri"]
        == "https://example.invalid/current.png"
    )


def test_embedded_asset_references_warn_that_json_does_not_package_resources():
    imported = preserved_card(3, container="png")
    result = export(imported.draft, ExportTarget.CHARACTER_CARD_V3)
    assert document(result)["data"]["assets"][0]["uri"] == "ccdefault:"
    assert "export_asset_reference_not_packaged" in warning_codes(result)


def test_export_is_inert_and_never_opens_or_writes_files_or_executes_external_regex(monkeypatch):
    imported = LorebookImporter().normalize_embedded(preserved_card(3))
    keys = {key for entry in roots(imported)[1] for key in entry.keywords}
    keys.update(book_document()["entries"]["0"]["key"])
    native = standalone()
    before = imported.draft.preview_hash(), native.draft.preview_hash()

    def forbidden(*args, **kwargs):
        pytest.fail("Exporter attempted an external effect")

    with monkeypatch.context() as patch:
        patch.setattr(builtins, "open", forbidden)
        patch.setattr(Path, "open", forbidden)
        patch.setattr(Path, "write_text", forbidden)
        patch.setattr(Path, "write_bytes", forbidden)
        patch.setattr(socket, "create_connection", forbidden)
        patch.setattr(subprocess, "Popen", forbidden)
        patch.setattr(urllib.request, "urlopen", forbidden)
        for name in ("compile", "search", "match", "fullmatch"):
            original = getattr(re, name)

            def guard(pattern, *args, _original=original, **kwargs):
                if isinstance(pattern, str) and pattern in keys:
                    forbidden()
                return _original(pattern, *args, **kwargs)

            patch.setattr(re, name, guard)
        card = export(
            imported.draft, ExportTarget.CHARACTER_CARD_V3, roots(imported)[2][0].content_id
        )
        world_info = export(native.draft, ExportTarget.SILLYTAVERN_WORLD_INFO)
    assert "@@dont_activate" in card.serialized_bytes.decode("utf-8")
    assert "https://example.invalid/bg.png" in card.serialized_bytes.decode("utf-8")
    assert "run this command" in world_info.serialized_bytes.decode("utf-8")
    assert before == (imported.draft.preview_hash(), native.draft.preview_hash())


@pytest.mark.parametrize(
    "mutation",
    [
        lambda c: replace(c, authored_instructions={"character_card": {"first_mes": 7}}),
        lambda c: replace(c, extensions={CARD_METADATA_KEY: {"group_only_greetings": "bad"}}),
        lambda c: replace(
            c, extensions={CARD_METADATA_KEY: {"creator_notes_multilingual": {"en": 7}}}
        ),
    ],
)
def test_exporter_validates_generated_target_before_returning_bytes(mutation):
    imported = CharacterCardImporter().parse(json_bytes(card_document(3)), imported_at=IMPORTED_AT)
    with pytest.raises(ContentExportError, match="invalid_character_card_export"):
        export(
            edit_root(imported.draft, mutation(imported.draft.contents[0])),
            ExportTarget.CHARACTER_CARD_V3,
        )


@pytest.mark.parametrize("policy", [0, "false", []])
def test_v3_policy_rejects_non_boolean_values(policy):
    with pytest.raises(ContentExportError, match="invalid_v3_export_policy"):
        V3CharacterBookOptions(policy)


def test_explicit_target_version_and_type_errors_are_clear():
    imported = standalone()
    with pytest.raises(ExportDecisionRequiredError, match="character_book_version_required"):
        export(imported.draft, ExportTarget.CHARACTER_BOOK)
    with pytest.raises(ContentExportError, match="invalid_export_request"):
        export(imported.draft, "file.json")
    with pytest.raises(ContentExportError, match="export_target_content_mismatch"):
        export(imported.draft, ExportTarget.CHARACTER_CARD_V2)
    with pytest.raises(ContentExportError, match="unexpected_v3_export_policy"):
        export(
            imported.draft,
            ExportTarget.SILLYTAVERN_WORLD_INFO,
            v3_book_options=V3CharacterBookOptions(False),
        )


def test_canonical_deletion_does_not_restore_source_examples_or_old_group():
    imported = CharacterCardImporter().parse(json_bytes(card_document(2)), imported_at=IMPORTED_AT)
    edited = replace(imported.draft.contents[0], example_dialogue=(), tags=())
    output = document(export(edit_root(imported.draft, edited), ExportTarget.CHARACTER_CARD_V2))
    assert output["data"]["mes_example"] == "" and output["data"]["tags"] == []
    native = standalone()
    edited = replace(roots(native)[1][0], group=None)
    output = document(export(edit_root(native.draft, edited), ExportTarget.SILLYTAVERN_WORLD_INFO))
    assert "group" not in output["entries"]["0"]


def test_multiple_authored_example_blocks_require_explicit_single_block_conversion():
    imported = CharacterCardImporter().parse(json_bytes(card_document(2)), imported_at=IMPORTED_AT)
    edited = replace(imported.draft.contents[0], example_dialogue=("First", "Second"))
    with pytest.raises(
        ExportDecisionRequiredError, match="example_dialogue_serialization_required"
    ):
        export(edit_root(imported.draft, edited), ExportTarget.CHARACTER_CARD_V2)


def test_st_advanced_metadata_values_are_serialized_independently_without_defaults():
    imported = standalone()
    entry = document(export(imported.draft, ExportTarget.SILLYTAVERN_WORLD_INFO))["entries"]["0"]
    source = book_document()["entries"]["0"]
    for field in (
        "probability",
        "useProbability",
        "groupOverride",
        "groupWeight",
        "useGroupScoring",
        "sticky",
        "cooldown",
        "delay",
        "vectorized",
        "excludeRecursion",
        "preventRecursion",
        "delayUntilRecursion",
        "automationId",
        "triggers",
        "ignoreBudget",
        "characterFilter",
        "scanDepth",
        "caseSensitive",
        "matchWholeWords",
        "depth",
        "role",
    ):
        assert entry[field] == source[field]
    blank = standalone({"entries": {"0": {"key": [], "content": "No metadata"}}})
    output = document(export(blank.draft, ExportTarget.SILLYTAVERN_WORLD_INFO))["entries"]["0"]
    assert (
        not {
            "position",
            "selectiveLogic",
            "useProbability",
            "probability",
            "vectorized",
            "scanDepth",
            "group",
        }
        & output.keys()
    )


def test_foreign_entry_unknowns_are_not_restored_by_collection_origin():
    imported = standalone()
    collection, entries, _ = roots(imported)
    foreign = LorebookImporter().normalize_embedded(preserved_card(3))
    mixed = replace(
        roots(foreign)[1][0], content_id=LoreEntryId(uuid4()), collection_id=collection.content_id
    )
    draft = replace(
        imported.draft,
        contents=(
            replace(collection, lore_entry_ids=(*collection.lore_entry_ids, mixed.content_id)),
            *entries,
            mixed,
        ),
        raw_imports=(*imported.draft.raw_imports, *foreign.draft.raw_imports),
    )
    result = export(draft, ExportTarget.SILLYTAVERN_WORLD_INFO)
    exported = document(result)["entries"]["2"]
    assert "future_entry" not in exported and exported["extensions"] == {}
    assert "target_format_does_not_preserve_source_extension" in warning_codes(result)


def test_dictionary_order_does_not_change_export_bytes_or_warning_order():
    imported = standalone()

    def reverse(value):
        if isinstance(value, dict):
            return {key: reverse(value[key]) for key in reversed(value)}
        if isinstance(value, list):
            return [reverse(item) for item in value]
        return value

    draft = replace(
        imported.draft,
        contents=tuple(
            replace(root, extensions=reverse(json_value(root.extensions)))
            for root in imported.draft.contents
        ),
    )
    assert export(draft, ExportTarget.SILLYTAVERN_WORLD_INFO) == export(
        imported.draft, ExportTarget.SILLYTAVERN_WORLD_INFO
    )


@pytest.mark.parametrize("activation", [{"use_regex": "false"}, {"constant": "false"}])
def test_bad_known_activation_values_fail_structural_export_validation(activation):
    imported = standalone()
    entry = roots(imported)[1][0]
    with pytest.raises(ContentExportError):
        export(
            edit_root(imported.draft, replace(entry, activation_metadata=activation)),
            ExportTarget.CHARACTER_BOOK,
            character_book_version=CharacterBookVersion.V3,
            v3_book_options=V3CharacterBookOptions(False),
        )


def test_empty_canonical_collection_can_export_v3_without_regex_decision():
    imported = standalone({"entries": {"0": {"key": [], "content": ""}}})
    result = export(
        imported.draft, ExportTarget.CHARACTER_BOOK, character_book_version=CharacterBookVersion.V3
    )
    assert document(result)["entries"] == []


def test_json_does_not_serialize_internal_content_or_runtime_structure():
    imported = LorebookImporter().normalize_embedded(preserved_card(3))
    result = export(
        imported.draft, ExportTarget.CHARACTER_CARD_V3, roots(imported)[2][0].content_id
    )
    output = document(result)
    forbidden = {
        "content_id",
        "collection_id",
        "revision",
        "provenance",
        "world_id",
        "character_id",
        "resource_reference",
        "raw_import_id",
        "memories",
        "relationships",
        "private_knowledge",
        "api_key",
        "runtime_events",
        "player_data",
        "character_state",
    }
    assert not forbidden & output.keys()
    assert not forbidden & output["data"].keys()
    for entry in output["data"]["character_book"]["entries"]:
        assert not forbidden & entry.keys()
    for root in imported.draft.contents:
        assert root.content_id.value.hex not in result.serialized_bytes.decode("utf-8")


def test_newer_source_v3_version_is_not_silently_claimed_as_preserved():
    source = card_document(3)
    source["spec_version"] = "3.1"
    imported = CharacterCardImporter().parse(json_bytes(source), imported_at=IMPORTED_AT)
    result = export(imported.draft, ExportTarget.CHARACTER_CARD_V3)
    assert document(result)["spec_version"] == "3.0"
    assert "source_schema_version_not_preserved" in warning_codes(result)


@pytest.mark.parametrize("identity", [[], "untyped", 17])
def test_export_content_identity_must_be_typed(identity):
    imported = standalone()
    with pytest.raises(ContentExportError, match="invalid_export_content_id"):
        ExportRequest(
            draft=imported.draft,
            content_id=identity,
            target_format=ExportTarget.SILLYTAVERN_WORLD_INFO,
        )


def test_conflicting_current_case_sensitivity_aliases_fail_without_guessing():
    imported = standalone()
    entry = roots(imported)[1][0]
    edited = replace(entry, activation_metadata={"caseSensitive": True, "case_sensitive": False})
    with pytest.raises(ContentExportError, match="conflicting_activation_aliases"):
        export(edit_root(imported.draft, edited), ExportTarget.SILLYTAVERN_WORLD_INFO)


def test_no_content_database_runtime_or_receipt_mutation_and_restart_retains_export(environment):
    async def run():
        env = environment
        try:
            await env.initialize()
            truth_id = KnowledgeAssertionId(env.world, uuid4())
            await env.handler.execute(
                env.command(
                    AssertWorldTruth,
                    assertion_id=truth_id,
                    subject="door",
                    predicate="state",
                    value="locked",
                )
            )
            await env.handler.execute(
                env.command(
                    FormCharacterBelief,
                    assertion_id=KnowledgeAssertionId(env.world, uuid4()),
                    character_id=env.alice,
                    subject="door",
                    predicate="state",
                    value="unlocked",
                    epistemic_status="believed",
                    valid_from=WorldTime(123),
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
            imported = LorebookImporter().normalize_embedded(preserved_card(3))
            await commit(env.database.content_repository(), imported)

            async def all_rows():
                async with env.database.engine.connect() as connection:
                    tables = (
                        (
                            await connection.execute(
                                text(
                                    "SELECT name FROM sqlite_master WHERE type='table' "
                                    "AND name NOT LIKE 'sqlite_%' ORDER BY name"
                                )
                            )
                        )
                        .scalars()
                        .all()
                    )
                    return {
                        table: (
                            await connection.execute(
                                text(f'SELECT * FROM "{table}" ORDER BY rowid')
                            )
                        ).all()
                        for table in tables
                    }

            async def loaded_draft():
                repository = env.database.content_repository()
                return ContentDraft(
                    contents=tuple(
                        [await repository.load(root.content_id) for root in imported.draft.contents]
                    ),
                    assets=tuple(
                        [
                            await repository.load_asset(asset.asset_id)
                            for asset in imported.draft.assets
                        ]
                    ),
                    raw_imports=tuple(
                        [
                            await repository.load_raw_import(raw.import_id)
                            for raw in imported.draft.raw_imports
                        ]
                    ),
                )

            before, snapshot = await all_rows(), await env.snapshot()
            draft = await loaded_draft()
            result = export(draft, ExportTarget.CHARACTER_CARD_V3, roots(imported)[2][0].content_id)
            assert await all_rows() == before and await env.snapshot() == snapshot
            assert [serialize_content(root) for root in draft.contents] == [
                serialize_content(root) for root in imported.draft.contents
            ]
            await env.restart()
            assert await all_rows() == before
            assert (
                export(
                    await loaded_draft(),
                    ExportTarget.CHARACTER_CARD_V3,
                    roots(imported)[2][0].content_id,
                )
                == result
            )
        finally:
            await env.database.close()

    asyncio.run(run())
