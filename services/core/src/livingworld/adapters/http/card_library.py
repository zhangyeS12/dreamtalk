"""Authenticated local card authoring, presentation and explicit world placement."""

import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import Field

from livingworld.adapters.http import contracts as wire
from livingworld.adapters.http.content_editor_pages import EditorPatchRequest
from livingworld.adapters.http.wire_contracts import card_library as dto
from livingworld.adapters.http.wire_contracts.card_packs import LibraryCardRemoval
from livingworld.adapters.http.world_content import _view
from livingworld.application.card_design import DesignWrite, ImageCropWrite, Strict
from livingworld.application.content import ContentConflictError
from livingworld.application.content_authoring import EditorDraft
from livingworld.application.content_editor_pages import header_fields, merge_editor_patch
from livingworld.application.content_packages import PackageError
from livingworld.application.errors import EntityNotFoundError
from livingworld.application.exports import ContentExportError
from livingworld.application.file_exports import attachment_headers
from livingworld.application.imports import ContentImportError, ImportDraft
from livingworld.application.world_covers import CoverCrop, CoverError
from livingworld.domain.contracts import API_PROTOCOL
from livingworld.domain.errors import DomainInvariantError
from livingworld.domain.identifiers import WorldId


class EditorPreview(Strict):
    draft: EditorDraft
    card_id: UUID | None = None
    expected_revision: int = Field(default=0, ge=0, strict=True)


class Review(Strict):
    card_id: UUID
    reviewed_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class DesignSave(Strict):
    expected_revision: int = Field(ge=1, strict=True)
    design: DesignWrite


class JoinPreview(Strict):
    expected_revision: int = Field(ge=1, strict=True)


class CardDelete(Strict):
    expected_revision: int = Field(ge=1, strict=True)


class JoinConfirm(Strict):
    import_id: UUID
    reviewed_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    initial_location_id: UUID | None = None


