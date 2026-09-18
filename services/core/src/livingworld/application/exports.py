"""Pure content export contracts. Callers choose the format and save bytes themselves."""

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import Protocol

from livingworld.application.content import ContentDraft
from livingworld.domain.content.identifiers import ContentId, LoreCollectionId


class ExportTarget(StrEnum):
    CHARACTER_CARD_V2 = "character_card_v2"
    CHARACTER_CARD_V3 = "character_card_v3"
    SILLYTAVERN_WORLD_INFO = "sillytavern_world_info"
    CHARACTER_BOOK = "character_book"


class CharacterBookVersion(StrEnum):
    V2 = "v2"
    V3 = "v3"


class ContentExportError(ValueError):
    """Stable code/path without authored content, tokens or original bytes."""

    def __init__(self, code: str, path: str = "") -> None:
        self.code, self.path = code, path
        super().__init__(f"{code}: {path}" if path else code)


class ExportDecisionRequiredError(ContentExportError):
    """A required target semantic needs an explicit caller decision."""


@dataclass(frozen=True, slots=True)
class ExportWarning:
    code: str
    message: str
    path: str = ""


@dataclass(frozen=True, slots=True)
class V3CharacterBookOptions:
    # Explicit export policy for unspecified entries only; never a global setting.
    use_regex: bool | None = None

    def __post_init__(self) -> None:
        if self.use_regex is not None and type(self.use_regex) is not bool:
            raise ContentExportError("invalid_v3_export_policy", "use_regex")


@dataclass(frozen=True, slots=True, kw_only=True)
class ExportRequest:
    draft: ContentDraft
    content_id: ContentId
    target_format: ExportTarget
    embedded_collection_id: LoreCollectionId | None = None
    character_book_version: CharacterBookVersion | None = None
    v3_book_options: V3CharacterBookOptions = V3CharacterBookOptions()

    def __post_init__(self) -> None:
        if not isinstance(self.draft, ContentDraft) or not isinstance(
            self.target_format, ExportTarget
        ):
            raise ContentExportError("invalid_export_request")
        if not isinstance(self.content_id, ContentId.__value__):
            raise ContentExportError("invalid_export_content_id")
        if not isinstance(self.v3_book_options, V3CharacterBookOptions):
            raise ContentExportError("invalid_v3_export_policy")
        if self.embedded_collection_id is not None and not isinstance(
            self.embedded_collection_id, LoreCollectionId
        ):
            raise ContentExportError("invalid_lore_selection")
        if self.target_format is ExportTarget.CHARACTER_BOOK:
            if self.character_book_version is None:
                raise ExportDecisionRequiredError("character_book_version_required")
            if not isinstance(self.character_book_version, CharacterBookVersion):
                raise ContentExportError("invalid_character_book_version")
        elif self.character_book_version is not None:
            raise ContentExportError("unexpected_character_book_version")
        if self.v3_book_options.use_regex is not None and not (
            self.target_format is ExportTarget.CHARACTER_CARD_V3
            or self.target_format is ExportTarget.CHARACTER_BOOK
            and self.character_book_version is CharacterBookVersion.V3
        ):
            raise ContentExportError("unexpected_v3_export_policy")


@dataclass(frozen=True, slots=True)
class ExportResult:
    target_format: ExportTarget
    serialized_bytes: bytes
    content_type: str
    suggested_extension: str
    warnings: tuple[ExportWarning, ...]
    semantic_hash: str

    def __post_init__(self) -> None:
        if type(self.serialized_bytes) is not bytes or (
            self.semantic_hash != sha256(self.serialized_bytes).hexdigest()
        ):
            raise ContentExportError("invalid_export_result")


class ContentExporter(Protocol):
    def serialize(self, request: ExportRequest) -> ExportResult: ...


class ExportService:
    """Orchestrate a validated, explicit content snapshot without persistence writes."""

    def __init__(self, exporter: ContentExporter) -> None:
        self._exporter = exporter

    def export(self, request: ExportRequest) -> ExportResult:
        if not isinstance(request, ExportRequest):
            raise ContentExportError("invalid_export_request")
        if request.content_id not in {root.content_id for root in request.draft.contents}:
            raise ContentExportError("export_content_not_found")
        return self._exporter.serialize(request)
