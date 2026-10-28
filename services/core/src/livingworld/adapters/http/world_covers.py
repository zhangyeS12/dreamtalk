"""Authenticated local image and presentation endpoints, with bounded uploads."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

from livingworld.adapters.http import contracts as wire
from livingworld.application.errors import EntityNotFoundError
from livingworld.application.world_covers import MAX_IMAGE_BYTES, CoverCrop, CoverError
from livingworld.domain.contracts import API_PROTOCOL
from livingworld.domain.errors import ConcurrencyConflictError
from livingworld.domain.identifiers import WorldId


class CropWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    x: float = Field(ge=0, le=100)
    y: float = Field(ge=0, le=100)
    width: float = Field(gt=0, le=100)
    height: float = Field(gt=0, le=100)
    rotation: Literal[0, 90, 180, 270] = 0


class FaceWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    crop: CropWrite


HEX_COLOR = r"^#[0-9a-fA-F]{6}$"
DIGEST = r"^[0-9a-f]{64}$"
BUILTIN_STICKERS = ("star", "moon", "sun", "seal", "ribbon", "film", "sakura", "tape", "heart")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class DesignTitleWrite(_Strict):
    text: str = Field(max_length=60)
    font: Literal["yahei", "hei", "song", "kai", "fangsong"]
    color: str = Field(pattern=HEX_COLOR)
    size: float = Field(ge=12, le=96)
    vertical: bool = Field(strict=True)
    x: float = Field(ge=0, le=100)
    y: float = Field(ge=0, le=100)


class DesignSkyWindowWrite(_Strict):
    on: bool = Field(strict=True)
    x: float = Field(ge=0, le=100)
    y: float = Field(ge=0, le=100)
    w: float = Field(ge=4, le=100)
    h: float = Field(ge=4, le=100)


class DesignStickerWrite(_Strict):
    kind: Literal["builtin", "image"]
    ref: str = Field(max_length=64)
    x: float = Field(ge=-20, le=120)
    y: float = Field(ge=-20, le=120)
    w: float = Field(ge=2, le=160)
    r: float = Field(ge=-720, le=720)
    opacity: float = Field(ge=0.1, le=1)

    @model_validator(mode="after")
    def _reference(self):
        import re

        if self.kind == "builtin" and self.ref not in BUILTIN_STICKERS:
            raise ValueError("cover_sticker_unknown")
        if self.kind == "image" and not re.fullmatch(DIGEST, self.ref):
            raise ValueError("cover_sticker_invalid")
        return self


class DesignStickersWrite(_Strict):
    front: list[DesignStickerWrite] = Field(max_length=24)
    spine: list[DesignStickerWrite] = Field(max_length=12)
    back: list[DesignStickerWrite] = Field(max_length=24)


class BookDesignWrite(_Strict):
    """A bounded, local-only book appearance. It never reaches models or world truth."""

    version: Literal[1]
    template: str = Field(max_length=24)
    material: Literal["paper", "cloth", "leather", "gloss", "holo"]
    case_color: str = Field(pattern=HEX_COLOR)
    edge: Literal["paper", "gilt"]
    thickness: Literal["thin", "normal", "thick"]
    wrap: bool = Field(strict=True)
    brand: bool = Field(strict=True)
    title: DesignTitleWrite
    sky_window: DesignSkyWindowWrite
    stickers: DesignStickersWrite


class CoverWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["text", "image"]
    title: str = Field(max_length=120)
    show_title: bool = Field(strict=True)
    faces: dict[Literal["front", "spine", "back"], FaceWrite] = Field(max_length=3)
    expected_revision: int = Field(ge=0, strict=True)
    design: BookDesignWrite | None = None


def create_world_cover_router(service, authorize):
    router = APIRouter(prefix=f"/api/v{API_PROTOCOL}", dependencies=[Depends(authorize)])

    async def call(operation):
        try:
            return await operation
        except EntityNotFoundError as error:
            raise HTTPException(404, detail=str(error)) from error
        except ConcurrencyConflictError as error:
            raise HTTPException(409, detail="cover_edit_conflict") from error
        except CoverError as error:
            raise HTTPException(422, detail=str(error)) from error

    @router.get("/world-covers", response_model=list[wire.WorldCover])
    async def list_covers():
        return await call(service.list_covers())

    @router.get("/worlds/{world_id}/cover", response_model=wire.WorldCover)
    async def load(world_id: UUID):
        return await call(service.load(WorldId(world_id)))

    @router.put("/worlds/{world_id}/cover", response_model=wire.WorldCover)
    async def save(world_id: UUID, body: CoverWrite):
        # A designed book may carry its title as a layer, or deliberately none.
        if body.design is None and body.mode == "text" and not body.title.strip():
            raise HTTPException(422, detail="cover_title_required")
        faces = {
            name: (face.source_digest, CoverCrop(**face.crop.model_dump()))
            for name, face in body.faces.items()
        }
        return await call(
            service.save(
                WorldId(world_id),
                body.mode,
                body.title,
                body.show_title,
                faces,
                body.expected_revision,
                body.design.model_dump() if body.design else None,
            )
        )

    @router.post("/worlds/{world_id}/cover/images", response_model=wire.CoverImage)
    async def upload(world_id: UUID, request: Request):
        if request.headers.get("content-type", "").split(";", 1)[0] not in {
            "image/jpeg",
            "image/png",
            "image/webp",
            "application/octet-stream",
        }:
            raise HTTPException(415, detail="cover_image_format")
        # Validate identity before accepting the body; never trust Content-Length alone.
        await call(service.load(WorldId(world_id)))
        data = bytearray()
        async for chunk in request.stream():
            if len(data) + len(chunk) > MAX_IMAGE_BYTES:
                raise HTTPException(413, detail="cover_image_size_limit")
            data.extend(chunk)
        return await call(service.upload(WorldId(world_id), bytes(data)))

    @router.get("/worlds/{world_id}/cover/images/{digest}")
    async def image(world_id: UUID, digest: str):
        import re

        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise HTTPException(404, detail="cover_image_not_found")
        data, info = await call(service.image(WorldId(world_id), digest))
        return Response(
            data,
            media_type=info["media_type"],
            headers={
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    return router
