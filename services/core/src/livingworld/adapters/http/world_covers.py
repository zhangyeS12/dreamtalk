"""Authenticated local image and presentation endpoints, with bounded uploads."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

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


class CoverWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["text", "image"]
    title: str = Field(min_length=1, max_length=120)
    show_title: bool = Field(strict=True)
    faces: dict[Literal["front", "spine", "back"], FaceWrite] = Field(max_length=3)
    expected_revision: int = Field(ge=0, strict=True)


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

    @router.get("/world-covers")
    async def list_covers():
        return await call(service.list_covers())

    @router.get("/worlds/{world_id}/cover")
    async def load(world_id: UUID):
        return await call(service.load(WorldId(world_id)))

    @router.put("/worlds/{world_id}/cover")
    async def save(world_id: UUID, body: CoverWrite):
        if not body.title.strip():
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
            )
        )

    @router.post("/worlds/{world_id}/cover/images")
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
