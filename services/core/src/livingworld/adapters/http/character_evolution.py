"""Authenticated reversible character-card evolution endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from livingworld.adapters.http import contracts as wire
from livingworld.application.errors import EntityNotFoundError
from livingworld.domain.contracts import API_PROTOCOL
from livingworld.domain.identifiers import WorldId


class EvolutionChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str = Field(min_length=1, max_length=32)
    scope: str = Field(min_length=1, max_length=120)
    text: str = Field(default="", max_length=4000)
    operation: str = Field(default="add", max_length=16)
    entry_id: UUID | None = None
    locked: bool = False
    source: str = Field(default="user", max_length=16)


def character_evolution_router(store, authorize) -> APIRouter:
    router = APIRouter(
        prefix=f"/api/v{API_PROTOCOL}/worlds/{{world_id}}/characters/{{root_import_id}}/evolution",
        dependencies=[Depends(authorize)],
    )

    @router.get("", response_model=list[wire.CharacterEvolutionEntry])
    async def list_evolution(world_id: UUID, root_import_id: UUID) -> list[dict]:
        try:
            return await store.list(WorldId(world_id), root_import_id)
        except EntityNotFoundError as error:
            raise HTTPException(404, str(error)) from None

    @router.post("", response_model=wire.CharacterEvolutionEntry)
    async def change_evolution(
        world_id: UUID, root_import_id: UUID, body: EvolutionChange
    ) -> dict:
        try:
            return await store.change(
                WorldId(world_id),
                root_import_id,
                field=body.field,
                scope=body.scope,
                text=body.text,
                operation=body.operation,
                entry_id=body.entry_id,
                locked=body.locked,
                source=body.source,
            )
        except EntityNotFoundError as error:
            raise HTTPException(404, str(error)) from None
        except ValueError as error:
            code = str(error)
            status = 409 if code == "character_evolution_locked" else 422
            raise HTTPException(status, code) from None

    return router
