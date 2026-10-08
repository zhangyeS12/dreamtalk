"""Reviewed world-scoped authored imports, independent of runtime characters."""

from dataclasses import dataclass
from time import monotonic
from typing import Literal, Protocol
from uuid import UUID, uuid4

from livingworld.application.content import ContentConflictError, ContentDraft
from livingworld.application.imports import (
    ContentImporter,
    ContentImportError,
    ImportDraft,
    ImportPreview,
)
from livingworld.domain.content.models import CanonicalContent, LoreCollection, LoreEntry
from livingworld.domain.content.serialization import json_value, stable_json
from livingworld.domain.identifiers import WorldId

ImportKind = Literal["character", "lorebook"]


@dataclass(frozen=True)
class AcceptedWorldContent:
    import_id: UUID
    world_id: WorldId
    reviewed_hash: str
    kind: ImportKind
    contents: tuple[CanonicalContent, ...]
    replaces_import_id: UUID | None = None


def unchanged_lore_entry_pairs(
    previous: AcceptedWorldContent, current: AcceptedWorldContent
) -> tuple[tuple[UUID, UUID], ...]:
    """Retain only server-tracked, unchanged entries from this native edit."""
    if (
        previous.world_id != current.world_id
        or previous.kind != "lorebook"
        or current.kind != "lorebook"
        or current.replaces_import_id != previous.import_id
    ):
        return ()
    books = [root for root in current.contents if isinstance(root, LoreCollection)]
    if len(books) != 1 or books[0].provenance.source_format != "dreamtalk-editor":
        return ()
    edit = json_value(books[0].extensions.get("dreamtalk.edit", {}))
    if not isinstance(edit, dict) or edit.get("previous_import_id") != str(previous.import_id):
        return ()
    lineage = edit.get("lore_entry_predecessors")
    if not isinstance(lineage, dict):
        return ()
    # No title/text guessing: new or externally replaced entries have no trusted
    # native-edit predecessor. Duplicate source targets must not widen exposure.
    predecessors = [value for value in lineage.values() if isinstance(value, str)]
    old_entries = {
        root.content_id.value: root for root in previous.contents if isinstance(root, LoreEntry)
    }
    old_books = {
        root.content_id: root for root in previous.contents if isinstance(root, LoreCollection)
    }
    pairs = []
    for entry in current.contents:
        if not isinstance(entry, LoreEntry) or not entry.enabled:
            continue
        predecessor = lineage.get(str(entry.content_id.value))
        if not isinstance(predecessor, str) or predecessors.count(predecessor) != 1:
            continue
        try:
            original = old_entries.get(UUID(predecessor))
        except ValueError:
            continue
        if original is None or (collection := old_books.get(original.collection_id)) is None:
            continue
        if collection.activation_metadata != books[0].activation_metadata:
            continue
        old, new = json_value(original), json_value(entry)
        # IDs/provenance change in every independent graph; all authored fields,
        # opaque conditions and extensions must still match exactly.
        for field in ("content_id", "revision", "provenance", "collection_id"):
            old.pop(field)
            new.pop(field)
        if stable_json(old) == stable_json(new):
            pairs.append((original.content_id.value, entry.content_id.value))
    return tuple(pairs)


@dataclass(frozen=True)
class CommonLoreEntry:
    import_id: UUID
    entry: LoreEntry
    collection: LoreCollection | None = None


class WorldContentStore(Protocol):
    async def require_world(self, world_id: WorldId) -> None: ...
    async def list_imports(
        self, world_id: WorldId, *, include_removed: bool = False
    ) -> tuple[AcceptedWorldContent, ...]: ...
    async def find(self, import_id: UUID) -> AcceptedWorldContent | None: ...
    async def is_current(self, import_id: UUID) -> bool: ...
    async def remove_character(self, world_id: WorldId, import_id: UUID) -> None: ...
    async def accept(
        self, item: AcceptedWorldContent, preview: ImportPreview
    ) -> AcceptedWorldContent: ...
    async def list_common_lore(self, world_id: WorldId) -> tuple[CommonLoreEntry, ...]: ...
    async def set_common_lore(
        self, world_id: WorldId, import_id: UUID, entry_id: UUID, common: bool
    ) -> None: ...


@dataclass(frozen=True)
class PendingWorldContent:
    item: AcceptedWorldContent
    preview: ImportPreview
    expires: float


