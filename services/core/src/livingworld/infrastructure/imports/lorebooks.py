"""Independent World Info / CharacterBook normalization. All triggers stay inert."""

from dataclasses import asdict, dataclass, replace
from datetime import datetime
from hashlib import sha256
from math import isfinite
from uuid import uuid4

from livingworld.application.content import ContentDraft, RawImportEnvelope
from livingworld.application.imports import (
    IMPORT_METADATA_KEY,
    LOREBOOK_METADATA_KEY,
    ContentImportError,
    ImportDraft,
    ImportWarning,
)
from livingworld.domain.content.identifiers import LoreCollectionId, LoreEntryId, RawImportId
from livingworld.domain.content.models import (
    CharacterDefinition,
    ContentProvenance,
    ContentSourceKind,
    LoreCollection,
    LoreEntry,
)
from livingworld.domain.content.serialization import json_value
from livingworld.infrastructure.imports.character_cards import CARD_METADATA_KEY, V2_SPEC, V3_SPEC
from livingworld.infrastructure.imports.json_input import read_json_object

# Reviewed public enum declarations, not a runtime scanner or placement algorithm.
_SELECTIVE_LOGIC = {0: "AND_ANY", 1: "NOT_ALL", 2: "NOT_ANY", 3: "AND_ALL"}
_ST_POSITIONS = {
    0: "before_char",
    1: "after_char",
    2: "before_author_note",
    3: "after_author_note",
    4: "at_depth",
    5: "before_examples",
    6: "after_examples",
    7: "outlet",
}
_BOOK_FIELDS = {
    "name",
    "description",
    "scan_depth",
    "token_budget",
    "recursive_scanning",
    "extensions",
    "entries",
}
_CARD_ENTRY_FIELDS = {
    "keys",
    "secondary_keys",
    "content",
    "extensions",
    "enabled",
    "insertion_order",
    "case_sensitive",
    "name",
    "priority",
    "id",
    "comment",
    "selective",
    "constant",
    "position",
    "use_regex",
}
_ST_BOOLEANS = {
    "constant",
    "vectorized",
    "selective",
    "disable",
    "useProbability",
    "groupOverride",
    "excludeRecursion",
    "preventRecursion",
    "ignoreBudget",
    "addMemo",
    "matchPersonaDescription",
    "matchCharacterDescription",
    "matchCharacterPersonality",
    "matchCharacterDepthPrompt",
    "matchScenario",
    "matchCreatorNotes",
}
_ST_NULLABLE_BOOLEANS = {"caseSensitive", "matchWholeWords", "useGroupScoring"}
_ST_TEXTS = {"comment", "group", "automationId", "outletName"}
_ST_NULLABLE_COUNTS = {"scanDepth", "sticky", "cooldown", "delay"}
_ST_ENTRY_FIELDS = {
    "uid",
    "key",
    "keysecondary",
    "content",
    "order",
    "position",
    "selectiveLogic",
    "probability",
    "depth",
    "groupWeight",
    "delayUntilRecursion",
    "role",
    "displayIndex",
    "triggers",
    "characterFilter",
    "extensions",
    *_ST_BOOLEANS,
    *_ST_NULLABLE_BOOLEANS,
    *_ST_TEXTS,
    *_ST_NULLABLE_COUNTS,
}


@dataclass(frozen=True, slots=True)
class LorebookLimits:
    max_json_bytes: int = 4 * 1024 * 1024
    max_json_depth: int = 64
    max_entries: int = 10000

    def __post_init__(self) -> None:
        if any(type(value) is not int or value <= 0 for value in asdict(self).values()):
            raise ValueError("Lorebook parser limits must be positive integers")


def _error(path: str) -> None:
    raise ContentImportError("invalid_lorebook_structure", path)


def _typed(value: object, kind: type, path: str) -> None:
    if type(value) is not kind:
        _error(path)


def _strings(value: object, path: str) -> list[str]:
    _typed(value, list, path)
    if any(type(item) is not str for item in value):
        _error(path)
    return value


