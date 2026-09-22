"""Authenticated local-user profile editing without runtime mutation rights."""

from collections.abc import Callable
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from livingworld.application.errors import EntityNotFoundError
from livingworld.application.local_profile import LocalProfile, LocalProfileStore
from livingworld.domain.contracts import API_PROTOCOL
from livingworld.domain.errors import ConcurrencyConflictError
from livingworld.domain.identifiers import WorldId
from livingworld.domain.values import Revision


class ProfileWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(max_length=120)
    description: str = Field(max_length=8000)
    expected_revision: int = Field(ge=0, strict=True)


def profile_router(store: LocalProfileStore, authorize: Callable[..., None]) -> APIRouter:
    router = APIRouter(prefix=f"/api/v{API_PROTOCOL}", dependencies=[Depends(authorize)])

    async def read(world_id: UUID | None) -> dict[str, str | int]:
        try:
            result = await store.load(WorldId(world_id) if world_id is not None else None)
        except EntityNotFoundError:
            raise HTTPException(404, "world_not_found") from None
        return _response(result)

    async def write(body: ProfileWrite, world_id: UUID | None) -> dict[str, str | int]:
        try:
            result = await store.save(
                LocalProfile(body.name, body.description, Revision(body.expected_revision)),
                WorldId(world_id) if world_id is not None else None,
            )
        except EntityNotFoundError:
            raise HTTPException(404, "world_not_found") from None
        except ConcurrencyConflictError:
            raise HTTPException(409, "profile_edit_conflict") from None
        return _response(result)

    @router.get("/me/profile")
    async def read_general() -> dict[str, str | int]:
        return await read(None)

    @router.post("/me/profile")
    async def write_general(body: ProfileWrite) -> dict[str, str | int]:
        return await write(body, None)

    @router.get("/worlds/{world_id}/me/profile")
    async def read_world(world_id: UUID) -> dict[str, str | int]:
        return await read(world_id)

    @router.post("/worlds/{world_id}/me/profile")
    async def write_world(world_id: UUID, body: ProfileWrite) -> dict[str, str | int]:
        return await write(body, world_id)

    return router


def _response(profile: LocalProfile) -> dict[str, str | int]:
    return {
        "name": profile.name,
        "description": profile.description,
        "revision": profile.revision.value,
    }
