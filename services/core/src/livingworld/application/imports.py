"""Import-only review contracts, with warnings bound to the ordinary content preview."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from livingworld.application.content import ContentDraft, ContentPreview
from livingworld.domain.content.identifiers import LoreCollectionId
from livingworld.domain.content.models import ContentProvenance, LoreCollection

IMPORT_METADATA_KEY = "livingworld.import"
LOREBOOK_METADATA_KEY = "livingworld.lorebook"


class ContentImportError(ValueError):
    """Stable error code and structural path; never includes imported text or bytes."""

    def __init__(self, code: str, path: str = "") -> None:
        self.code = code
        self.path = path
        super().__init__(f"{code}: {path}" if path else code)


@dataclass(frozen=True, slots=True)
class ImportWarning:
    code: str
    message: str
    path: str = ""


@dataclass(frozen=True, slots=True)
class LorebookSummary:
    collection_id: LoreCollectionId
    source_entry_count: int
    canonical_entry_count: int
    provenance: ContentProvenance


@dataclass(frozen=True, slots=True)
class ImportDraft:
    draft: ContentDraft

    @property
    def warnings(self) -> tuple[ImportWarning, ...]:
        return tuple(
            ImportWarning(item["code"], item["message"], item["path"])
            for content in self.draft.contents
            for item in content.extensions.get(IMPORT_METADATA_KEY, {}).get("warnings", ())
        )

    def preview(self) -> "ImportPreview":
        return ImportPreview(ContentPreview(self.draft, self.draft.preview_hash()))


@dataclass(frozen=True, slots=True)
class ImportPreview:
    content: ContentPreview

    @property
    def warnings(self) -> tuple[ImportWarning, ...]:
        return ImportDraft(self.content.draft).warnings

    @property
    def lorebooks(self) -> tuple[LorebookSummary, ...]:
        return tuple(
            LorebookSummary(
                root.content_id,
                root.extensions[LOREBOOK_METADATA_KEY]["source_entry_count"],
                len(root.lore_entry_ids),
                root.provenance,
            )
            for root in self.content.draft.contents
            if isinstance(root, LoreCollection) and LOREBOOK_METADATA_KEY in root.extensions
        )


class ContentImporter(Protocol):
    def parse(
        self, payload: bytes, *, imported_at: datetime, original_name: str | None = None
    ) -> ImportDraft: ...
