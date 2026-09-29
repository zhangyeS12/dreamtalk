"""Authenticated local world-authoring API; no whereabouts or event feed."""

from collections.abc import Callable
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from livingworld.application.errors import (
    EntityAlreadyExistsError,
    EntityNotFoundError,
    IdempotencyConflictError,
    WorldRuntimeUnavailableError,
)
from livingworld.application.world_locations import (
    LocalLocation,
    LocationCatalogError,
    WorldLocationsService,
)
from livingworld.domain.contracts import API_PROTOCOL, RequestId
from livingworld.domain.errors import DomainInvariantError
from livingworld.domain.identifiers import WorldId


class CreateLocationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)


def _response(location: LocalLocation) -> dict[str, str | bool]:
    return {
        "location_id": str(location.location_id.value),
        "name": location.name,
        "is_home": location.is_home,
    }


def world_locations_router(
    service: WorldLocationsService, authorize: Callable[..., None]
) -> APIRouter:
    router = APIRouter(prefix=f"/api/v{API_PROTOCOL}", dependencies=[Depends(authorize)])

    @router.get("/worlds/{world_id}/activity-locations")
    async def list_locations(world_id: UUID) -> list[dict[str, str | bool]]:
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
    ) -> dict[str, str | bool]:
        try:
            request_id = RequestId.parse(x_request_id or "")
        except ValueError:
            raise HTTPException(400, "valid_request_id_required") from None
        try:
            return _response(await service.create(WorldId(world_id), body.name, request_id))
        except LocationCatalogError as error:
            code = str(error)
            raise HTTPException(
                422 if code in {"invalid_location_name", "location_home_reserved"} else 409, code
            ) from None
        except EntityNotFoundError:
            raise HTTPException(404, "world_not_found") from None
        except (IdempotencyConflictError, EntityAlreadyExistsError):
            raise HTTPException(409, "location_creation_conflict") from None
        except WorldRuntimeUnavailableError:
            raise HTTPException(503, "world_runtime_unavailable") from None
        except DomainInvariantError:
            raise HTTPException(422, "invalid_location_name") from None

    return router
