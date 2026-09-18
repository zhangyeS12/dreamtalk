"""Validated content snapshots; prompt-like text and extensions are inert data."""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from livingworld.domain.content import LIVINGWORLD_CONTENT_VERSION
from livingworld.domain.content.identifiers import (
    CharacterDefinitionId,
    ContentAssetId,
    LoreCollectionId,
    LoreEntryId,
    RawImportId,
    WorldContentId,
)
from livingworld.domain.errors import DomainInvariantError
from livingworld.domain.values import (
    JsonValue,
    freeze_json,
    require_text,
    require_type,
    utc_timestamp,
)


@dataclass(frozen=True, slots=True)
class ContentRevision:
    """Library edit version, unrelated to projection Revision or ledger position."""

    value: int = 0

    def __post_init__(self) -> None:
        if type(self.value) is not int or self.value < 0:
            raise DomainInvariantError("ContentRevision requires a nonnegative integer")


class ContentSourceKind(StrEnum):
    NATIVE = "native"
    IMPORT = "import"
    BUILDER = "builder"


def require_hash(value: str) -> None:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise DomainInvariantError("Content hash requires lowercase SHA-256 hex")


def _texts(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list)):
        raise DomainInvariantError(f"{name} requires a sequence of text")
    result = tuple(value)
    for item in result:
        require_text(item, name)
    return result


def _objects(value: object, kind: type, name: str) -> tuple:
    if not isinstance(value, (tuple, list)):
        raise DomainInvariantError(f"{name} requires a sequence")
    result = tuple(value)
    for item in result:
        require_type(item, kind, name)
    return result


