"""Public-spec CCv2/CCv3 adapter, implemented independently of SillyTavern."""

import base64
import binascii
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from uuid import uuid4

from livingworld.application.content import ContentDraft, RawImportEnvelope
from livingworld.application.imports import (
    IMPORT_METADATA_KEY,
    ContentImportError,
    ImportDraft,
    ImportWarning,
)
from livingworld.domain.content.identifiers import (
    CharacterDefinitionId,
    ContentAssetId,
    RawImportId,
)
from livingworld.domain.content.models import (
    AssetReference,
    CharacterDefinition,
    ContentAsset,
    ContentProvenance,
    ContentSourceKind,
)
from livingworld.domain.content.serialization import stable_json
from livingworld.domain.errors import DomainInvariantError
from livingworld.infrastructure.imports.png import PNG_SIGNATURE, read_png

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


@dataclass(frozen=True, slots=True)
class CharacterCardLimits:
    """Local parser resource policy, configurable without changing content semantics."""

    max_input_bytes: int = 32 * 1024 * 1024
    max_json_bytes: int = 4 * 1024 * 1024
    max_json_depth: int = 64
    max_png_chunks: int = 10000

    def __post_init__(self) -> None:
        if any(type(value) is not int or value <= 0 for value in asdict(self).values()):
            raise ValueError("Character card parser limits must be positive integers")


def _object(value: object, path: str) -> dict:
    if type(value) is not dict:
        raise ContentImportError("invalid_character_card_structure", path)
    return value


def _strings(value: object, path: str) -> list[str]:
    if type(value) is not list or any(type(item) is not str for item in value):
        raise ContentImportError("invalid_character_card_structure", path)
    return value