def _number(
    value: object,
    path: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
    integral: bool = False,
) -> None:
    if type(value) not in (int, float) or (type(value) is float and not isfinite(value)):
        _error(path)
    if (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
        raise ContentImportError("invalid_lorebook_numeric_range", path)
    if integral and type(value) is float and not value.is_integer():
        raise ContentImportError("invalid_lorebook_numeric_range", path)


def _warn(warnings: list[ImportWarning], code: str, path: str, message: str) -> None:
    warnings.append(ImportWarning(code, message, path))


def _book(book: dict, *, native: bool, limits: LorebookLimits) -> list[tuple[str, dict]]:
    for name in ("name", "description"):
        if name in book:
            _typed(book[name], str, f"book.{name}")
    if "extensions" in book:
        _typed(book["extensions"], dict, "book.extensions")
    for name in ("scan_depth", "token_budget"):
        if name in book:
            _number(book[name], f"book.{name}", minimum=0)
    if "recursive_scanning" in book:
        _typed(book["recursive_scanning"], bool, "book.recursive_scanning")
    entries = book.get("entries")
    _typed(entries, dict if native else list, "book.entries")
    if len(entries) > limits.max_entries:
        raise ContentImportError("lorebook_entry_count_limit", "book.entries")
    result = list(entries.items()) if native else [(str(i), item) for i, item in enumerate(entries)]
    for key, entry in result:
        _typed(entry, dict, f"book.entries[{key}]")
    return result


def _validate_entry(entry: dict, path: str, *, native: bool, v3: bool) -> None:
    _typed(entry.get("content"), str, f"{path}.content")
    _strings(entry.get("key" if native else "keys"), f"{path}.keys")
    if "extensions" in entry:
        _typed(entry["extensions"], dict, f"{path}.extensions")
    secondary = "keysecondary" if native else "secondary_keys"
    if secondary in entry and not (v3 and type(entry[secondary]) is str):
        _strings(entry[secondary], f"{path}.{secondary}")
    if not native:
        _typed(entry.get("enabled"), bool, f"{path}.enabled")
        _number(entry.get("insertion_order"), f"{path}.insertion_order")
        for name in ("case_sensitive", "selective", "constant"):
            if name in entry:
                _typed(entry.get(name), bool, f"{path}.{name}")
        if v3:
            _typed(entry.get("use_regex"), bool, f"{path}.use_regex")
        for name in ("name", "comment"):
            if name in entry:
                _typed(entry[name], str, f"{path}.{name}")
        if "priority" in entry:
            _number(entry["priority"], f"{path}.priority")
        if "id" in entry:
            if v3 and type(entry["id"]) is str:
                pass
            else:
                _number(entry["id"], f"{path}.id")
    else:
        for name in _ST_BOOLEANS:
            if name in entry:
                _typed(entry[name], bool, f"{path}.{name}")
        for name in _ST_NULLABLE_BOOLEANS:
            if name in entry and entry[name] is not None:
                _typed(entry[name], bool, f"{path}.{name}")
        for name in _ST_TEXTS:
            if name in entry:
                _typed(entry[name], str, f"{path}.{name}")
        for name in ("uid", "depth", "displayIndex"):
            if name in entry:
                _number(entry[name], f"{path}.{name}", minimum=0, integral=True)
        for name in _ST_NULLABLE_COUNTS:
            if name in entry and entry[name] is not None:
                _number(entry[name], f"{path}.{name}", minimum=0, integral=True)
        if "delayUntilRecursion" in entry and type(entry["delayUntilRecursion"]) is not bool:
            _number(
                entry["delayUntilRecursion"],
                f"{path}.delayUntilRecursion",
                minimum=0,
                integral=True,
            )
        for name in ("order", "role", "selectiveLogic"):
            if name in entry:
                _number(entry[name], f"{path}.{name}")
        if "probability" in entry:
            _number(entry["probability"], f"{path}.probability", minimum=0, maximum=100)
        if "groupWeight" in entry:
            _number(entry["groupWeight"], f"{path}.groupWeight", minimum=0)
        if "triggers" in entry:
            _strings(entry["triggers"], f"{path}.triggers")
        if "characterFilter" in entry:
            _typed(entry["characterFilter"], dict, f"{path}.characterFilter")
            for name in ("names", "tags"):
                if name in entry["characterFilter"]:
                    _strings(entry["characterFilter"][name], f"{path}.characterFilter.{name}")
            if "isExclude" in entry["characterFilter"]:
                _typed(
                    entry["characterFilter"]["isExclude"], bool, f"{path}.characterFilter.isExclude"
                )
    if "position" in entry and type(entry["position"]) not in (int, float, str):
        _error(f"{path}.position")


def _keys(values: list[str], path: str, warnings: list[ImportWarning]) -> tuple[str, ...]:
    safe = tuple(value for value in values if value.strip())
    if len(safe) != len(values):
        _warn(
            warnings,
            "lore_blank_keys_omitted_from_canonical",
            path,
            "Blank keys omitted only from canonical keys; complete source values retained.",
        )
    return safe


def _integer(value: int | float, path: str, warnings: list[ImportWarning]) -> int:
    if type(value) is int or value.is_integer():
        return int(value)
    _warn(
        warnings,
        "lore_fractional_order_preserved",
        path,
        "Fractional source order/priority retained; canonical integer field left at its default.",
    )
    return 0


def _entry(
    entry: dict,
    key: str,
    collection_id: LoreCollectionId,
    provenance: ContentProvenance,
    warnings: list[ImportWarning],
    *,
    native: bool,
    v3: bool,
) -> LoreEntry | None:
    path = f"book.entries[{key}]"
    _validate_entry(entry, path, native=native, v3=v3)
    secondary_name = "keysecondary" if native else "secondary_keys"
    secondary = entry.get(secondary_name, [])
    if type(secondary) is str:
        _warn(
            warnings,
            "lore_secondary_keys_ambiguous_string_preserved",
            f"{path}.{secondary_name}",
            "Ambiguous secondary-key string retained exactly; not split or interpreted.",
        )
        secondary = []
    if not entry["content"].strip():
        identity = entry.get("uid" if native else "id", key)
        _warn(
            warnings,
            "lore_entry_empty_content_omitted_from_canonical",
            path,
            f"Source entry identity {identity!r} has blank content; entire source entry retained. "
            "No canonical LoreEntry created; commit remains allowed.",
        )
        return None
    primary = _keys(entry["key" if native else "keys"], f"{path}.keys", warnings)
    secondary = _keys(secondary, f"{path}.{secondary_name}", warnings)
    if secondary and not primary:
        _warn(
            warnings,
            "lore_secondary_keys_without_primary_preserved",
            f"{path}.{secondary_name}",
            "Secondary keys retained in source data; canonical keys require a nonblank primary.",
        )
        secondary = ()
    known = (
        _ST_ENTRY_FIELDS
        if native
        else (_CARD_ENTRY_FIELDS if v3 else _CARD_ENTRY_FIELDS - {"use_regex"})
    )
    unknown = {name: value for name, value in entry.items() if name not in known}
    if unknown:
        _warn(
            warnings,
            "lore_unknown_entry_fields_preserved",
            path,
            "Unknown entry fields retained as inert compatibility data.",
        )
    activation = {}
    activation_names = (
        (
            {
                *_ST_BOOLEANS,
                *_ST_NULLABLE_BOOLEANS,
                *_ST_NULLABLE_COUNTS,
                "probability",
                "group",
                "groupWeight",
                "delayUntilRecursion",
                "triggers",
                "characterFilter",
                "automationId",
            }
            - {"disable"}
        )
        if native
        else (
            {"constant", "selective", "case_sensitive", "use_regex"}
            if v3
            else {"constant", "selective", "case_sensitive"}
        )
    )
    activation.update({name: entry[name] for name in activation_names if name in entry})
    if native and "selectiveLogic" in entry:
        logic = entry["selectiveLogic"]
        symbol = _SELECTIVE_LOGIC.get(logic)
        if symbol is not None:
            activation["selective_logic"] = symbol
        else:
            _warn(
                warnings,
                "lore_unknown_selective_logic_preserved",
                f"{path}.selectiveLogic",
                "Unknown selective logic retained without guessing a mode.",
            )
    insertion = {name: entry[name] for name in ("depth", "role", "outletName") if name in entry}
    if "position" in entry:
        position = entry["position"]
        symbol = (
            _ST_POSITIONS.get(position)
            if native
            else (position if position in ("before_char", "after_char") else None)
        )
        if symbol is not None:
            insertion["position"] = symbol
        else:
            _warn(
                warnings,
                "lore_unknown_position_preserved",
                f"{path}.position",
                "Unknown position retained; no automatic canonical placement selected.",
            )
    if activation or insertion or any(value.startswith("/") for value in (*primary, *secondary)):
        _warn(
            warnings,
            "lore_activation_metadata_preserved_inert",
            path,
            "Activation, placement, regex, vector, timing and automation data are not executed.",
        )
    order_name = "order" if native else "insertion_order"
    group = entry.get("group") if native else None
    if group and not group.strip():
        _warn(
            warnings,
            "lore_blank_group_preserved",
            f"{path}.group",
            "Blank group omitted only from canonical group; original value retained in metadata.",
        )
    return LoreEntry(
        content_id=LoreEntryId(uuid4()),
        collection_id=collection_id,
        content=entry["content"],
        title=entry.get("comment", "") if native else entry.get("name", ""),
        comment=entry.get("comment", ""),
        keywords=primary,
        secondary_keywords=secondary,
        enabled=not entry.get("disable", False) if native else entry["enabled"],
        order=_integer(
            entry.get(order_name, 100 if native else 0), f"{path}.{order_name}", warnings
        ),
        priority=0 if native else _integer(entry.get("priority", 0), f"{path}.priority", warnings),
        group=group if group is not None and group.strip() else None,
        activation_metadata=activation,
        insertion_metadata=insertion,
        provenance=provenance,
        extensions={
            LOREBOOK_METADATA_KEY: {
                "source_entry": entry,
                "source_map_key": key if native else None,
                "source_ordinal": None if native else int(key),
                "unknown_fields": unknown,
                "external_extensions": entry.get("extensions", {}),
            }
        },
    )


def _normalize(
    book: dict, provenance: ContentProvenance, limits: LorebookLimits, *, native: bool, v3: bool
) -> tuple[LoreCollection, tuple[LoreEntry, ...]]:
    external = _book(book, native=native, limits=limits)
    collection_id = LoreCollectionId(uuid4())
    warnings = []
    entries = tuple(
        result
        for key, entry in external
        if (result := _entry(entry, key, collection_id, provenance, warnings, native=native, v3=v3))
        is not None
    )
    unknown = {name: value for name, value in book.items() if name not in _BOOK_FIELDS}
    if unknown:
        _warn(
            warnings,
            "lore_unknown_book_fields_preserved",
            "book",
            "Unknown book fields retained as inert compatibility data.",
        )
    collection = LoreCollection(
        content_id=collection_id,
        name=book.get("name", ""),
        description=book.get("description", ""),
        lore_entry_ids=tuple(entry.content_id for entry in entries),
        provenance=provenance,
        activation_metadata={
            name: book[name]
            for name in ("scan_depth", "token_budget", "recursive_scanning")
            if name in book
        },
        extensions={
            LOREBOOK_METADATA_KEY: {
                "source_book": book,
                "source_entry_count": len(external),
                "unknown_fields": unknown,
                "external_extensions": book.get("extensions", {}),
                "origin": "standalone_world_info" if native else "embedded_character_book",
            },
            IMPORT_METADATA_KEY: {"warnings": [asdict(warning) for warning in warnings]},
        },
    )
    return collection, entries


class LorebookImporter:
    def __init__(self, limits: LorebookLimits | None = None) -> None:
        self._limits = limits if limits is not None else LorebookLimits()

    def parse(
        self, payload: bytes, *, imported_at: datetime, original_name: str | None = None
    ) -> ImportDraft:
        if type(payload) is not bytes:
            raise ContentImportError("invalid_lorebook_input")
        book = read_json_object(
            payload,
            max_bytes=self._limits.max_json_bytes,
            max_depth=self._limits.max_json_depth,
            prefix="lorebook",
            root_path="book",
        )
        raw_id = RawImportId(uuid4())
        provenance = ContentProvenance(
            source_kind=ContentSourceKind.IMPORT,
            source_format="sillytavern_world_info",
            original_name=original_name,
            imported_at=imported_at,
            content_hash=sha256(payload).hexdigest(),
            raw_import_id=raw_id,
        )
        collection, entries = _normalize(book, provenance, self._limits, native=True, v3=False)
        raw = RawImportEnvelope(
            import_id=raw_id,
            provenance=provenance,
            original_payload=payload,
            unknown_extensions={LOREBOOK_METADATA_KEY: {"source_book": book}},
        )
        return ImportDraft(ContentDraft(contents=(collection, *entries), raw_imports=(raw,)))

    def normalize_embedded(self, imported: ImportDraft) -> ImportDraft:
        """Consume C-004B's preserved representation before its preview/commit; no PNG reparse."""
        if not isinstance(imported, ImportDraft):
            raise ContentImportError("invalid_embedded_lore_draft")
        characters = [
            root for root in imported.draft.contents if isinstance(root, CharacterDefinition)
        ]
        if len(characters) != 1:
            raise ContentImportError("invalid_embedded_lore_draft")
        character = characters[0]
        compatibility = character.extensions.get(CARD_METADATA_KEY, {})
        if "character_book" not in compatibility:
            return imported
        if character.lore_collection_ids:
            raise ContentImportError("embedded_lore_already_normalized")
        if character.provenance.source_format not in (V2_SPEC, V3_SPEC):
            raise ContentImportError("unsupported_embedded_lore_source")
        book = json_value(compatibility["character_book"])
        collection, entries = _normalize(
            book,
            character.provenance,
            self._limits,
            native=False,
            v3=character.provenance.source_format == V3_SPEC,
        )
        extensions = json_value(character.extensions)
        extensions[IMPORT_METADATA_KEY]["warnings"] = [
            item
            for item in extensions[IMPORT_METADATA_KEY]["warnings"]
            if item["code"] != "character_card_embedded_lore_deferred"
        ]
        character = replace(
            character, lore_collection_ids=(collection.content_id,), extensions=extensions
        )
        return ImportDraft(
            replace(
                imported.draft,
                contents=tuple(
                    character if root.content_id == character.content_id else root
                    for root in imported.draft.contents
                )
                + (collection, *entries),
            )
        )
