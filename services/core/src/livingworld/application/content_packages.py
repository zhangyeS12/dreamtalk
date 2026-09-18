"""Native authored-content contracts. No ZIP, filesystem or runtime capabilities."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from typing import Protocol
from uuid import UUID

from livingworld.application.content import ContentDraft, ContentRepository
from livingworld.domain.content import LIVINGWORLD_CONTENT_VERSION
from livingworld.domain.content.identifiers import ContentAssetId, ContentId
from livingworld.domain.content.models import (
    CanonicalContent,
    CharacterDefinition,
    LoreEntry,
    WorldContent,
    require_hash,
)
from livingworld.domain.content.serialization import json_value, semantic_hash, stable_json
from livingworld.domain.values import freeze_json, utc_timestamp

LWCONTENT_PACKAGE_FORMAT = 1
LWCONTENT_IDENTITY = "livingworld.content.package"
# Explicit authored-source classification; new source families require registration.
APPROVED_CONTENT_SOURCES = frozenset({"chara_card_v2", "chara_card_v3", "sillytavern_world_info"})


class PackageError(ValueError):
    def __init__(self, code: str, path: str = "") -> None:
        self.code, self.path = code, path
        super().__init__(f"{code}: {path}" if path else code)


@dataclass(frozen=True, slots=True)
class PackageId:
    value: UUID

    def __post_init__(self) -> None:
        if not isinstance(self.value, UUID):
            raise PackageError("invalid_package_identity")


@dataclass(frozen=True, slots=True)
class PackageLimits:
    max_entries: int = 10_000
    max_manifest_bytes: int = 4 * 1024 * 1024
    max_entry_bytes: int = 32 * 1024 * 1024
    max_total_bytes: int = 256 * 1024 * 1024
    max_compression_ratio: int = 200
    max_archive_bytes: int = 256 * 1024 * 1024
    max_json_depth: int = 64
    read_chunk_bytes: int = 64 * 1024

    def __post_init__(self) -> None:
        for value in json_value(self).values():
            if type(value) is not int or value <= 0:
                raise PackageError("invalid_package_limits")


@dataclass(frozen=True, slots=True)
class AssetBlobBinding:
    asset_id: ContentAssetId
    digest: str
    size: int

    def __post_init__(self) -> None:
        if not isinstance(self.asset_id, ContentAssetId):
            raise PackageError("invalid_blob_asset_identity")
        require_hash(self.digest)
        if type(self.size) is not int or self.size < 0:
            raise PackageError("invalid_blob_size")


@dataclass(frozen=True, slots=True)
class PackagedBlob:
    binding: AssetBlobBinding
    data: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.binding, AssetBlobBinding) or type(self.data) is not bytes:
            raise PackageError("invalid_asset_blob")
        if (
            len(self.data) != self.binding.size
            or sha256(self.data).hexdigest() != self.binding.digest
        ):
            raise PackageError("asset_integrity_mismatch")


def content_dependencies(content: CanonicalContent) -> tuple[ContentId, ...]:
    if isinstance(content, LoreEntry):
        if content.collection_id is None:
            raise PackageError("legacy_unbound_lore_not_portable")
        return (content.collection_id,)
    if isinstance(content, (CharacterDefinition, WorldContent)):
        return (*content.lore_entry_ids, *content.lore_collection_ids)
    return content.lore_entry_ids


def dependency_closure(
    roots: tuple[ContentId, ...], contents: Mapping[ContentId, CanonicalContent]
) -> set[ContentId]:
    found, pending = set(), list(roots)
    while pending:
        identity = pending.pop()
        if identity in found:
            continue
        content = contents.get(identity)
        if content is None:
            raise PackageError("unresolved_content_reference")
        found.add(identity)
        pending.extend(content_dependencies(content))
    return found


def _portable(value: str | None) -> None:
    if value is not None and (
        value.startswith(("/", "\\", "file:"))
        or len(value) >= 2
        and value[1] == ":"
        and value[0].isalpha()
    ):
        raise PackageError("nonportable_local_reference")


@dataclass(frozen=True, slots=True, kw_only=True)
class PackageDraft:
    package_id: PackageId
    created_at_utc: datetime
    root_ids: tuple[ContentId, ...]
    content: ContentDraft
    blobs: tuple[PackagedBlob, ...] = ()
    archive_size: int = 0
    uncompressed_size: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.package_id, PackageId) or not isinstance(self.content, ContentDraft):
            raise PackageError("invalid_package_draft")
        object.__setattr__(
            self, "created_at_utc", utc_timestamp(self.created_at_utc, "package time")
        )
        if not isinstance(self.root_ids, (tuple, list)) or any(
            not isinstance(identity, ContentId.__value__) for identity in self.root_ids
        ):
            raise PackageError("invalid_package_roots")
        object.__setattr__(self, "root_ids", tuple(self.root_ids))
        object.__setattr__(self, "blobs", tuple(self.blobs))
        if not self.root_ids or len(set(self.root_ids)) != len(self.root_ids):
            raise PackageError("invalid_package_roots")
        contents = {root.content_id: root for root in self.content.contents}
        if dependency_closure(self.root_ids, contents) != set(contents):
            raise PackageError("unselected_package_content")
        referenced_assets = {
            ref.asset_id
            for root in self.content.contents
            if isinstance(root, (CharacterDefinition, WorldContent))
            for ref in root.assets
        }
        assets = {asset.asset_id: asset for asset in self.content.assets}
        if set(assets) != referenced_assets:
            raise PackageError("unselected_package_asset")
        blob_ids = set()
        for blob in self.blobs:
            if not isinstance(blob, PackagedBlob) or blob.binding.asset_id not in assets:
                raise PackageError("unresolved_blob_asset")
            if blob.binding.asset_id in blob_ids:
                raise PackageError("duplicate_blob_asset")
            blob_ids.add(blob.binding.asset_id)
            expected = assets[blob.binding.asset_id].content_hash
            if expected is not None and expected != blob.binding.digest:
                raise PackageError("canonical_asset_hash_mismatch")
        referenced_sources = {
            root.provenance.raw_import_id
            for root in self.content.contents
            if root.provenance.raw_import_id is not None
        }
        for asset in assets.values():
            _portable(asset.resource_reference)
            descriptor = asset.extensions.get("character_card_descriptor")
            if isinstance(descriptor, Mapping) and isinstance(descriptor.get("uri"), str):
                _portable(descriptor["uri"])
            raw_id = asset.extensions.get("raw_import_id")
            if raw_id is not None:
                matching = [
                    raw.import_id
                    for raw in self.content.raw_imports
                    if raw.import_id.value.hex == raw_id
                ]
                if not matching:
                    raise PackageError("unresolved_asset_source")
                referenced_sources.update(matching)
        if {raw.import_id for raw in self.content.raw_imports} != referenced_sources:
            raise PackageError("unselected_package_source")
        for root in self.content.contents:
            _portable(root.provenance.original_name)
            _portable(root.provenance.source_identifier)
        for raw in self.content.raw_imports:
            if raw.provenance.source_format not in APPROVED_CONTENT_SOURCES:
                raise PackageError("source_not_classified_as_portable_content")
            _portable(raw.provenance.original_name)
            _portable(raw.provenance.source_identifier)
        if type(self.archive_size) is not int or self.archive_size < 0:
            raise PackageError("invalid_archive_size")
        if type(self.uncompressed_size) is not int or self.uncompressed_size < 0:
            raise PackageError("invalid_archive_size")

    @property
    def semantic_hash(self) -> str:
        return sha256(
            stable_json(
                {
                    "format": LWCONTENT_IDENTITY,
                    "format_version": LWCONTENT_PACKAGE_FORMAT,
                    "content_version": LIVINGWORLD_CONTENT_VERSION,
                    "package_id": self.package_id.value.hex,
                    "created_at_utc": json_value(self.created_at_utc),
                    "roots": sorted(
                        (type(identity).__name__, identity.value.hex) for identity in self.root_ids
                    ),
                    "content": self.content.preview_hash(),
                    "blobs": sorted(
                        (blob.binding.asset_id.value.hex, blob.binding.digest, blob.binding.size)
                        for blob in self.blobs
                    ),
                }
            ).encode("utf-8")
        ).hexdigest()


class ConflictState(StrEnum):
    NEW = "NEW"
    IDENTICAL = "IDENTICAL"
    LOCAL_MODIFIED = "LOCAL_MODIFIED"
    INCOMING_DIFFERENT = "INCOMING_DIFFERENT"
    DIVERGED = "DIVERGED"
    DIFFERENT_NO_BASELINE = "DIFFERENT_NO_BASELINE"


class ConflictDecision(StrEnum):
    KEEP_LOCAL = "KEEP_LOCAL"
    REPLACE_WITH_INCOMING = "REPLACE_WITH_INCOMING"


@dataclass(frozen=True, slots=True)
class AcceptedImportBaseline:
    content_id: ContentId
    accepted_semantic_hash: str
    accepted_at_utc: datetime
    source_package_id: PackageId | None = None
    source_package_hash: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.content_id, ContentId.__value__):
            raise PackageError("invalid_baseline_identity")
        require_hash(self.accepted_semantic_hash)
        object.__setattr__(
            self, "accepted_at_utc", utc_timestamp(self.accepted_at_utc, "baseline time")
        )
        if self.source_package_id is not None and not isinstance(self.source_package_id, PackageId):
            raise PackageError("invalid_baseline_package_identity")
        if self.source_package_hash is not None:
            require_hash(self.source_package_hash)


@dataclass(frozen=True, slots=True)
class PackageConflict:
    incoming: CanonicalContent
    local: CanonicalContent | None
    baseline: AcceptedImportBaseline | None

    @property
    def state(self) -> ConflictState:
        if self.local is None:
            return ConflictState.NEW
        local, incoming = semantic_hash(self.local), semantic_hash(self.incoming)
        if local == incoming:
            return ConflictState.IDENTICAL
        if self.baseline is None:
            return ConflictState.DIFFERENT_NO_BASELINE
        baseline = self.baseline.accepted_semantic_hash
        if local != baseline and incoming == baseline:
            return ConflictState.LOCAL_MODIFIED
        if local == baseline and incoming != baseline:
            return ConflictState.INCOMING_DIFFERENT
        return ConflictState.DIVERGED


@dataclass(frozen=True, slots=True)
class PackagePreview:
    package: PackageDraft
    conflicts: tuple[PackageConflict, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.package, PackageDraft) or not isinstance(
            self.conflicts, (tuple, list)
        ):
            raise PackageError("invalid_package_preview")
        if any(not isinstance(item, PackageConflict) for item in self.conflicts):
            raise PackageError("invalid_package_preview")
        object.__setattr__(self, "conflicts", tuple(self.conflicts))

    @property
    def summary(self) -> Mapping:
        from livingworld.domain.content.serialization import content_kind

        counts = {}
        for root in self.package.content.contents:
            kind = content_kind(root)
            counts[kind] = counts.get(kind, 0) + 1
        return freeze_json(
            {
                "format": LWCONTENT_IDENTITY,
                "format_version": LWCONTENT_PACKAGE_FORMAT,
                "package_id": self.package.package_id.value.hex,
                "content_counts": counts,
                "asset_count": len(self.package.content.assets),
                "source_count": len(self.package.content.raw_imports),
                "packaged_blob_count": len({blob.binding.digest for blob in self.package.blobs}),
                "archive_size": self.package.archive_size,
                "uncompressed_size": self.package.uncompressed_size,
                "unresolved_references": [],
            }
        )

    @property
    def reviewed_hash(self) -> str:
        return sha256(
            stable_json(
                {
                    "package": self.package.semantic_hash,
                    "conflicts": [
                        {
                            "id": json_value(item.incoming.content_id),
                            "kind": type(item.incoming.content_id).__name__,
                            "incoming": semantic_hash(item.incoming),
                            "local": semantic_hash(item.local) if item.local else None,
                            "baseline": {
                                "hash": item.baseline.accepted_semantic_hash,
                                "accepted_at_utc": json_value(item.baseline.accepted_at_utc),
                                "source_package_id": item.baseline.source_package_id.value.hex
                                if item.baseline.source_package_id
                                else None,
                                "source_package_hash": item.baseline.source_package_hash,
                            }
                            if item.baseline
                            else None,
                            "state": item.state.value,
                        }
                        for item in self.conflicts
                    ],
                }
            ).encode("utf-8")
        ).hexdigest()

    @property
    def warnings(self) -> tuple[str, ...]:
        packaged = {blob.binding.asset_id for blob in self.package.blobs}
        return tuple(
            sorted(
                "asset_reference_only:" + asset.asset_id.value.hex
                for asset in self.package.content.assets
                if asset.asset_id not in packaged
            )
        )


@dataclass(frozen=True, slots=True)
class PackageExportResult:
    package_bytes: bytes
    package: PackageDraft
    warnings: tuple[str, ...]
    suggested_extension: str = ".lwcontent"
    content_type: str = "application/vnd.livingworld.content+zip"

    @property
    def summary(self) -> Mapping:
        summary = dict(PackagePreview(self.package, ()).summary)
        summary["archive_size"] = len(self.package_bytes)
        # A constructed export draft has not recorded container read statistics.
        summary["uncompressed_size"] = self.package.uncompressed_size or None
        return freeze_json(summary)

    @property
    def semantic_hash(self) -> str:
        return self.package.semantic_hash


class PackageAdapter(Protocol):
    def write(self, package: PackageDraft) -> bytes: ...
    def read(self, payload: bytes) -> PackageDraft: ...


class ContentAssetStore(Protocol):
    async def read(self, binding: AssetBlobBinding) -> bytes: ...
    async def materialize(self, blob: PackagedBlob) -> None: ...


class PackageRepository(ContentRepository, Protocol):
    async def load_baseline(self, content_id: ContentId) -> AcceptedImportBaseline | None: ...
    async def load_blob_binding(self, asset_id: ContentAssetId) -> AssetBlobBinding | None: ...
    async def commit_package(
        self,
        draft: ContentDraft,
        *,
        expected: tuple[PackageConflict, ...],
        accepted: tuple[AcceptedImportBaseline, ...],
        bindings: tuple[AssetBlobBinding, ...],
    ) -> None: ...