def card_library_router(service, authorize):
    router = APIRouter(
        prefix=f"/api/v{API_PROTOCOL}/card-library", dependencies=[Depends(authorize)]
    )

    async def call(awaitable):
        try:
            return await awaitable
        except EntityNotFoundError:
            raise HTTPException(404, "card_library_target_unavailable") from None
        except ContentConflictError as error:
            code = str(error)
            raise HTTPException(
                409, code if code.startswith("card_library_") else "card_library_changed"
            ) from None
        except ContentImportError as error:
            raise HTTPException(422, error.code) from None
        except (ContentExportError, PackageError):
            raise HTTPException(422, "card_share_invalid") from None
        except CoverError as error:
            raise HTTPException(422, str(error)) from None
        except DomainInvariantError:
            raise HTTPException(422, "card_library_invalid") from None

    async def bounded(request, maximum):
        data = bytearray()
        async for chunk in request.stream():
            if len(data) + len(chunk) > maximum:
                raise HTTPException(413, "card_library_upload_too_large")
            data.extend(chunk)
        return bytes(data)

    def preview_view(pending):
        return {
            "preview_id": str(pending.preview_id),
            "card_id": str(pending.card.card_id),
            "expected_revision": pending.expected_revision,
            "reviewed_hash": pending.card.reviewed_hash,
            "shared": pending.shared,
            "design": pending.card.design,
            "image_count": len(pending.images),
            "content": {
                **_view(pending.card),
                "warnings": [
                    {"code": warning.code, "path": warning.path}
                    for warning in ImportDraft(pending.card.draft).warnings
                ],
            },
        }

    @router.get("", response_model=list[dto.LibraryCardItem])
    async def list_cards():
        return await call(service.store.list())

    @router.delete("/{card_id}", response_model=LibraryCardRemoval)
    async def remove(card_id: UUID, body: CardDelete):
        return await call(service.remove(card_id, body.expected_revision))

    @router.post("/import/preview", response_model=dto.LibraryCardPreview)
    async def import_preview(request: Request):
        return preview_view(
            await call(service.preview(payload=await bounded(request, 32 * 1024 * 1024)))
        )

    @router.post("/editor/preview", response_model=dto.LibraryCardPreview)
    async def editor_preview(body: EditorPreview):
        return preview_view(
            await call(
                service.preview(
                    editor=body.draft,
                    card_id=body.card_id,
                    expected_revision=body.expected_revision,
                )
            )
        )

    @router.post("/previews/{preview_id}/commit", response_model=dto.LibraryCardItem)
    async def confirm(preview_id: UUID, body: Review):
        saved = await call(service.commit(preview_id, body.card_id, body.reviewed_hash))
        return await call(service.store.summary(saved.card_id))

    @router.post("/previews/{preview_id}/discard", response_model=wire.DiscardWorldContentResult)
    async def discard(preview_id: UUID):
        service.discard(preview_id)
        return {"discarded": True}

    @router.get("/previews/{preview_id}/images/{digest}", response_class=Response)
    async def preview_image(preview_id: UUID, digest: str) -> Response:
        try:
            data, info = service.preview_image(preview_id, digest)
        except ContentImportError as error:
            raise HTTPException(422, error.code) from None
        except EntityNotFoundError:
            raise HTTPException(404, "card_library_image_not_found") from None
        return Response(
            data,
            media_type=info["media_type"],
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    @router.get("/{card_id}/export/info", response_model=wire.ContentExportInfo)
    async def export_info(card_id: UUID, expected_revision: int = Query(ge=1)):
        result = await call(service.export(card_id, expected_revision))
        return {
            "filename": result.filename,
            "digest": result.digest,
            "size": len(result.payload),
            "warnings": [],
        }

    @router.get("/{card_id}/export", response_class=Response)
    async def export(
        card_id: UUID,
        expected_revision: int = Query(ge=1),
        expected_digest: str = Query(pattern=r"^[a-f0-9]{64}$"),
    ) -> Response:
        result = await call(service.export(card_id, expected_revision))
        if result.digest != expected_digest:
            raise HTTPException(409, "card_library_changed")
        return Response(
            result.payload,
            media_type=result.media_type,
            headers=attachment_headers(result.filename),
        )

    @router.get("/{card_id}", response_model=dto.LibraryCardRead)
    async def read(card_id: UUID):
        card = await call(service.store.load(card_id))
        return {
            "card": await call(service.store.summary(card_id)),
            "draft": header_fields(card),
        }

    @router.post("/{card_id}/editor/preview-changes", response_model=dto.LibraryCardPreview)
    async def preview_changes(
        card_id: UUID, body: EditorPatchRequest, expected_revision: int = Query(ge=1)
    ):
        card = await call(service.store.load(card_id))
        try:
            fields = merge_editor_patch(
                card,
                body.fields.model_dump(exclude_unset=True),
                [
                    (item.source_entry_id, item.fields.model_dump(exclude_unset=True))
                    for item in body.updates
                ],
                body.removed,
                body.added,
            )
        except ContentImportError as error:
            raise HTTPException(422, error.code) from None
        return preview_view(
            await call(
                service.preview(editor=fields, card_id=card_id, expected_revision=expected_revision)
            )
        )

    @router.put("/{card_id}/design", response_model=dto.LibraryCardItem)
    async def design(card_id: UUID, body: DesignSave):
        return await call(
            service.save_design(card_id, body.expected_revision, body.design.model_dump())
        )

    @router.post("/{card_id}/images", response_model=wire.CoverImage)
    async def upload(card_id: UUID, request: Request):
        await call(service.store.load(card_id))
        return await call(service.upload(card_id, await bounded(request, 10 * 1024 * 1024)))

    @router.get("/{card_id}/images/{digest}", response_class=Response)
    async def image(card_id: UUID, digest: str) -> Response:
        if not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise HTTPException(404, "card_library_image_not_found")
        data, info = await call(service.image(card_id, digest))
        return Response(
            data,
            media_type=info["media_type"],
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    @router.post("/{card_id}/images/{digest}/crop", response_model=wire.CoverImage)
    async def crop(card_id: UUID, digest: str, body: ImageCropWrite):
        if not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise HTTPException(404, "card_library_image_not_found")
        return await call(service.crop(card_id, digest, CoverCrop(**body.model_dump())))

    @router.post("/{card_id}/worlds/{world_id}/preview", response_model=dto.LibraryCardJoinPreview)
    async def prepare_join(card_id: UUID, world_id: UUID, body: JoinPreview):
        pending = await call(
            service.prepare_join(card_id, WorldId(world_id), body.expected_revision)
        )
        return {
            "card_id": str(card_id),
            "source_revision": pending.item.library_card_revision,
            "content": {
                **_view(pending.item),
                "warnings": [
                    {"code": warning.code, "path": warning.path}
                    for warning in pending.preview.warnings
                ],
            },
        }

    @router.post("/{card_id}/worlds/{world_id}/commit", response_model=wire.WorldContentItem)
    async def commit_join(card_id: UUID, world_id: UUID, body: JoinConfirm):
        saved = await call(
            service.commit_join(
                card_id,
                WorldId(world_id),
                body.import_id,
                body.reviewed_hash,
                body.initial_location_id,
            )
        )
        return _view(saved)

    return router
