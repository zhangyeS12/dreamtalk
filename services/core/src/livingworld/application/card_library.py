"""Reviewed card templates; adding one creates independent world-authored content."""

import asyncio
from dataclasses import dataclass, replace
from hashlib import sha256
from time import monotonic
from typing import ClassVar, Literal
from uuid import UUID, uuid4, uuid5

from livingworld.application.card_design import referenced_images
from livingworld.application.content import ContentConflictError, ContentDraft, RawImportEnvelope
from livingworld.application.content_authoring import EditorDraft, authored_graph
from livingworld.application.content_packages import AssetBlobBinding, PackagedBlob
from livingworld.application.errors import EntityNotFoundError
from livingworld.application.file_exports import ExportedFile, export_filename
from livingworld.application.imports import ContentImportError
from livingworld.application.world_covers import MAX_IMAGE_BYTES, CoverError
from livingworld.domain.content.models import (
    CanonicalContent,
    CharacterDefinition,
    ContentProvenance,
    ContentRevision,
    ContentSourceKind,
    LoreCollection,
    LoreEntry,
)
from livingworld.domain.content.serialization import stable_json
from livingworld.domain.identifiers import LocationId, WorldId


@dataclass(frozen=True)
class LibraryCard:
    card_id: UUID
    revision: int
    reviewed_hash: str
    draft: ContentDraft
    design: dict | None = None
    kind: ClassVar[Literal["character"]] = "character"
    replaces_import_id: ClassVar[None] = None

    @property
    def import_id(self) -> UUID:
        return self.card_id

    @property
    def contents(self) -> tuple[CanonicalContent, ...]:
        return self.draft.contents

    @property
    def name(self) -> str:
        return next(x.display_name for x in self.contents if isinstance(x, CharacterDefinition))


@dataclass(frozen=True)
class PendingLibraryCard:
    preview_id: UUID
    card: LibraryCard
    expected_revision: int
    expires: float
    images: tuple[tuple[bytes, dict], ...] = ()
    shared: bool = False


def independent_draft(draft: ContentDraft, namespace: UUID) -> ContentDraft:
    """Only typed authored IDs are remapped; opaque text and immutable evidence stay exact."""
    identities = {
        root.content_id: type(root.content_id)(
            uuid5(namespace, f"{type(root.content_id).__name__}:{root.content_id.value}")
        )
        for root in draft.contents
    }

    copied = []
    for root in draft.contents:
        changes = {"content_id": identities[root.content_id], "revision": ContentRevision()}
        if isinstance(root, LoreEntry):
            changes["collection_id"] = (
                identities[root.collection_id] if root.collection_id else None
            )
        if isinstance(root, (CharacterDefinition, LoreCollection)):
            changes["lore_entry_ids"] = tuple(identities[key] for key in root.lore_entry_ids)
        if isinstance(root, CharacterDefinition):
            changes["lore_collection_ids"] = tuple(
                identities[key] for key in root.lore_collection_ids
            )
        copied.append(replace(root, **changes))

    return ContentDraft(
        contents=tuple(copied),
        assets=draft.assets,
        raw_imports=draft.raw_imports,
    )


