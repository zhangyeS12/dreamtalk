"""Versioned canonical JSON, separate from external format parsing and archives."""

import json
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from uuid import UUID

from livingworld.domain.content.identifiers import (
    CharacterDefinitionId,
    ContentAssetId,
    LoreCollectionId,
    LoreEntryId,
    RawImportId,
    WorldContentId,
    _ContentIdentity,
)
from livingworld.domain.content.models import (
    AssetReference,
    AuthoredFaction,
    AuthoredPlace,
    CanonicalContent,
    CharacterDefinition,
    ContentAsset,
    ContentProvenance,
    ContentRevision,
    ContentSourceKind,
    LoreCollection,
    LoreEntry,
    WorldContent,
)
from livingworld.domain.errors import DomainInvariantError
from livingworld.domain.values import freeze_json

_KINDS = {
    "character_definition": CharacterDefinition,
    "world_content": WorldContent,
    "lore_entry": LoreEntry,
    "lore_collection": LoreCollection,
}


def json_value(value: object) -> object:
    if isinstance(value, _ContentIdentity):
        return value.value.hex
    if isinstance(value, ContentRevision):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat(timespec="microseconds")
    if isinstance(value, StrEnum):
        return value.value
    if is_dataclass(value):
        return {item.name: json_value(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {key: json_value(child) for key, child in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_value(child) for child in value]
    return value


def stable_json(value: object) -> str:
    # Validate finite JSON and reject arbitrary objects, non-string keys and cycles.
    frozen = freeze_json(value)
    try:
        result = json.dumps(
            json_value(frozen),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        result.encode("utf-8")
        return result
    except (ValueError, TypeError, UnicodeError):
        raise DomainInvariantError("Canonical JSON must be finite UTF-8 data") from None


def content_kind(content: CanonicalContent) -> str:
    for kind, model in _KINDS.items():
        if type(content) is model:
            return kind
    raise DomainInvariantError("Unsupported canonical content type")


def serialize_content(content: CanonicalContent) -> str:
    data = json_value(content)
    # Additive v1 fields have explicit legacy encodings. Old rows/hashes stay exact;
    # missing unrelated fields and unknown fields remain errors on deserialization.
    if isinstance(content, LoreEntry) and content.collection_id is None:
        del data["collection_id"]
    if isinstance(content, (CharacterDefinition, WorldContent)) and not content.lore_collection_ids:
        del data["lore_collection_ids"]
    return stable_json({"kind": content_kind(content), "data": data})


def semantic_hash(content: CanonicalContent) -> str:
    return sha256(serialize_content(content).encode("utf-8")).hexdigest()


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise DomainInvariantError("Duplicate canonical JSON object key")
        result[key] = value
    return result


def parse_json(payload: str) -> object:
    try:
        value = json.loads(payload, object_pairs_hook=_unique_object)
        freeze_json(value)
        return value
    except (ValueError, TypeError, RecursionError):
        raise DomainInvariantError("Malformed canonical JSON") from None


def _data(value: object, model: type) -> dict:
    legacy_defaults = {
        LoreEntry: {"collection_id": None},
        CharacterDefinition: {"lore_collection_ids": []},
        WorldContent: {"lore_collection_ids": []},
    }.get(model, {})
    if not isinstance(value, dict):
        raise DomainInvariantError("Canonical fields must match the declared model exactly")
    data = dict(value)
    for name, default in legacy_defaults.items():
        data.setdefault(name, default)
    if set(data) != {item.name for item in fields(model)}:
        raise DomainInvariantError("Canonical fields must match the declared model exactly")
    return data


def _id(value: object, kind: type) -> _ContentIdentity:
    if not isinstance(value, str) or len(value) != 32:
        raise DomainInvariantError("Canonical identity requires UUID hex")
    try:
        identity = UUID(hex=value)
    except ValueError:
        raise DomainInvariantError("Invalid canonical identity") from None
    if identity.hex != value:
        raise DomainInvariantError("Canonical identity requires lowercase UUID hex")
    return kind(identity)


def _sequence(value: object) -> list:
    if not isinstance(value, list):
        raise DomainInvariantError("Canonical array must be a JSON array")
    return value


def decode_provenance(value: object) -> ContentProvenance:
    data = _data(value, ContentProvenance)
    try:
        data["source_kind"] = ContentSourceKind(data["source_kind"])
        if data["imported_at"] is not None:
            if not isinstance(data["imported_at"], str):
                raise ValueError
            data["imported_at"] = datetime.fromisoformat(data["imported_at"])
    except (ValueError, TypeError):
        raise DomainInvariantError("Invalid canonical provenance") from None
    if data["raw_import_id"] is not None:
        data["raw_import_id"] = _id(data["raw_import_id"], RawImportId)
    return ContentProvenance(**data)


def decode_asset(value: object) -> ContentAsset:
    data = _data(value, ContentAsset)
    data["asset_id"] = _id(data["asset_id"], ContentAssetId)
    return ContentAsset(**data)


def deserialize_content(payload: str) -> CanonicalContent:
    envelope = parse_json(payload)
    if not isinstance(envelope, dict) or set(envelope) != {"kind", "data"}:
        raise DomainInvariantError("Invalid canonical content envelope")
    kind = envelope["kind"]
    if not isinstance(kind, str) or kind not in _KINDS:
        raise DomainInvariantError("Unsupported canonical content kind")
    model = _KINDS[kind]
    data = _data(envelope["data"], model)
    data["content_id"] = _id(
        data["content_id"],
        {
            CharacterDefinition: CharacterDefinitionId,
            WorldContent: WorldContentId,
            LoreEntry: LoreEntryId,
            LoreCollection: LoreCollectionId,
        }[model],
    )
    data["provenance"] = decode_provenance(data["provenance"])
    data["revision"] = ContentRevision(data["revision"])
    if model is LoreEntry and data["collection_id"] is not None:
        data["collection_id"] = _id(data["collection_id"], LoreCollectionId)
    if model in (CharacterDefinition, WorldContent):
        data["lore_collection_ids"] = [
            _id(value, LoreCollectionId) for value in _sequence(data["lore_collection_ids"])
        ]
    if model is not LoreEntry:
        data["lore_entry_ids"] = [
            _id(value, LoreEntryId) for value in _sequence(data["lore_entry_ids"])
        ]
    if model in (CharacterDefinition, WorldContent):
        refs = []
        for value in _sequence(data["assets"]):
            ref = _data(value, AssetReference)
            ref["asset_id"] = _id(ref["asset_id"], ContentAssetId)
            refs.append(AssetReference(**ref))
        data["assets"] = refs
    if model is WorldContent:
        for name, part in (("factions", AuthoredFaction), ("locations", AuthoredPlace)):
            data[name] = [part(**_data(value, part)) for value in _sequence(data[name])]
    return model(**data)
