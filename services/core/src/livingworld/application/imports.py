"""Import-only review contracts, with warnings bound to the ordinary content preview."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from livingworld.application.content import ContentDraft, ContentPreview

IMPORT_METADATA_KEY = "livingworld.import"


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


class ContentImporter(Protocol):
    def parse(
        self, payload: bytes, *, imported_at: datetime, original_name: str | None = None
    ) -> ImportDraft: ...
