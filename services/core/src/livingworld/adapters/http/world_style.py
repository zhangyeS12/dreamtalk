"""Authenticated world-style draft, preview and confirmation."""

from collections.abc import Callable
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, field_validator

from livingworld.adapters.http.wire_contracts.world_style import (
    WorldStylePreview,
    WorldStyleSnapshot,
)
from livingworld.application.errors import EntityNotFoundError
from livingworld.application.world_style import WorldStyleService, style_preview_id
from livingworld.domain.contracts import API_PROTOCOL
from livingworld.domain.errors import ConcurrencyConflictError
from livingworld.domain.identifiers import WorldId


class StyleDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instructions: str = Field(max_length=4000, strict=True)
    expected_revision: int = Field(ge=0, strict=True)


class StyleConfirm(StyleDraft):
    preview_id: str = Field(pattern="^[0-9a-f]{64}$")
    confirmed: Literal[True]

    @field_validator("confirmed", mode="before")
    @classmethod
    def explicit_confirmation(cls, value):
        if value is not True:
            raise ValueError("world_style_confirmation_required")
        return value


class StyleRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def validated(request):
            try:
                return await handler(request)
            except RequestValidationError:
                return JSONResponse(status_code=422, content={"detail": "world_style_invalid"})

        return validated


def world_style_router(service: WorldStyleService, authorize: Callable[..., None]) -> APIRouter:
    router = APIRouter(
        prefix=f"/api/v{API_PROTOCOL}/worlds/{{world_id}}/style",
        dependencies=[Depends(authorize)],
        route_class=StyleRoute,
    )

    def fail(error: Exception):
        code = str(error)
        status = (
            404
            if isinstance(error, EntityNotFoundError)
            else 409
            if isinstance(error, ConcurrencyConflictError)
            else 422
        )
        return HTTPException(status, code)

    @router.get("")
    async def read(world_id: UUID) -> WorldStyleSnapshot:
        try:
            style = await service.store.load(WorldId(world_id))
            return {"instructions": style.instructions, "revision": style.revision}
        except EntityNotFoundError as error:
            raise fail(error) from None

    @router.post("/preview")
    async def preview(world_id: UUID, body: StyleDraft) -> WorldStylePreview:
        world = WorldId(world_id)
        try:
            style = await service.preview(world, body.instructions, body.expected_revision)
            return {
                "instructions": style.instructions,
                "revision": style.revision,
                "preview_id": style_preview_id(world, style),
            }
        except (EntityNotFoundError, ConcurrencyConflictError, ValueError) as error:
            raise fail(error) from None

    @router.post("/commit")
    async def commit(world_id: UUID, body: StyleConfirm) -> WorldStyleSnapshot:
        try:
            style = await service.confirm(
                WorldId(world_id), body.instructions, body.expected_revision, body.preview_id
            )
            return {"instructions": style.instructions, "revision": style.revision}
        except (EntityNotFoundError, ConcurrencyConflictError, ValueError) as error:
            raise fail(error) from None

    return router
