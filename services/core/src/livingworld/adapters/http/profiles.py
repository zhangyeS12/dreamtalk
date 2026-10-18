"""Authenticated local-user profile editing without runtime mutation rights."""

from collections.abc import Callable
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from livingworld.adapters.http.contracts import LocalProfile, ProfileWrite
from livingworld.application.errors import EntityNotFoundError
from livingworld.application.local_profile import LocalProfile as LocalProfileValue
from livingworld.application.local_profile import LocalProfileStore
from livingworld.domain.contracts import API_PROTOCOL
from livingworld.domain.errors import ConcurrencyConflictError
from livingworld.domain.identifiers import WorldId
from livingworld.domain.values import Revision


def profile_router(store: LocalProfileStore, authorize: Callable[..., None]) -> APIRouter:
    router = APIRouter(prefix=f"/api/v{API_PROTOCOL}", dependencies=[Depends(authorize)])

    async def read(world_id: UUID | None) -> LocalProfile:
        try:
            result = await store.load(WorldId(world_id) if world_id is not None else None)
        except EntityNotFoundError:
            raise HTTPException(404, "world_not_found") from None
        return _response(result)

    async def write(body: ProfileWrite, world_id: UUID | None) -> LocalProfile:
        try:
            result = await store.save(
                LocalProfileValue(body.name, body.description, Revision(body.expected_revision)),
                WorldId(world_id) if world_id is not None else None,
            )
        except EntityNotFoundError:
            raise HTTPException(404, "world_not_found") from None
        except ConcurrencyConflictError:
            raise HTTPException(409, "profile_edit_conflict") from None
        return _response(result)

    @router.get("/me/profile")
    async def read_general() -> LocalProfile:
        return await read(None)

    @router.post("/me/profile")
    async def write_general(body: ProfileWrite) -> LocalProfile:
        return await write(body, None)

    @router.get("/worlds/{world_id}/me/profile")
    async def read_world(world_id: UUID) -> LocalProfile:
        return await read(world_id)

    @router.post("/worlds/{world_id}/me/profile")
    async def write_world(world_id: UUID, body: ProfileWrite) -> LocalProfile:
        return await write(body, world_id)

    return router


def _response(profile: LocalProfileValue) -> LocalProfile:
    return {
        "name": profile.name,
        "description": profile.description,
        "revision": profile.revision.value,
    }
