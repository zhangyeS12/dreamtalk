"""Authenticated creator setup, limited to current local-Player direct contacts."""

from collections.abc import Callable
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict

from livingworld.application.character_activity_setup import CharacterActivitySetupService
from livingworld.application.errors import (
    CharacterActivitySetupError,
    EntityNotFoundError,
    IdempotencyConflictError,
    WorldCatchingUpError,
    WorldRuntimeUnavailableError,
)
from livingworld.domain.contracts import API_PROTOCOL, RequestId
from livingworld.domain.errors import ConcurrencyConflictError
from livingworld.domain.identifiers import CharacterId, LocationId, PlayerId, WorldId


class InitialActivityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    player_id: UUID
    location_id: UUID


def character_activity_setup_router(
    service: CharacterActivitySetupService, authorize: Callable[..., None]
) -> APIRouter:
    router = APIRouter(prefix=f"/api/v{API_PROTOCOL}", dependencies=[Depends(authorize)])

    @router.get("/worlds/{world_id}/activity-characters")
    async def list_characters(world_id: UUID) -> dict:
        try:
            player, characters = await service.list_characters(WorldId(world_id))
            return {
                "player_id": str(player.value) if player else None,
                "items": [
                    {
                        "character_id": str(item.character_id.value),
                        "name": item.name,
                        "initialized": item.initialized,
                    }
                    for item in characters
                ],
            }
        except EntityNotFoundError:
            raise HTTPException(404, "activity_character_unavailable") from None
        except CharacterActivitySetupError as error:
            raise HTTPException(409, str(error)) from None

    @router.post("/worlds/{world_id}/activity-characters/{character_id}/initial-location")
    async def initialize(
        world_id: UUID,
        character_id: UUID,
        body: InitialActivityRequest,
        x_request_id: str | None = Header(default=None),
    ) -> dict:
        try:
            request_id = RequestId.parse(x_request_id or "")
        except ValueError:
            raise HTTPException(400, "valid_request_id_required") from None
        world = WorldId(world_id)
        try:
            await service.initialize(
                PlayerId(world, body.player_id),
                CharacterId(world, character_id),
                LocationId(world, body.location_id),
                request_id,
            )
            return {"character_id": str(character_id), "initialized": True}
        except CharacterActivitySetupError as error:
            raise HTTPException(409, str(error)) from None
        except ConcurrencyConflictError:
            raise HTTPException(409, "activity_initial_already_set") from None
        except IdempotencyConflictError:
            raise HTTPException(409, "activity_request_conflict") from None
        except EntityNotFoundError:
            raise HTTPException(404, "activity_target_unavailable") from None
        except (WorldCatchingUpError, WorldRuntimeUnavailableError):
            raise HTTPException(503, "world_runtime_unavailable") from None

    return router