class CardLibraryService:
    def __init__(
        self,
        store,
        repository,
        importer,
        normalize,
        clock,
        world_content,
        activities,
        assets,
        processor,
        shares,
    ):
        self.store, self.repository = store, repository
        self.importer, self.normalize, self.clock = importer, normalize, clock
        self.world_content, self.activities = world_content, activities
        self.assets, self.processor = assets, processor
        self.shares = shares
        self._pending: dict[UUID, PendingLibraryCard] = {}
        self._join_lock = asyncio.Lock()
        self._joins: dict[tuple[UUID, UUID], tuple[int, UUID]] = {}
        self._image_lock = asyncio.Lock()

    async def preview(
        self,
        *,
        payload: bytes | None = None,
        editor: EditorDraft | None = None,
        card_id: UUID | None = None,
        expected_revision: int = 0,
    ):
        previous = await self.store.load(card_id) if card_id is not None else None
        if previous is not None and previous.revision != expected_revision:
            raise ContentConflictError("card_library_changed")
        if previous is None and expected_revision != 0:
            raise ContentConflictError("card_library_changed")
        shared = None
        if payload is not None:
            if not payload or len(payload) > 32 * 1024 * 1024:
                raise ContentImportError("import_input_invalid")
            shared = await asyncio.to_thread(self.shares.read, payload)
            draft = (
                shared.draft
                if shared
                else self.normalize(
                    self.importer.parse(payload, imported_at=self.clock.now_utc())
                ).draft
            )
            if shared:
                from livingworld.domain.content.identifiers import RawImportId

                raw_id = RawImportId(uuid4())
                evidence = RawImportEnvelope(
                    import_id=raw_id,
                    provenance=ContentProvenance(
                        source_kind=ContentSourceKind.IMPORT,
                        source_format="chara_card_v3",
                        source_format_version="3.0",
                        imported_at=self.clock.now_utc(),
                        content_hash=sha256(payload).hexdigest(),
                        raw_import_id=raw_id,
                    ),
                    original_payload=payload,
                )
                draft = replace(draft, raw_imports=(*draft.raw_imports, evidence))
        elif editor is not None and editor.kind == "character":
            draft = await authored_graph(editor, previous, self.repository)
            if previous:
                raws = {x.import_id: x for x in (*previous.draft.raw_imports, *draft.raw_imports)}
                draft = replace(draft, raw_imports=tuple(raws.values()))
        else:
            raise ContentImportError("card_library_character_required")
        if len([x for x in draft.contents if isinstance(x, CharacterDefinition)]) != 1:
            raise ContentImportError("card_library_character_required")
        self._pending = {
            key: value for key, value in self._pending.items() if value.expires > monotonic()
        }
        if len(self._pending) >= 2:
            raise ContentImportError("preview_capacity_reached")
        identity = card_id or uuid4()
        # Imported IDs may already exist in another card or an older world import.
        # A library revision owns its authored graph; immutable source bytes stay exact.
        draft = independent_draft(draft, uuid5(identity, f"revision:{expected_revision + 1}"))
        digest = sha256(
            stable_json(
                {
                    "card": str(identity),
                    "revision": expected_revision,
                    "draft": draft.preview_hash(),
                    "design": shared.design if shared else previous.design if previous else None,
                    "images": [info["digest"] for _, info in shared.images] if shared else [],
                }
            ).encode()
        ).hexdigest()
        card = LibraryCard(
            identity,
            expected_revision + 1,
            digest,
            draft,
            shared.design if shared else previous.design if previous else None,
        )
        pending = PendingLibraryCard(
            uuid4(),
            card,
            expected_revision,
            monotonic() + 900,
            shared.images if shared else (),
            shared is not None,
        )
        self._pending[pending.preview_id] = pending
        return pending

    async def commit(self, preview_id, card_id, reviewed_hash):
        existing = await self.store.find(card_id)
        if existing is not None and existing.reviewed_hash == reviewed_hash:
            return existing
        pending = self._pending.get(preview_id)
        if pending is None or pending.expires <= monotonic():
            raise ContentImportError("preview_expired")
        if pending.card.card_id != card_id or pending.card.reviewed_hash != reviewed_hash:
            raise ContentConflictError("card_library_review_changed")
        for data, info in pending.images:
            await self.assets.materialize(
                PackagedBlob(
                    self._binding(card_id, info["digest"], info["size"]),
                    data,
                )
            )
        await self.store.save(
            pending.card, pending.expected_revision, tuple(info for _, info in pending.images)
        )
        self._pending.pop(preview_id, None)
        return await self.store.load(card_id)

    def discard(self, preview_id):
        self._pending.pop(preview_id, None)

    async def remove(self, card_id, revision):
        async with self._join_lock, self._image_lock:
            result = await self.store.remove(card_id, revision)
            self._pending = {
                key: value for key, value in self._pending.items() if value.card.card_id != card_id
            }
            self._joins = {key: value for key, value in self._joins.items() if key[0] != card_id}
            return result

    def preview_image(self, preview_id, digest):
        pending = self._pending.get(preview_id)
        if pending is None or pending.expires <= monotonic():
            raise ContentImportError("preview_expired")
        for data, info in pending.images:
            if info["digest"] == digest:
                return data, info
        raise EntityNotFoundError("card_library_image_not_found")

    async def export(self, card_id, revision):
        card = await self.store.load(card_id)
        if card.revision != revision:
            raise ContentConflictError("card_library_changed")
        images = {
            digest: await self.image(card_id, digest) for digest in referenced_images(card.design)
        }
        payload = await asyncio.to_thread(self.shares.write, card, images)
        if (await self.store.load(card_id)).revision != revision:
            raise ContentConflictError("card_library_changed")
        return ExportedFile(export_filename(card.name, "-角色卡.charx"), payload, "application/zip")

    async def prepare_join(self, card_id, world_id, expected_revision):
        async with self._join_lock:
            card = await self.store.load(card_id)
            if card.revision != expected_revision:
                raise ContentConflictError("card_library_changed")
            existing = await self.store.world_link(card_id, world_id)
            if existing is not None and existing["active"]:
                raise ContentConflictError("card_library_already_added")
            key = (card_id, world_id.value)
            self._joins = {
                key: value
                for key, value in self._joins.items()
                if self.world_content.pending(WorldId(key[1]), value[1]) is not None
            }
            cached = self._joins.get(key)
            if cached and cached[0] == card.revision:
                pending = self.world_content.pending(world_id, cached[1])
                if pending:
                    return pending
            identity = (
                uuid5(existing["import_id"], "card-library-rejoin:v1")
                if existing
                else uuid5(card_id, f"card-library-world:v1:{world_id.value}")
            )
            pending = await self.world_content.prepare_draft(
                world_id,
                "character",
                independent_draft(card.draft, identity),
                import_id=identity,
                library_card_id=card_id,
                library_card_revision=card.revision,
            )
            self._joins[key] = (card.revision, identity)
            return pending

    async def commit_join(self, card_id, world_id, import_id, reviewed_hash, location_id):
        await self.store.load(card_id)
        pending = self.world_content.pending(world_id, import_id)
        link = await self.store.world_link(card_id, world_id)
        if pending is not None:
            if pending.item.library_card_id != card_id:
                raise ContentConflictError("card_library_review_changed")
        elif link is None or link["import_id"] != import_id or not link["active"]:
            raise ContentConflictError("card_library_review_changed")
        saved = await self.world_content.commit(world_id, import_id, reviewed_hash)
        try:
            await self.activities.initialize_card(
                world_id,
                saved.import_id,
                LocationId(world_id, location_id) if location_id is not None else None,
            )
        except Exception:
            # The accepted authored snapshot and origin link are durable. The
            # same confirmation can finish placement without making another copy.
            raise ContentConflictError("card_library_location_pending") from None
        return saved

    async def save_design(self, card_id, revision, design):
        await self.store.load(card_id)
        for face in (design["front"], design["back"]):
            for digest in {face.get("image_digest"), face.get("source_digest")} - {None}:
                await self.store.image(card_id, digest)
        return await self.store.save_design(card_id, revision, design)

    def _binding(self, card_id, digest, size):
        from livingworld.domain.content.identifiers import ContentAssetId

        return AssetBlobBinding(
            ContentAssetId(uuid5(card_id, "card-library-image:" + digest)), digest, size
        )

    async def _store_image(self, card_id, data, info):
        image = {**info, "digest": sha256(data).hexdigest(), "size": len(data)}
        await self.assets.materialize(
            PackagedBlob(self._binding(card_id, image["digest"], image["size"]), data)
        )
        await self.store.add_image(card_id, image)
        return image

    async def upload(self, card_id, data):
        await self.store.load(card_id)
        if not data or len(data) > MAX_IMAGE_BYTES:
            raise CoverError("cover_image_size_limit")
        async with self._image_lock:
            info = await asyncio.to_thread(self.processor.inspect, data)
            return await self._store_image(card_id, data, info)

    async def image(self, card_id, digest):
        info = await self.store.image(card_id, digest)
        return await self.assets.read(self._binding(card_id, digest, info["size"])), info

    async def crop(self, card_id, digest, crop):
        data, _ = await self.image(card_id, digest)
        async with self._image_lock:
            rendered = await asyncio.to_thread(self.processor.render, data, crop, (1200, 757))
            return await self._store_image(
                card_id, rendered, {"media_type": "image/webp", "width": 1200, "height": 757}
            )
