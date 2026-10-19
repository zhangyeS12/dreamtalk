"""Authenticated author preview/confirm endpoints for the selected world's player."""

from collections.abc import Callable
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field

from livingworld.application.player_persona import (
    PersonaSourcePage,
    PlayerPersonaDraft,
    PlayerPersonaError,
    PlayerPersonaPreview,
    PlayerPersonaService,
    PlayerPersonaSnapshot,
)
from livingworld.domain.contracts import API_PROTOCOL
from livingworld.domain.identifiers import WorldId


class PersonaPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    draft: PlayerPersonaDraft
    expected_revision: int = Field(ge=0, strict=True)
    expected_player_id: UUID


class PersonaCommitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preview_id: UUID
    confirmed: Literal[True]


class PersonaRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def validated(request: Request):
            try:
                return await handler(request)
            except RequestValidationError:
                # Do not echo private opening knowledge or malformed Unicode input.
                return JSONResponse(status_code=422, content={"detail": "persona_input_invalid"})

        return validated


def player_persona_router(service: PlayerPersonaService, authorize: Callable[..., None]):
    router = APIRouter(
        prefix=f"/api/v{API_PROTOCOL}/worlds/{{world_id}}/me/persona",
        dependencies=[Depends(authorize)],
        route_class=PersonaRoute,
    )

    def failure(error: PlayerPersonaError):
        code = str(error)
        status = (
            404
            if code == "world_not_found"
            else 409
            if code
            in {
                "persona_edit_conflict",
                "persona_player_changed",
                "persona_source_changed",
                "persona_character_changed",
                "persona_preview_expired",
            }
            else 422
        )
        return HTTPException(status, code)

    @router.get("")
    async def read(world_id: UUID) -> PlayerPersonaSnapshot:
        try:
            return await service.store.snapshot(WorldId(world_id))
        except PlayerPersonaError as error:
            raise failure(error) from None

    @router.get("/sources")
    async def sources(
        world_id: UUID,
        query: str = Query(default="", max_length=120),
        after: str | None = Query(default=None, max_length=80),
        characters: bool = False,
    ) -> PersonaSourcePage:
        try:
            return await service.store.sources(
                WorldId(world_id), query, after, characters=characters
            )
        except PlayerPersonaError as error:
            raise failure(error) from None

    @router.post("/preview")
    async def preview(world_id: UUID, body: PersonaPreviewRequest) -> PlayerPersonaPreview:
        try:
            return await service.preview(
                WorldId(world_id),
                body.draft,
                body.expected_revision,
                expected_player=body.expected_player_id,
            )
        except PlayerPersonaError as error:
            raise failure(error) from None

    @router.post("/commit")
    async def commit(world_id: UUID, body: PersonaCommitRequest) -> PlayerPersonaSnapshot:
        try:
            return await service.commit(WorldId(world_id), body.preview_id)
        except PlayerPersonaError as error:
            raise failure(error) from None

    return router
