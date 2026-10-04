"""Authenticated local-user event feed; never exposes canonical event payloads."""

from collections.abc import Callable
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from livingworld.application.errors import EntityNotFoundError
from livingworld.application.player_event_feed import PlayerEventFeedService
from livingworld.application.player_onboarding import LocalPlayerOnboardingService
from livingworld.domain.contracts import API_PROTOCOL, RequestId
from livingworld.domain.errors import ConcurrencyConflictError, DomainInvariantError
from livingworld.domain.identifiers import PlayerId, WorldId
from livingworld.domain.participants import PlayerAvailability
from livingworld.domain.values import Revision


class BindPlayerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    player_id: UUID


class AvailabilityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    availability: PlayerAvailability
    expected_presence_revision: int = Field(ge=0, strict=True)


_EVENT_TITLES = {
    "PlayerMoved": "有人移动了位置",
    "PlayerPlaced": "有人来到了一个地点",
    "CharacterPlaced": "有角色来到了一个地点",
    "CharactersMet": "有角色短暂碰面",
    "SharedActivityStarted": "有角色开始共同休闲",
    "SharedActivityEnded": "有角色的共同休闲结束了",
    "SharedActivityInterrupted": "有角色的共同休闲中断了",
    "CharacterRoutineStarted": "有角色开始了日常活动",
    "CharacterRoutineEnded": "有角色的活动时段结束了",
    "CharacterRoutineInterrupted": "有角色的活动中断了",
}


def player_events_router(
    service: PlayerEventFeedService,
    authorize: Callable[..., None],
    onboarding: LocalPlayerOnboardingService | None = None,
) -> APIRouter:
    router = APIRouter(prefix=f"/api/v{API_PROTOCOL}", dependencies=[Depends(authorize)])

    @router.get("/worlds/{world_id}/players")
    async def list_players(world_id: UUID) -> list[dict[str, str]]:
        identity = WorldId(world_id)
        return [
            {"player_id": str(player.player_id.value), "name": player.name}
            for player in await service.players(identity)
        ]

    @router.get("/worlds/{world_id}/me/player")
    async def selected_player(world_id: UUID) -> dict[str, str | int | None]:
        identity = WorldId(world_id)
        presence = await service.selected_presence(identity)
        player = (
            presence.player_id if presence is not None else await service.selected_player(identity)
        )
        return {
            "player_id": str(player.value) if player is not None else None,
            "availability": presence.availability.value if presence is not None else None,
            "presence_revision": presence.revision.value if presence is not None else None,
        }

    @router.post("/worlds/{world_id}/me/player")
    async def bind_player(world_id: UUID, body: BindPlayerRequest) -> dict[str, str]:
        player = PlayerId(WorldId(world_id), body.player_id)
        try:
            await service.bind_player(player)
        except ValueError:
            raise HTTPException(404, "player_not_found_in_world") from None
        return {"player_id": str(player.value)}

    if onboarding is not None:

        @router.post("/worlds/{world_id}/me/start")
        async def start_at_home(world_id: UUID) -> dict[str, str]:
            try:
                player = await onboarding.start_at_home(WorldId(world_id))
            except EntityNotFoundError:
                raise HTTPException(404, "world_not_found") from None
            return {"player_id": str(player.value)}

        @router.post("/worlds/{world_id}/me/availability")
        async def set_availability(
            world_id: UUID,
            body: AvailabilityRequest,
            x_request_id: str | None = Header(default=None),
        ) -> dict[str, int | str]:
            try:
                request_id = RequestId.parse(x_request_id or "")
            except ValueError:
                raise HTTPException(400, "valid_request_id_required") from None
            try:
                revision = await onboarding.set_availability(
                    WorldId(world_id),
                    body.availability,
                    Revision(body.expected_presence_revision),
                    request_id,
                )
            except EntityNotFoundError:
                raise HTTPException(404, "local_player_not_found") from None
            except ConcurrencyConflictError:
                raise HTTPException(409, "player_presence_changed") from None
            except DomainInvariantError:
                raise HTTPException(422, "availability_already_set") from None
            return {"availability": body.availability.value, "presence_revision": revision.value}

    @router.get("/worlds/{world_id}/known-events")
    async def known_events(world_id: UUID) -> list[dict[str, str | int | None]]:
        return [
            {
                "event_id": str(event.event_id.value),
                "title": _EVENT_TITLES.get(event.event_type, "你获知了一件世界事件"),
                "occurred_at": str(event.occurred_at.microseconds),
                "observed_at": str(event.observed_at.microseconds),
                "ledger_position": event.ledger_position,
                "description": event.description,
                "observation_channel": event.observation_channel,
            }
            for event in await service.known_events(WorldId(world_id))
        ]

    return router