class WorldContentService:
    """Pending previews are bounded and transient; accepted receipts are durable."""

    def __init__(
        self,
        store: WorldContentStore,
        character_importer: ContentImporter,
        lorebook_importer: ContentImporter,
        normalize_embedded,
        wall_clock,
    ) -> None:
        self.store = store
        self._clock = wall_clock
        self._character = character_importer
        self._lorebook = lorebook_importer
        self._normalize = normalize_embedded
        self._pending: dict[UUID, PendingWorldContent] = {}

    async def prepare(
        self,
        world_id: WorldId,
        kind: ImportKind,
        payload: bytes,
        replaces_import_id: UUID | None = None,
    ) -> PendingWorldContent:
        await self.store.require_world(world_id)
        if replaces_import_id is not None:
            previous = await self.store.find(replaces_import_id)
            if (
                previous is None
                or previous.world_id != world_id
                or previous.kind != kind
                or not await self.store.is_current(replaces_import_id)
            ):
                raise ContentConflictError("Content replacement target is no longer current")
        self._pending = {
            key: value for key, value in self._pending.items() if value.expires > monotonic()
        }
        # At most two 32 MiB uploads pending in one local session.
        if len(self._pending) >= 2:
            raise ContentImportError("preview_capacity_reached")
        if kind not in ("character", "lorebook") or not payload or len(payload) > 32 * 1024 * 1024:
            raise ContentImportError("import_input_invalid")
        importer = self._character if kind == "character" else self._lorebook
        imported: ImportDraft = importer.parse(payload, imported_at=self._clock.now_utc())
        if kind == "character":
            imported = self._normalize(imported)
        preview = imported.preview()
        item = AcceptedWorldContent(
            uuid4(),
            world_id,
            preview.content.preview_hash,
            kind,
            imported.draft.contents,
            replaces_import_id,
        )
        pending = PendingWorldContent(item, preview, monotonic() + 15 * 60)
        self._pending[item.import_id] = pending
        return pending

    async def current(self, world_id: WorldId, import_id: UUID) -> AcceptedWorldContent:
        await self.store.require_world(world_id)
        previous = next(
            (
                item
                for item in await self.store.list_imports(world_id)
                if item.import_id == import_id
            ),
            None,
        )
        if previous is None or not await self.store.is_current(import_id):
            raise ContentConflictError("Content replacement target is no longer current")
        return previous

    async def prepare_draft(
        self,
        world_id: WorldId,
        kind: ImportKind,
        draft: ContentDraft,
        replaces_import_id: UUID | None = None,
    ) -> PendingWorldContent:
        await self.store.require_world(world_id)
        if replaces_import_id is not None:
            previous = await self.current(world_id, replaces_import_id)
            if previous.kind != kind:
                raise ContentConflictError("Content kind mismatch")
        self._pending = {
            key: value for key, value in self._pending.items() if value.expires > monotonic()
        }
        if len(self._pending) >= 2:
            raise ContentImportError("preview_capacity_reached")
        preview = ImportDraft(draft).preview()
        item = AcceptedWorldContent(
            uuid4(),
            world_id,
            preview.content.preview_hash,
            kind,
            draft.contents,
            replaces_import_id,
        )
        pending = PendingWorldContent(item, preview, monotonic() + 15 * 60)
        self._pending[item.import_id] = pending
        return pending

    def discard(self, world_id: WorldId, import_id: UUID) -> None:
        pending = self._pending.get(import_id)
        if pending is not None and pending.item.world_id == world_id:
            del self._pending[import_id]

    async def commit(
        self,
        world_id: WorldId,
        import_id: UUID,
        reviewed_hash: str,
        *,
        initial_location_required=False,
        initial_location_provided=False,
    ) -> AcceptedWorldContent:
        existing = await self.store.find(import_id)
        if existing is not None:
            if existing.world_id != world_id or existing.reviewed_hash != reviewed_hash:
                raise ContentConflictError("Import confirmation mismatch")
            return existing
        pending = self._pending.get(import_id)
        if pending is None or pending.expires <= monotonic():
            raise ContentImportError("preview_expired")
        if pending.item.world_id != world_id or pending.item.reviewed_hash != reviewed_hash:
            raise ContentConflictError("Import confirmation mismatch")
        if (
            initial_location_required
            and pending.item.kind == "character"
            and pending.item.replaces_import_id is None
            and not initial_location_provided
        ):
            raise ContentImportError("character_initial_location_required")
        result = await self.store.accept(pending.item, pending.preview)
        self._pending.pop(import_id, None)
        return result

    async def list_common_lore(self, world_id: WorldId) -> tuple[CommonLoreEntry, ...]:
        return await self.store.list_common_lore(world_id)

    async def set_common_lore(
        self, world_id: WorldId, import_id: UUID, entry_id: UUID, common: bool
    ) -> None:
        await self.store.set_common_lore(world_id, import_id, entry_id, common)
