"""Authenticated local world-authoring API; no whereabouts or event feed."""

from collections.abc import Callable
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from livingworld.application.errors import (
    EntityAlreadyExistsError,
    EntityNotFoundError,
    IdempotencyConflictError,
    WorldCatchingUpError,
    WorldRuntimeUnavailableError,
)
from livingworld.application.world_locations import (
    LocalLocation,
    LocationCatalogError,
    WorldLocationsService,
)
from livingworld.domain.contracts import API_PROTOCOL, RequestId
from livingworld.domain.errors import ConcurrencyConflictError, DomainInvariantError
from livingworld.domain.identifiers import CharacterId, LocationId, WorldId


class CreateLocationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    parent_id: UUID | None = None
    hidden: bool = False
    is_region: bool = False
    allowed_character_ids: list[UUID] = Field(default_factory=list)


class EditLocationRequest(CreateLocationRequest):
    expected_revision: int = Field(ge=0)


class RemoveLocationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)


def _response(location: LocalLocation) -> dict:
    return {
        "location_id": str(location.location_id.value),
        "name": location.name,
        "is_home": location.is_home,
        "parent_id": str(location.parent_id.value) if location.parent_id else None,
        "hidden": location.hidden,
        "is_region": location.is_region,
        "allowed_character_ids": [str(item.value) for item in location.allowed_characters],
        "revision": location.revision,
    }


def world_locations_router(
    service: WorldLocationsService, authorize: Callable[..., None]
) -> APIRouter:
    router = APIRouter(prefix=f"/api/v{API_PROTOCOL}", dependencies=[Depends(authorize)])

    @router.get("/worlds/{world_id}/activity-locations")
    async def list_locations(world_id: UUID) -> list[dict]:
        try:
            return [_response(item) for item in await service.list_locations(WorldId(world_id))]
        except EntityNotFoundError:
            raise HTTPException(404, "world_not_found") from None
        except LocationCatalogError as error:
            raise HTTPException(409, str(error)) from None

    @router.post("/worlds/{world_id}/activity-locations", status_code=201)
    async def create_location(
        world_id: UUID,
        body: CreateLocationRequest,
        x_request_id: str | None = Header(default=None),
    ) -> dict:
        try:
            request_id = RequestId.parse(x_request_id or "")
        except ValueError:
            raise HTTPException(400, "valid_request_id_required") from None
        try:
            world = WorldId(world_id)
            return _response(
                await service.create(
                    world,
                    body.name,
                    request_id,
                    parent_id=LocationId(world, body.parent_id) if body.parent_id else None,
                    hidden=body.hidden,
                    is_region=body.is_region,
                    allowed_characters=tuple(
                        CharacterId(world, item) for item in body.allowed_character_ids
                    ),
                )
            )
        except LocationCatalogError as error:
            code = str(error)
            raise HTTPException(
                422 if code in {"invalid_location_name", "location_home_reserved"} else 409, code
            ) from None
        except EntityNotFoundError:
            raise HTTPException(404, "world_not_found") from None
        except (IdempotencyConflictError, EntityAlreadyExistsError):
            raise HTTPException(409, "location_creation_conflict") from None
        except (WorldCatchingUpError, WorldRuntimeUnavailableError):
            raise HTTPException(503, "world_runtime_unavailable") from None
        except DomainInvariantError:
            raise HTTPException(422, "invalid_location_name") from None

    @router.put("/worlds/{world_id}/activity-locations/{location_id}")
    async def edit_location(
        world_id: UUID,
        location_id: UUID,
        body: EditLocationRequest,
        x_request_id: str | None = Header(default=None),
    ):
        try:
            request_id = RequestId.parse(x_request_id or "")
        except ValueError:
            raise HTTPException(400, "valid_request_id_required") from None
        world = WorldId(world_id)
        try:
            return _response(
                await service.edit(
                    world,
                    LocationId(world, location_id),
                    body.name,
                    body.expected_revision,
                    request_id,
                    parent_id=LocationId(world, body.parent_id) if body.parent_id else None,
                    hidden=body.hidden,
                    is_region=body.is_region,
                    allowed_characters=tuple(
                        CharacterId(world, item) for item in body.allowed_character_ids
                    ),
                )
            )
        except LocationCatalogError as error:
            raise HTTPException(409, str(error)) from None
        except ConcurrencyConflictError:
            raise HTTPException(409, "location_revision_changed") from None
        except IdempotencyConflictError:
            raise HTTPException(409, "location_creation_conflict") from None
        except EntityNotFoundError:
            raise HTTPException(404, "location_not_found") from None
        except (WorldCatchingUpError, WorldRuntimeUnavailableError):
            raise HTTPException(503, "world_runtime_unavailable") from None
        except DomainInvariantError:
            raise HTTPException(422, "invalid_location_name") from None

    @router.delete("/worlds/{world_id}/activity-locations/{location_id}")
    async def remove_location(world_id: UUID, location_id: UUID, body: RemoveLocationRequest):
        try:
            await service.remove(LocationId(WorldId(world_id), location_id), body.expected_revision)
            return {"removed": True}
        except LocationCatalogError as error:
            raise HTTPException(409, str(error)) from None
        except EntityNotFoundError:
            raise HTTPException(404, "location_not_found") from None

    return router
