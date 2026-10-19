"""Loss-aware input normalization; strict output validation remains in card_schema."""

from copy import deepcopy
from math import isfinite

from livingworld.application.imports import ContentImportError, ImportWarning
from livingworld.infrastructure.imports.card_schema import (
    _TEXTS,
    V2_SPEC,
    V3_SPEC,
)


def normalize_card(document: dict, warnings: list[ImportWarning]) -> tuple[dict, dict]:
    """Keep exact source bytes elsewhere; record every input-only adjustment for review."""
    result = dict(document)
    if type(document.get("data")) is dict:
        result["data"] = dict(document["data"])
    original_fields: dict = {}

    def changed(path: str, original: object, code: str = "character_card_field_normalized") -> None:
        original_fields[path] = original
        warnings.append(ImportWarning(code, "Input normalized; original source retained.", path))

    spec = result.get("spec")
    origin = "standard"
    if spec is None:
        if "char_name" in result and "name" not in result:
            origin = "pygmalion"
            mapping = {
                "name": "char_name",
                "description": "char_persona",
                "first_mes": "char_greeting",
                "mes_example": "example_dialogue",
                "scenario": "world_scenario",
            }
            data = {key: result.get(source) for key, source in mapping.items()}
            for key in ("creator", "tags", "creator_notes", "creatorcomment"):
                if key in result:
                    data[key] = result[key]
        elif "name" in result:
            origin = "v1"
            data = dict(result)
        else:
            raise ContentImportError("unsupported_character_card_spec", "spec")
        result = {"spec": V2_SPEC, "spec_version": "2.0", "data": data}
        changed("spec", document.get("spec"), "character_card_legacy_converted")
    if result.get("spec") not in (V2_SPEC, V3_SPEC):
        raise ContentImportError("unsupported_character_card_spec", "spec")
    data = result.get("data")
    if data is None and type(result.get("name")) is str:
        data = {
            key: value
            for key, value in result.items()
            if key not in ("spec", "spec_version", "data")
        }
        result["data"] = data
        changed("data", document.get("data"))
    if type(data) is not dict:
        raise ContentImportError("invalid_character_card_structure", "data")
    version = result.get("spec_version")
    expected = "3.0" if result["spec"] == V3_SPEC else "2.0"
    if (
        version is None
        or type(version) in (int, float)
        or (result["spec"] == V2_SPEC and version == "2")
    ):
        replacement = expected if version is None else str(version)
        if replacement in ("2", "3"):
            replacement += ".0"
        changed("spec_version", version)
        result["spec_version"] = replacement
    for key in (*_TEXTS[:6], "tags", "alternate_greetings"):
        if data.get(key) is None and key in document:
            changed(f"data.{key}", data.get(key))
            data[key] = deepcopy(document[key])
    if type(data.get("name")) is not str or not data["name"].strip():
        raise ContentImportError("character_card_name_not_representable", "data.name")
    if "creator_notes" not in data and type(data.get("creatorcomment")) is str:
        data["creator_notes"] = data["creatorcomment"]
        changed("data.creator_notes", None)
    for key in _TEXTS:
        if key == "name":
            continue
        value = data.get(key)
        if value is None:
            changed(f"data.{key}", value)
            data[key] = ""
        elif type(value) is not str:
            # Authored character text is never stringified or silently discarded.
            if key not in ("creator", "character_version"):
                raise ContentImportError("invalid_character_card_structure", f"data.{key}")
            changed(f"data.{key}", value, "character_card_optional_field_preserved")
            data[key] = str(value) if type(value) in (int, float, bool) else ""
    arrays = ("tags", "alternate_greetings") + (
        ("group_only_greetings", "source") if result["spec"] == V3_SPEC else ()
    )
    for key in arrays:
        if key == "source" and key not in data:
            continue
        value = data.get(key)
        if type(value) is list and all(type(item) is str for item in value):
            continue
        changed(f"data.{key}", value)
        if type(value) is str:
            data[key] = (
                [item.strip() for item in value.split(",") if item.strip()]
                if key == "tags"
                else [value]
            )
        elif value is None:
            data[key] = []
        elif key in ("tags", "source"):
            data[key] = [item for item in value if type(item) is str] if type(value) is list else []
        else:
            raise ContentImportError("invalid_character_card_structure", f"data.{key}")
    if type(data.get("extensions")) is not dict:
        changed("data.extensions", data.get("extensions"))
        data["extensions"] = {}
    if "character_book" in data and data["character_book"] is None:
        changed("data.character_book", None, "character_card_empty_book_normalized")
        del data["character_book"]
    # Books are normalized separately, so malformed attachments cannot reject the card.
    book = data.pop("character_book", None)
    if result["spec"] == V3_SPEC:
        for key in ("nickname", "creator_notes_multilingual", "creation_date", "modification_date"):
            if key not in data:
                continue
            value = data[key]
            valid = (
                type(value) is str
                if key == "nickname"
                else (
                    type(value) is dict
                    and all(
                        type(k) is str
                        and len(k) == 2
                        and k.isascii()
                        and k.islower()
                        and k.isalpha()
                        and type(v) is str
                        for k, v in value.items()
                    )
                    if key == "creator_notes_multilingual"
                    else type(value) in (int, float) and (type(value) is int or isfinite(value))
                )
            )
            if not valid:
                changed(f"data.{key}", value, "character_card_optional_field_preserved")
                del data[key]
        if "assets" in data:
            source_assets = data["assets"]
            usable = []
            source_indices = []
            asset_candidates = source_assets if type(source_assets) is list else []
            if len(asset_candidates) > 10000:
                changed("data.assets", source_assets, "character_card_asset_preserved_only")
                asset_candidates = []
            for index, asset in enumerate(asset_candidates):
                if type(asset) is not dict or any(
                    type(asset.get(k)) is not str for k in ("type", "uri", "name", "ext")
                ):
                    changed(f"data.assets[{index}]", asset, "character_card_asset_preserved_only")
                    continue
                ext = asset["ext"].lower().lstrip(".")
                if not ext or any(c in ext for c in "./\\\0") or any(c.isspace() for c in ext):
                    changed(f"data.assets[{index}]", asset, "character_card_asset_preserved_only")
                    continue
                if ext != asset["ext"]:
                    changed(f"data.assets[{index}].ext", asset["ext"])
                usable.append({**asset, "ext": ext})
                source_indices.append(index)
            for kind in ("icon", "background"):
                matching = [a for a in usable if a["type"] == kind]
                mains = sum(a["name"] == "main" for a in matching)
                if len(matching) > 1 and ((kind == "icon" and mains != 1) or mains > 1):
                    changed("data.assets", source_assets, "character_card_asset_preserved_only")
                    kept = [
                        (a, i)
                        for a, i in zip(usable, source_indices, strict=True)
                        if a["type"] != kind
                    ]
                    usable = [a for a, _ in kept]
                    source_indices = [i for _, i in kept]
            if type(source_assets) is not list:
                changed("data.assets", source_assets, "character_card_asset_preserved_only")
            data["assets"] = usable
            original_fields["asset_source_indices"] = source_indices
    return result, {
        "origin": origin,
        "original_spec": document.get("spec"),
        "original_version": document.get("spec_version"),
        "original_fields": original_fields,
        **({"source_book": book} if book is not None else {}),
        **(
            {"source_assets": document["data"]["assets"]}
            if type(document.get("data")) is dict and "assets" in document["data"]
            else {}
        ),
    }
