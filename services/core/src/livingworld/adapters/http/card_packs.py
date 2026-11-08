"""Authenticated local pack metadata and bounded same-owner image operations."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response
from pydantic import Field, ValidationError

from livingworld.adapters.http import contracts as wire
from livingworld.adapters.http.wire_contracts.card_packs import CharacterPack
from livingworld.application.card_design import ImageCropWrite, PackDesignWrite, Strict
from livingworld.application.content import ContentConflictError
from livingworld.application.errors import EntityNotFoundError
from livingworld.application.world_covers import CoverCrop, CoverError
from livingworld.domain.contracts import API_PROTOCOL


class PackSave(Strict):
    expected_revision: int = Field(ge=0, strict=True)
    name: str = Field(min_length=1, max_length=60)
    subtitle: str = Field(max_length=120)
    cardIds: list[UUID] = Field(max_length=1024)
    design: PackDesignWrite


class IncludeCard(Strict):
    expected_revision: int = Field(ge=1, strict=True)


class PackDelete(Strict):
    expected_revision: int = Field(ge=1, strict=True)


def card_packs_router(service, authorize):
    router = APIRouter(prefix=f"/api/v{API_PROTOCOL}/card-packs", dependencies=[Depends(authorize)])

    async def call(awaitable):
        try:
            return await awaitable
        except EntityNotFoundError:
            raise HTTPException(404, "card_pack_target_unavailable") from None
        except ContentConflictError:
            raise HTTPException(409, "card_pack_changed") from None
        except (CoverError, ValidationError) as error:
            raise HTTPException(
                422, str(error) if isinstance(error, CoverError) else "card_pack_invalid"
            ) from None

    @router.get("", response_model=list[CharacterPack])
    async def list_packs():
        return await call(service.store.list())

    @router.delete("/{pack_id}", response_model=wire.RemoveStickerResult)
    async def remove(pack_id: UUID, body: PackDelete):
        return await call(service.remove(pack_id, body.expected_revision))

    @router.put("/{pack_id}", response_model=CharacterPack)
    async def save(pack_id: UUID, body: PackSave):
        if not body.name.strip():
            raise HTTPException(422, "card_pack_invalid")
        return await call(
            service.save(
                pack_id,
                body.expected_revision,
                body.name,
                body.subtitle,
                body.cardIds,
                body.design.model_dump(),
            )
        )

    @router.put("/{pack_id}/members/{card_id}", response_model=CharacterPack)
    async def include(pack_id: UUID, card_id: UUID, body: IncludeCard):
        return await call(service.store.include(pack_id, card_id, body.expected_revision))

    @router.post("/{pack_id}/images", response_model=wire.CoverImage)
    async def upload(pack_id: UUID, request: Request):
        data = bytearray()
        async for chunk in request.stream():
            if len(data) + len(chunk) > 10 * 1024 * 1024:
                raise HTTPException(413, "cover_image_size_limit")
            data.extend(chunk)
        return await call(service.upload(pack_id, bytes(data)))

    @router.get("/{pack_id}/images/{digest}", response_class=Response)
    async def image(pack_id: UUID, digest: str = Path(pattern=r"^[a-f0-9]{64}$")) -> Response:
        data, info = await call(service.image(pack_id, digest))
        return Response(
            data,
            media_type=info["media_type"],
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    @router.post("/{pack_id}/images/{digest}/crop", response_model=wire.CoverImage)
    async def crop(
        pack_id: UUID, body: ImageCropWrite, digest: str = Path(pattern=r"^[a-f0-9]{64}$")
    ):
        return await call(service.crop(pack_id, digest, CoverCrop(**body.model_dump())))

    @router.post("/{pack_id}/discard", response_model=wire.DiscardWorldContentResult)
    async def discard(pack_id: UUID):
        service.discard(pack_id)
        return {"discarded": True}

    return router
