"""Authenticated local-user event feed; never exposes canonical event payloads."""

from collections.abc import Callable
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from livingworld.application.errors import EntityNotFoundError
from livingworld.application.player_event_feed import PlayerEventFeedService
from livingworld.application.player_onboarding import LocalPlayerOnboardingService
from livingworld.domain.contracts import API_PROTOCOL
from livingworld.domain.identifiers import PlayerId, WorldId


class BindPlayerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    player_id: UUID


_EVENT_TITLES = {"PlayerMoved": "有人移动了位置"}


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
    async def selected_player(world_id: UUID) -> dict[str, str | None]:
        player = await service.selected_player(WorldId(world_id))
        return {"player_id": str(player.value) if player is not None else None}

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

    @router.get("/worlds/{world_id}/known-events")
    async def known_events(world_id: UUID) -> list[dict[str, str | int]]:
        return [
            {
                "event_id": str(event.event_id.value),
                "title": _EVENT_TITLES.get(event.event_type, "你获知了一件世界事件"),
                "occurred_at": str(event.occurred_at.microseconds),
                "observed_at": str(event.observed_at.microseconds),
                "ledger_position": event.ledger_position,
            }
            for event in await service.known_events(WorldId(world_id))
        ]

    return router
