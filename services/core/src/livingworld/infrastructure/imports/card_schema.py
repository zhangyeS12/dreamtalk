"""Strict public-card schema for canonical conversion and export validation."""

import re
from decimal import Decimal, InvalidOperation

from livingworld.application.imports import ContentImportError, ImportWarning

CARD_METADATA_KEY = "livingworld.character_card"
V2_SPEC = "chara_card_v2"
V3_SPEC = "chara_card_v3"
V2_VERSION = "2.0"
V3_VERSION = "3.0"
_TEXTS = (
    "name",
    "description",
    "personality",
    "scenario",
    "first_mes",
    "mes_example",
    "creator_notes",
    "system_prompt",
    "post_history_instructions",
    "creator",
    "character_version",
)
_V2_FIELDS = {*_TEXTS, "alternate_greetings", "tags", "extensions", "character_book"}
_V3_FIELDS = {
    *_V2_FIELDS,
    "assets",
    "nickname",
    "creator_notes_multilingual",
    "source",
    "group_only_greetings",
    "creation_date",
    "modification_date",
}


def _object(value: object, path: str) -> dict:
    if type(value) is not dict:
        raise ContentImportError("invalid_character_card_structure", path)
    return value


def _strings(value: object, path: str) -> list[str]:
    if type(value) is not list or any(type(item) is not str for item in value):
        raise ContentImportError("invalid_character_card_structure", path)
    return value


def _validate(document: dict, warnings: list[ImportWarning]) -> tuple[str, str, dict]:
    spec = document.get("spec")
    if spec is None and all(key in document for key in _TEXTS[:6]):
        raise ContentImportError("unsupported_character_card_v1")
    if spec not in (V2_SPEC, V3_SPEC):
        raise ContentImportError("unsupported_character_card_spec", "spec")
    version = document.get("spec_version")
    if type(version) is not str:
        raise ContentImportError("invalid_character_card_structure", "spec_version")
    if spec == V2_SPEC and version != V2_VERSION:
        raise ContentImportError("unsupported_character_card_version", "spec_version")
    if spec == V3_SPEC:
        try:
            numeric_version = Decimal(version)
        except InvalidOperation:
            raise ContentImportError("unsupported_character_card_version", "spec_version") from None
        if not numeric_version.is_finite() or numeric_version < Decimal(V3_VERSION):
            raise ContentImportError("unsupported_character_card_version", "spec_version")
        if version != V3_VERSION:
            warnings.append(
                ImportWarning(
                    "character_card_newer_v3"
                    if numeric_version > Decimal(V3_VERSION)
                    else "character_card_noncanonical_v3_version",
                    "Known V3 structure imported; original version and unknown fields retained.",
                    "spec_version",
                )
            )
    data = dict(_object(document.get("data"), "data"))
    for field in _TEXTS:
        if type(data.get(field)) is not str:
            raise ContentImportError("invalid_character_card_structure", f"data.{field}")
    if not data["name"].strip():
        raise ContentImportError("character_card_name_not_representable", "data.name")
    for field in ("tags", "alternate_greetings"):
        _strings(data.get(field), f"data.{field}")
    # Only extensions has a spec-defined empty-object default among V2 fields.
    data.setdefault("extensions", {})
    _object(data["extensions"], "data.extensions")
    if "character_book" in data:
        book = _object(data["character_book"], "data.character_book")
        if type(book.get("entries")) is not list or any(
            type(entry) is not dict for entry in book["entries"]
        ):
            raise ContentImportError(
                "invalid_character_card_structure", "data.character_book.entries"
            )
        warnings.append(
            ImportWarning(
                "character_card_embedded_lore_deferred",
                "Complete embedded lore retained with card provenance; "
                "normalization deferred to C-004C.",
                "data.character_book",
            )
        )
    if spec == V3_SPEC:
        _strings(data.get("group_only_greetings"), "data.group_only_greetings")
        if "nickname" in data and type(data["nickname"]) is not str:
            raise ContentImportError("invalid_character_card_structure", "data.nickname")
        if "source" in data:
            _strings(data["source"], "data.source")
        if "creator_notes_multilingual" in data:
            multilingual = _object(
                data["creator_notes_multilingual"], "data.creator_notes_multilingual"
            )
            if any(
                re.fullmatch(r"[a-z]{2}", key) is None or type(value) is not str
                for key, value in multilingual.items()
            ):
                raise ContentImportError(
                    "invalid_character_card_structure", "data.creator_notes_multilingual"
                )
        for field in ("creation_date", "modification_date"):
            if field in data and type(data[field]) not in (int, float):
                raise ContentImportError("invalid_character_card_structure", f"data.{field}")
        if "assets" in data:
            if type(data["assets"]) is not list:
                raise ContentImportError("invalid_character_card_structure", "data.assets")
            for index, asset in enumerate(data["assets"]):
                _object(asset, f"data.assets[{index}]")
                if any(type(asset.get(key)) is not str for key in ("type", "uri", "name", "ext")):
                    raise ContentImportError(
                        "invalid_character_card_structure", f"data.assets[{index}]"
                    )
                extension = asset["ext"]
                if (
                    not extension
                    or extension != extension.lower()
                    or any(char in extension for char in ".\\/\0")
                    or any(char.isspace() for char in extension)
                ):
                    raise ContentImportError(
                        "invalid_character_card_asset_extension", f"data.assets[{index}].ext"
                    )
            for kind in ("icon", "background"):
                matching = [asset for asset in data["assets"] if asset["type"] == kind]
                mains = sum(asset["name"] == "main" for asset in matching)
                if len(matching) > 1 and ((kind == "icon" and mains != 1) or mains > 1):
                    raise ContentImportError("ambiguous_character_card_main_asset", "data.assets")
    return spec, version, data