def _opaque(value: object) -> Mapping[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise DomainInvariantError("Opaque metadata requires a JSON object")
    return freeze_json(value)


@dataclass(frozen=True, slots=True, kw_only=True)
class ContentProvenance:
    source_kind: ContentSourceKind
    source_format: str
    source_format_version: str | None = None
    original_name: str | None = None
    source_identifier: str | None = None
    imported_at: datetime | None = None
    content_hash: str | None = None
    raw_import_id: RawImportId | None = None

    def __post_init__(self) -> None:
        require_type(self.source_kind, ContentSourceKind, "source_kind")
        require_text(self.source_format, "source_format")
        for name in ("source_format_version", "original_name", "source_identifier"):
            if (value := getattr(self, name)) is not None:
                require_text(value, name)
        if self.imported_at is not None:
            object.__setattr__(self, "imported_at", utc_timestamp(self.imported_at, "imported_at"))
        if self.content_hash is not None:
            require_hash(self.content_hash)
        if self.raw_import_id is not None:
            require_type(self.raw_import_id, RawImportId, "raw_import_id")
        if self.source_kind is ContentSourceKind.IMPORT and (
            self.imported_at is None or self.content_hash is None or self.raw_import_id is None
        ):
            raise DomainInvariantError(
                "Imported provenance requires UTC time, hash and raw reference"
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class ContentAsset:
    """Opaque resource reference and metadata; never opens a path or processes images."""

    asset_id: ContentAssetId
    media_type: str
    resource_reference: str
    content_hash: str | None = None
    extensions: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_type(self.asset_id, ContentAssetId, "asset_id")
        require_text(self.media_type, "media_type")
        require_text(self.resource_reference, "resource_reference")
        if self.content_hash is not None:
            require_hash(self.content_hash)
        object.__setattr__(self, "extensions", _opaque(self.extensions))


@dataclass(frozen=True, slots=True, kw_only=True)
class AssetReference:
    asset_id: ContentAssetId
    role: str

    def __post_init__(self) -> None:
        require_type(self.asset_id, ContentAssetId, "asset_id")
        require_text(self.role, "asset role")


@dataclass(frozen=True, slots=True, kw_only=True)
class AuthoredPlace:
    """A local authored key, not a runtime LocationId or a simulated location."""

    key: str
    name: str
    description: str = ""
    extensions: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_text(self.key, "place key")
        require_text(self.name, "place name")
        require_type(self.description, str, "place description")
        object.__setattr__(self, "extensions", _opaque(self.extensions))


@dataclass(frozen=True, slots=True, kw_only=True)
class AuthoredFaction:
    key: str
    name: str
    description: str = ""
    extensions: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_text(self.key, "faction key")
        require_text(self.name, "faction name")
        require_type(self.description, str, "faction description")
        object.__setattr__(self, "extensions", _opaque(self.extensions))


@dataclass(frozen=True, slots=True, kw_only=True)
class _Content:
    provenance: ContentProvenance
    revision: ContentRevision = ContentRevision()
    content_version: int = LIVINGWORLD_CONTENT_VERSION
    extensions: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_type(self.provenance, ContentProvenance, "provenance")
        require_type(self.revision, ContentRevision, "content revision")
        if type(self.content_version) is not int or (
            self.content_version != LIVINGWORLD_CONTENT_VERSION
        ):
            raise DomainInvariantError("Unsupported canonical content version")
        object.__setattr__(self, "extensions", _opaque(self.extensions))


@dataclass(frozen=True, slots=True, kw_only=True)
class LoreEntry(_Content):
    content_id: LoreEntryId
    content: str
    # None is a deprecated read/edit compatibility state, never a new write option.
    collection_id: LoreCollectionId | None
    title: str = ""
    comment: str = ""
    keywords: tuple[str, ...] = ()
    secondary_keywords: tuple[str, ...] = ()
    enabled: bool = True
    priority: int = 0
    order: int = 0
    scope: str | None = None
    category: str | None = None
    group: str | None = None
    activation_metadata: Mapping[str, JsonValue] = field(default_factory=dict)
    insertion_metadata: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _Content.__post_init__(self)
        require_type(self.content_id, LoreEntryId, "lore content_id")
        require_text(self.content, "lore content")
        if self.collection_id is not None:
            require_type(self.collection_id, LoreCollectionId, "lore collection_id")
        for name in ("title", "comment"):
            require_type(getattr(self, name), str, name)
        for name in ("keywords", "secondary_keywords"):
            object.__setattr__(self, name, _texts(getattr(self, name), name))
        if self.secondary_keywords and not self.keywords:
            raise DomainInvariantError("Secondary keywords require primary keywords")
        if type(self.enabled) is not bool:
            raise DomainInvariantError("Lore enabled must be bool")
        for name in ("priority", "order"):
            if type(getattr(self, name)) is not int:
                raise DomainInvariantError(f"Lore {name} must be integer")
        for name in ("scope", "category", "group"):
            if (value := getattr(self, name)) is not None:
                require_text(value, name)
        for name in ("activation_metadata", "insertion_metadata"):
            object.__setattr__(self, name, _opaque(getattr(self, name)))


@dataclass(frozen=True, slots=True, kw_only=True)
class LoreCollection(_Content):
    """Authored library root; references its entries without asserting world facts."""

    content_id: LoreCollectionId
    name: str = ""
    description: str = ""
    lore_entry_ids: tuple[LoreEntryId, ...] = ()
    activation_metadata: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _Content.__post_init__(self)
        require_type(self.content_id, LoreCollectionId, "lore collection content_id")
        for name in ("name", "description"):
            require_type(getattr(self, name), str, name)
        entries = _objects(self.lore_entry_ids, LoreEntryId, "lore_entry_ids")
        if len(set(entries)) != len(entries):
            raise DomainInvariantError("Duplicate LoreEntryId reference")
        object.__setattr__(self, "lore_entry_ids", entries)
        object.__setattr__(self, "activation_metadata", _opaque(self.activation_metadata))


def _root_collections(root: object) -> None:
    object.__setattr__(root, "tags", _texts(root.tags, "tags"))
    lore = _objects(root.lore_entry_ids, LoreEntryId, "lore_entry_ids")
    if len(set(lore)) != len(lore):
        raise DomainInvariantError("Duplicate LoreEntryId reference")
    object.__setattr__(root, "lore_entry_ids", lore)
    assets = _objects(root.assets, AssetReference, "assets")
    if len(set(assets)) != len(assets):
        raise DomainInvariantError("Duplicate asset reference")
    object.__setattr__(root, "assets", assets)


def _collection_references(root: object) -> None:
    collections = _objects(root.lore_collection_ids, LoreCollectionId, "lore_collection_ids")
    if len(set(collections)) != len(collections):
        raise DomainInvariantError("Duplicate LoreCollectionId reference")
    object.__setattr__(root, "lore_collection_ids", collections)


@dataclass(frozen=True, slots=True, kw_only=True)
class CharacterDefinition(_Content):
    content_id: CharacterDefinitionId
    display_name: str
    aliases: tuple[str, ...] = ()
    description: str = ""
    personality: str = ""
    background: str = ""
    scenario: str = ""
    speech_guidance: str = ""
    creator_notes: str = ""
    authored_instructions: Mapping[str, JsonValue] = field(default_factory=dict)
    example_dialogue: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    assets: tuple[AssetReference, ...] = ()
    lore_entry_ids: tuple[LoreEntryId, ...] = ()
    lore_collection_ids: tuple[LoreCollectionId, ...] = ()

    def __post_init__(self) -> None:
        _Content.__post_init__(self)
        require_type(self.content_id, CharacterDefinitionId, "character definition content_id")
        require_text(self.display_name, "display_name")
        for name in (
            "description",
            "personality",
            "background",
            "scenario",
            "speech_guidance",
            "creator_notes",
        ):
            require_type(getattr(self, name), str, name)
        for name in ("aliases", "example_dialogue"):
            object.__setattr__(self, name, _texts(getattr(self, name), name))
        object.__setattr__(self, "authored_instructions", _opaque(self.authored_instructions))
        _root_collections(self)
        _collection_references(self)


@dataclass(frozen=True, slots=True, kw_only=True)
class WorldContent(_Content):
    content_id: WorldContentId
    title: str
    description: str = ""
    setting: str = ""
    rules: tuple[str, ...] = ()
    factions: tuple[AuthoredFaction, ...] = ()
    locations: tuple[AuthoredPlace, ...] = ()
    lore_entry_ids: tuple[LoreEntryId, ...] = ()
    tags: tuple[str, ...] = ()
    assets: tuple[AssetReference, ...] = ()
    lore_collection_ids: tuple[LoreCollectionId, ...] = ()

    def __post_init__(self) -> None:
        _Content.__post_init__(self)
        require_type(self.content_id, WorldContentId, "world content_id")
        require_text(self.title, "title")
        for name in ("description", "setting"):
            require_type(getattr(self, name), str, name)
        object.__setattr__(self, "rules", _texts(self.rules, "rules"))
        for name, kind in (("factions", AuthoredFaction), ("locations", AuthoredPlace)):
            values = _objects(getattr(self, name), kind, name)
            if len({value.key for value in values}) != len(values):
                raise DomainInvariantError(f"Duplicate authored {name} key")
            object.__setattr__(self, name, values)
        _root_collections(self)
        _collection_references(self)


type CanonicalContent = CharacterDefinition | WorldContent | LoreEntry | LoreCollection
