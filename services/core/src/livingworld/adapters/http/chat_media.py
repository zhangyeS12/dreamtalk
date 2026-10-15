"""Authenticated management and media reads; no provider calls during configuration."""

import asyncio
from typing import Literal
from urllib.parse import unquote
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from livingworld.application.chat_media import MediaError, MediaSettings
from livingworld.domain.contracts import API_PROTOCOL
from livingworld.infrastructure.media_providers import (
    MAX_IMAGE_BYTES,
    inspect_image,
    validate_caption_endpoint,
)


class StickerEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str = Field(max_length=200)


def chat_media_router(service, authorize):
    router = APIRouter(
        prefix=f"/api/v{API_PROTOCOL}/worlds/{{world_id}}/media",
        dependencies=[Depends(authorize)],
    )

    @router.get("/settings")
    async def settings(world_id: UUID):
        return (await service.store.settings(world_id)).model_dump()

    @router.put("/settings")
    async def save_settings(world_id: UUID, body: MediaSettings):
        validate_caption_endpoint(body)
        await service.providers.wait_for_credential(world_id, body)
        if (
            body.caption_route == "compatible"
            and body.auto_caption
            and not body.remote_caption_consent
        ):
            raise MediaError("media_caption_consent_required")
        return (await service.store.save_settings(world_id, body)).model_dump()

    @router.get("/usage")
    async def usage(world_id: UUID):
        return await service.store.usage(world_id)

    @router.get("/stickers")
    async def stickers(
        world_id: UUID,
        library: Literal["personal", "public", "character"],
        root: UUID | None = None,
        offset: int = Query(default=0, ge=0),
        query: str = Query(default="", max_length=100),
    ):
        return await service.store.entries(world_id, library, root, offset, query)

    @router.post("/stickers", status_code=201)
    async def import_sticker(
        world_id: UUID,
        request: Request,
        library: Literal["personal", "public", "character"],
        root: UUID | None = None,
        x_media_description: str = Header(default=""),
    ):
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > MAX_IMAGE_BYTES:
                raise MediaError("media_image_size_limit")
        mime = await asyncio.to_thread(inspect_image, bytes(data))
        description = unquote(x_media_description).strip()[:200]
        result = await service.store.import_sticker(
            world_id, library, root, bytes(data), mime, description
        )
        settings = await service.store.settings(world_id)
        if settings.auto_caption and result["caption_state"] == "new":
            try:
                result["description"] = await service.caption(
                    world_id, UUID(result["asset_id"]), entry_id=UUID(result["entry_id"])
                )
                result["caption_state"] = "done"
            except MediaError:
                result["caption_state"] = "failed"
        return result

    @router.patch("/stickers/{entry_id}")
    async def edit_sticker(world_id: UUID, entry_id: UUID, body: StickerEdit):
        await service.store.edit_entry(world_id, entry_id, body.description)
        return {"saved": True}

    @router.delete("/stickers/{entry_id}")
    async def remove_sticker(world_id: UUID, entry_id: UUID):
        await service.store.edit_entry(world_id, entry_id, remove=True)
        return {"removed": True}

    @router.get("/assets/{asset_id}")
    async def image(world_id: UUID, asset_id: UUID):
        data, mime = await service.store.asset(world_id, asset_id)
        return Response(
            data,
            media_type=mime,
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    @router.post("/assets/{asset_id}/caption")
    async def caption(world_id: UUID, asset_id: UUID, entry_id: UUID | None = None):
        return {
            "description": await service.caption(world_id, asset_id, retry=True, entry_id=entry_id)
        }

    return router


async def media_error_handler(request, error):
    from fastapi.responses import JSONResponse

    del request
    code = str(error)
    return JSONResponse(
        status_code=404
        if code
        in {
            "world_not_found",
            "media_asset_unavailable",
            "media_character_unavailable",
            "media_sticker_unavailable",
        }
        else 422,
        content={"detail": code},
    )
