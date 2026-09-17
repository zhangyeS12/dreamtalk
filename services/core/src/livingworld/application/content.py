"""Closed content drafts and a preview/commit seam without runtime mutation rights."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Protocol

from livingworld.domain.content.identifiers import ContentAssetId, ContentId, RawImportId
from livingworld.domain.content.models import (
    CanonicalContent,
    ContentAsset,
    ContentProvenance,
    ContentRevision,
    ContentSourceKind,
    LoreEntry,
)
from livingworld.domain.content.serialization import (
    content_kind,
    json_value,
    serialize_content,
    stable_json,
)
from livingworld.domain.errors import DomainInvariantError
from livingworld.domain.values import JsonValue, freeze_json, require_type


class ContentConflictError(Exception):
    """Duplicate identity, stale edit version or immutable raw/asset collision."""


@dataclass(frozen=True, slots=True, kw_only=True)
class RawImportEnvelope:
    import_id: RawImportId
    provenance: ContentProvenance
    original_payload: bytes
    unknown_extensions: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_type(self.import_id, RawImportId, "import_id")
        require_type(self.provenance, ContentProvenance, "raw provenance")
        if type(self.original_payload) is not bytes:
            raise DomainInvariantError("Raw import payload requires exact bytes")
        if self.provenance.source_kind is not ContentSourceKind.IMPORT or (
            self.provenance.raw_import_id != self.import_id
            or self.provenance.content_hash != sha256(self.original_payload).hexdigest()
        ):
            raise DomainInvariantError("Raw import provenance/hash does not match original bytes")
        if not isinstance(self.unknown_extensions, Mapping):
            raise DomainInvariantError("Raw extensions require an object")
        object.__setattr__(self, "unknown_extensions", freeze_json(self.unknown_extensions))


@dataclass(frozen=True, slots=True, kw_only=True)
class ContentDraft:
    """Self-contained reference graph, not a World or an external file format."""

    contents: tuple[CanonicalContent, ...]
    assets: tuple[ContentAsset, ...] = ()
    raw_imports: tuple[RawImportEnvelope, ...] = ()

    def __post_init__(self) -> None:
        for name in ("contents", "assets", "raw_imports"):
            values = getattr(self, name)
            if not isinstance(values, (list, tuple)):
                raise DomainInvariantError("Draft members require sequences")
            object.__setattr__(self, name, tuple(values))
        if not self.contents:
            raise DomainInvariantError("Content draft must not be empty")
        ids = set()
        for content in self.contents:
            content_kind(content)
            if content.content_id in ids:
                raise DomainInvariantError("Duplicate typed content ID")
            ids.add(content.content_id)
        assets = {}
        for asset in self.assets:
            require_type(asset, ContentAsset, "draft asset")
            if asset.asset_id in assets:
                raise DomainInvariantError("Duplicate ContentAssetId")
            assets[asset.asset_id] = asset
        imports = {}
        for envelope in self.raw_imports:
            require_type(envelope, RawImportEnvelope, "raw import")
            if envelope.import_id in imports:
                raise DomainInvariantError("Duplicate RawImportId")
            imports[envelope.import_id] = envelope
        lore_ids = {
            content.content_id for content in self.contents if isinstance(content, LoreEntry)
        }
        for content in self.contents:
            if not isinstance(content, LoreEntry):
                if not set(content.lore_entry_ids) <= lore_ids:
                    raise DomainInvariantError("Unresolved LoreEntryId in draft")
                if any(ref.asset_id not in assets for ref in content.assets):
                    raise DomainInvariantError("Unresolved ContentAssetId in draft")
            provenance = content.provenance
            if provenance.raw_import_id is not None:
                envelope = imports.get(provenance.raw_import_id)
                if envelope is None or envelope.provenance != provenance:
                    raise DomainInvariantError("Unresolved or inconsistent raw provenance in draft")

    def preview_hash(self) -> str:
        # Bundle order is administrative; authored arrays inside each root retain order.
        contents = sorted(serialize_content(content) for content in self.contents)
        assets = sorted(stable_json(json_value(asset)) for asset in self.assets)
        imports = sorted(
            stable_json(
                {
                    "import_id": json_value(envelope.import_id),
                    "provenance": json_value(envelope.provenance),
                    "unknown_extensions": json_value(envelope.unknown_extensions),
                }
            )
            for envelope in self.raw_imports
        )
        return sha256(
            stable_json(
                {
                    "contents": contents,
                    "assets": assets,
                    "raw_imports": imports,
                }
            ).encode("utf-8")
        ).hexdigest()


@dataclass(frozen=True, slots=True)
class ContentPreview:
    draft: ContentDraft
    preview_hash: str

    def __post_init__(self) -> None:
        require_type(self.draft, ContentDraft, "preview draft")
        if self.preview_hash != self.draft.preview_hash():
            raise DomainInvariantError("Preview hash does not match draft")


class ContentRepository(Protocol):
    async def load(self, content_id: ContentId) -> CanonicalContent | None: ...

    async def load_asset(self, asset_id: ContentAssetId) -> ContentAsset | None: ...

    async def load_raw_import(self, import_id: RawImportId) -> RawImportEnvelope | None: ...

    async def save(
        self,
        draft: ContentDraft,
        expected_revisions: Mapping[ContentId, ContentRevision | None],
    ) -> None: ...


class ContentService:
    def __init__(self, repository: ContentRepository) -> None:
        self._repository = repository

    def preview(self, draft: ContentDraft) -> ContentPreview:
        require_type(draft, ContentDraft, "draft")
        return ContentPreview(draft, draft.preview_hash())

    async def commit(
        self,
        preview: ContentPreview,
        *,
        reviewed_hash: str,
        expected_revisions: Mapping[ContentId, ContentRevision | None],
    ) -> None:
        require_type(preview, ContentPreview, "preview")
        if reviewed_hash != preview.preview_hash or reviewed_hash != preview.draft.preview_hash():
            raise DomainInvariantError("Commit requires the reviewed preview hash")
        await self._repository.save(preview.draft, expected_revisions)