def _unique(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            # Imported keys are untrusted; no key value appears in the error.
            raise ContentImportError("duplicate_character_card_json_key")
        result[key] = value
    return result


def _json(payload: bytes, limits: CharacterCardLimits) -> dict:
    if len(payload) > limits.max_json_bytes:
        raise ContentImportError("character_card_json_size_limit")
    try:
        text = payload.decode("utf-8")
        # Bound nesting before the recursive JSON decoder (including unknown fields).
        depth = 0
        quoted = escaped = False
        for char in text:
            if quoted:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    quoted = False
            elif char == '"':
                quoted = True
            elif char in "[{":
                depth += 1
                if depth > limits.max_json_depth:
                    raise ContentImportError("character_card_json_depth_limit")
            elif char in "]}":
                depth -= 1
        document = json.loads(text, object_pairs_hook=_unique)
        stable_json(document)  # Finite JSON, UTF-8 strings, no escaped lone surrogates.
    except ContentImportError:
        raise
    except (ValueError, UnicodeError, RecursionError, DomainInvariantError):
        raise ContentImportError("invalid_character_card_json") from None
    return _object(document, "card")


def _base64(payload: bytes, limits: CharacterCardLimits) -> dict:
    if len(payload) > 4 * ((limits.max_json_bytes + 2) // 3):
        raise ContentImportError("character_card_json_size_limit")
    try:
        decoded = base64.b64decode(payload, validate=True)
        if base64.b64encode(decoded) != payload:
            raise ValueError("Noncanonical base64 padding")
    except (ValueError, binascii.Error):
        raise ContentImportError("invalid_character_card_base64") from None
    return _json(decoded, limits)


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


class CharacterCardImporter:
    def __init__(self, limits: CharacterCardLimits | None = None) -> None:
        self.limits = limits if limits is not None else CharacterCardLimits()

    def parse(
        self, payload: bytes, *, imported_at: datetime, original_name: str | None = None
    ) -> ImportDraft:
        if type(payload) is not bytes:
            raise ContentImportError("character_card_requires_bytes")
        if len(payload) > self.limits.max_input_bytes:
            raise ContentImportError("character_card_input_size_limit")
        warnings: list[ImportWarning] = []
        container = "json"
        selected = None
        chunk_counts = {}
        embedded_assets = ()
        if payload.startswith(PNG_SIGNATURE):
            metadata = read_png(payload, max_chunks=self.limits.max_png_chunks)
            container = metadata.container
            embedded_assets = metadata.embedded_assets
            candidates = {}
            for name, encoded in metadata.card_chunks:
                chunk_counts[name] = chunk_counts.get(name, 0) + 1
                if name in candidates and candidates[name][0] != encoded:
                    raise ContentImportError("ambiguous_character_card_chunks", name)
                # Validate even the nonselected payload: corruption never becomes a fallback.
                candidates[name] = (encoded, _base64(encoded, self.limits))
            selected = "ccv3" if "ccv3" in candidates else "chara"
            if selected not in candidates:
                raise ContentImportError("missing_character_card_chunk")
            document = candidates[selected][1]
            if selected == "ccv3" and document.get("spec") != V3_SPEC:
                raise ContentImportError("invalid_ccv3_payload_identity")
            if len(candidates) == 2:
                warnings.append(
                    ImportWarning(
                        "character_card_chara_shadowed",
                        "ccv3 selected; chara retained only in raw container.",
                        "chara",
                    )
                )
            if any(value > 1 for value in chunk_counts.values()):
                warnings.append(
                    ImportWarning(
                        "character_card_identical_chunks",
                        "Identical duplicate card chunks retained in raw container.",
                    )
                )
        elif payload.startswith(b"\x89PNG"):
            raise ContentImportError("invalid_png_signature")
        elif payload.startswith(b"PK\x03\x04"):
            raise ContentImportError("unsupported_character_card_charx")
        else:
            document = _json(payload, self.limits)
        spec, version, data = _validate(document, warnings)
        unknown_top = {
            key: value
            for key, value in document.items()
            if key not in ("spec", "spec_version", "data")
        }
        unknown_data = {
            key: value
            for key, value in data.items()
            if key not in (_V3_FIELDS if spec == V3_SPEC else _V2_FIELDS)
        }
        if unknown_top or unknown_data:
            warnings.append(
                ImportWarning(
                    "character_card_unknown_fields",
                    "Unknown fields preserved without interpretation.",
                )
            )
        if data["extensions"]:
            warnings.append(
                ImportWarning(
                    "character_card_opaque_extensions",
                    "External extensions preserved as inert compatibility data.",
                    "data.extensions",
                )
            )
        if embedded_assets:
            warnings.append(
                ImportWarning(
                    "character_card_embedded_assets_deferred",
                    "Legacy embedded asset chunks retained only in raw container; "
                    "extraction deferred.",
                )
            )
        tags = tuple(tag for tag in data["tags"] if tag.strip())
        if len(tags) != len(data["tags"]):
            warnings.append(
                ImportWarning(
                    "character_card_blank_tags_omitted_from_canonical",
                    "Blank tags omitted only from canonical tags; "
                    "complete original tags remain in source compatibility data.",
                    "data.tags",
                )
            )
        raw_id = RawImportId(uuid4())
        provenance = ContentProvenance(
            source_kind=ContentSourceKind.IMPORT,
            source_format=spec,
            source_format_version=version,
            original_name=original_name,
            imported_at=imported_at,
            content_hash=sha256(payload).hexdigest(),
            raw_import_id=raw_id,
        )
        assets = []
        if spec == V3_SPEC:
            descriptors = data.get(
                "assets", [{"type": "icon", "uri": "ccdefault:", "name": "main", "ext": "png"}]
            )
            for index, descriptor in enumerate(descriptors):
                pointer = f"/data/assets/{index}" if "assets" in data else "spec-default-assets/0"
                kind, uri = descriptor["type"], descriptor["uri"]
                if kind not in ("icon", "background", "user_icon", "emotion"):
                    warnings.append(
                        ImportWarning(
                            "character_card_asset_type_deferred",
                            "Asset type retained without runtime behavior.",
                            pointer,
                        )
                    )
                if (
                    not uri.startswith(("https://", "http://", "data:", "embeded://", "__asset:"))
                    and uri != "ccdefault:"
                ):
                    warnings.append(
                        ImportWarning(
                            "character_card_asset_uri_deferred",
                            "Unknown URI retained as reference only; never accessed.",
                            pointer,
                        )
                    )
                container_image = uri == "ccdefault:" and kind == "icon" and container != "json"
                reference = f"raw-import:{raw_id.value.hex}#" + (
                    "container-image" if container_image else pointer
                )
                safe_descriptor = dict(descriptor)
                if uri.startswith("data:"):
                    safe_descriptor["uri"] = {"raw_pointer": pointer + "/uri"}
                assets.append(
                    ContentAsset(
                        asset_id=ContentAssetId(uuid4()),
                        media_type="image/png" if container_image else "application/octet-stream",
                        resource_reference=reference,
                        extensions={
                            "character_card_descriptor": safe_descriptor,
                            "raw_import_id": raw_id.value.hex,
                            "materialized": False,
                        },
                    )
                )
            if descriptors:
                warnings.append(
                    ImportWarning(
                        "character_card_assets_reference_only",
                        "Asset descriptors retained; "
                        "fetching, decoding and materialization are deferred.",
                        "data.assets",
                    )
                )
        compatibility = {
            "original_tags": data["tags"],
            "creator": data["creator"],
            "character_version": data["character_version"],
            "external_extensions": data["extensions"],
            "unknown_top_level": unknown_top,
            "unknown_data": unknown_data,
            **{
                field: data[field]
                for field in (
                    "character_book",
                    "nickname",
                    "creator_notes_multilingual",
                    "source",
                    "group_only_greetings",
                    "creation_date",
                    "modification_date",
                )
                if field in data
            },
        }
        character = CharacterDefinition(
            content_id=CharacterDefinitionId(uuid4()),
            display_name=data["name"],
            description=data["description"],
            personality=data["personality"],
            scenario=data["scenario"],
            creator_notes=data["creator_notes"],
            example_dialogue=(data["mes_example"],) if data["mes_example"].strip() else (),
            tags=tags,
            provenance=provenance,
            authored_instructions={
                "character_card": {
                    field: data[field]
                    for field in (
                        "system_prompt",
                        "post_history_instructions",
                        "first_mes",
                        "alternate_greetings",
                        "mes_example",
                    )
                }
            },
            assets=tuple(
                AssetReference(
                    asset_id=asset.asset_id,
                    role=asset.extensions["character_card_descriptor"]["type"]
                    if asset.extensions["character_card_descriptor"]["type"].strip()
                    else "character-card-asset",
                )
                for asset in assets
            ),
            extensions={
                CARD_METADATA_KEY: compatibility,
                IMPORT_METADATA_KEY: {
                    "container": container,
                    "selected_chunk": selected,
                    "card_chunk_counts": chunk_counts,
                    "embedded_asset_chunks": embedded_assets,
                    "warnings": [asdict(warning) for warning in warnings],
                },
            },
        )
        raw = RawImportEnvelope(
            import_id=raw_id,
            provenance=provenance,
            original_payload=payload,
            unknown_extensions={
                "top_level": unknown_top,
                "data": unknown_data,
                "extensions": data["extensions"],
                "original_tags": data["tags"],
                **({"assets": data["assets"]} if "assets" in data and spec == V3_SPEC else {}),
            },
        )
        return ImportDraft(
            ContentDraft(contents=(character,), assets=tuple(assets), raw_imports=(raw,))
        )
