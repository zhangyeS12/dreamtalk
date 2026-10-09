"""Current-world faction editing and avatar bindings for the contact book."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from livingworld.domain.contracts import API_PROTOCOL
from livingworld.infrastructure.persistence.factions import FactionError


class FactionWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    parent_id: UUID | None = None


class AvatarWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class FactionLeave(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cut_contacts: StrictBool = False


def faction_router(store, authorize):
    router = APIRouter(
        prefix=f"/api/v{API_PROTOCOL}/worlds/{{world_id}}/social",
        dependencies=[Depends(authorize)],
    )

    async def call(operation):
        try:
            return await operation
        except FactionError as error:
            code = str(error)
            status = (
                404
                if code.endswith("not_found")
                else 409
                if code in {"faction_name_taken", "faction_cycle", "faction_not_empty"}
                else 422
            )
            raise HTTPException(status, detail=code) from None

    @router.get("")
    async def snapshot(world_id: UUID):
        return await call(store.snapshot(world_id))

    @router.post("/factions")
    async def create(world_id: UUID, body: FactionWrite):
        identity = await call(store.create(world_id, body.name, body.parent_id))
        return {"faction_id": str(identity)}

    @router.put("/factions/{faction_id}")
    async def edit(world_id: UUID, faction_id: UUID, body: FactionWrite):
        await call(store.edit(world_id, faction_id, body.name, body.parent_id))
        return {"saved": True}

    @router.delete("/factions/{faction_id}")
    async def remove(world_id: UUID, faction_id: UUID):
        await call(store.remove(world_id, faction_id))
        return {"saved": True}

    @router.put("/factions/{faction_id}/members/{root_import_id}")
    async def add_member(world_id: UUID, faction_id: UUID, root_import_id: UUID):
        await call(store.membership(world_id, faction_id, root_import_id, True))
        return {"saved": True}

    @router.delete("/factions/{faction_id}/members/{root_import_id}")
    async def remove_member(
        world_id: UUID, faction_id: UUID, root_import_id: UUID, body: FactionLeave | None = None
    ):
        await call(
            store.membership(
                world_id,
                faction_id,
                root_import_id,
                False,
                cut_contacts=body.cut_contacts if body else False,
            )
        )
        return {"saved": True}

    @router.put("/avatars/{root_import_id}")
    async def avatar(world_id: UUID, root_import_id: UUID, body: AvatarWrite):
        await call(store.avatar(world_id, root_import_id, body.digest))
        return {"saved": True}

    return router
