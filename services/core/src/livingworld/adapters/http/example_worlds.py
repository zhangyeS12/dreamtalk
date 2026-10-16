"""Authenticated preview and explicit confirmation of the bundled campus world."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from livingworld.application.errors import IdempotencyConflictError
from livingworld.domain.contracts import API_PROTOCOL, RequestId


class ExampleConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmed: bool
    reviewed_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    public_entries: list[str] = Field(max_length=16)


def example_world_router(service, authorize, storage_observer=None):
    router = APIRouter(
        prefix=f"/api/v{API_PROTOCOL}/world-examples", dependencies=[Depends(authorize)]
    )

    @router.get("")
    async def catalog():
        return await service.catalog()

    @router.post("/{template_id}", status_code=201)
    async def create(
        template_id: str,
        body: ExampleConfirmation,
        x_request_id: Annotated[str | None, Header()] = None,
    ):
        if not body.confirmed:
            raise HTTPException(422, "example_confirmation_required")
        try:
            request_id = RequestId.parse(x_request_id or "")
        except ValueError:
            raise HTTPException(400, "valid_request_id_required") from None
        try:
            world = await service.create(
                template_id, request_id, body.reviewed_hash, body.public_entries
            )
        except IdempotencyConflictError as error:
            code = (
                "example_world_deleted"
                if str(error) == "world_deleted"
                else "example_setup_conflict"
            )
            raise HTTPException(409, code) from None
        except ValueError:
            raise HTTPException(409, "example_preview_changed") from None
        if storage_observer:
            import asyncio

            await asyncio.to_thread(storage_observer)
        return {"world_id": str(world.value)}

    return router
