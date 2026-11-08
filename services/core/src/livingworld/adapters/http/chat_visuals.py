"""Authenticated world-scoped chat visual bindings."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from livingworld.adapters.http.wire_contracts import chat_visuals as wire
from livingworld.application.chat_visuals import ChatVisualService
from livingworld.application.errors import EntityNotFoundError
from livingworld.domain.contracts import API_PROTOCOL
from livingworld.domain.identifiers import WorldId


class BackgroundWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class CharacterBackgroundWrite(BackgroundWrite):
    root_import_id: UUID


class ExpressionWrite(BackgroundWrite):
    root_import_id: UUID
    expression: Literal[
        "neutral",
        "joy",
        "content",
        "sad",
        "angry",
        "surprised",
        "scared",
        "disgusted",
        "confused",
        "love",
        "embarrassed",
        "thinking",
    ]


def _view(value):
    return {
        "common_background_digest": value.common_background_digest,
        "character_backgrounds": {
            str(root): digest for root, digest in value.character_backgrounds.items()
        },
        "expressions": [
            {
                "root_import_id": str(item.root_import_id),
                "expression": item.expression,
                "digest": item.digest,
            }
            for item in value.expressions
        ],
    }


def create_chat_visual_router(service: ChatVisualService, authorize):
    router = APIRouter(
        prefix=f"/api/v{API_PROTOCOL}/worlds/{{world_id}}/chat-visuals",
        dependencies=[Depends(authorize)],
    )

    async def call(operation):
        try:
            return await operation
        except EntityNotFoundError as error:
            raise HTTPException(404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(422, detail=str(error)) from error

    @router.get("", response_model=wire.ChatVisuals)
    async def read(world_id: UUID):
        return _view(await call(service.load(WorldId(world_id))))

    @router.put("/background", response_model=wire.ChatVisuals)
    async def set_common(world_id: UUID, body: BackgroundWrite):
        return _view(await call(service.set_common_background(WorldId(world_id), body.digest)))

    @router.put("/character-background", response_model=wire.ChatVisuals)
    async def set_character(world_id: UUID, body: CharacterBackgroundWrite):
        return _view(
            await call(
                service.set_character_background(
                    WorldId(world_id), body.root_import_id, body.digest
                )
            )
        )

    @router.put("/expression", response_model=wire.ChatVisuals)
    async def set_expression(world_id: UUID, body: ExpressionWrite):
        return _view(
            await call(
                service.set_expression(
                    WorldId(world_id), body.root_import_id, body.expression, body.digest
                )
            )
        )

    return router
