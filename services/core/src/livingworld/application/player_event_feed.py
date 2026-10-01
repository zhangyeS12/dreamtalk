"""The current local user's Player binding and owner-scoped event timeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from livingworld.domain.identifiers import EventId, PlayerId, PrincipalId, WorldId
from livingworld.domain.participants import PlayerAvailability
from livingworld.domain.values import Revision, WorldTime


@dataclass(frozen=True, slots=True)
class SelectablePlayer:
    player_id: PlayerId
    name: str


@dataclass(frozen=True, slots=True)
class LocalPlayerPresence:
    player_id: PlayerId
    availability: PlayerAvailability
    revision: Revision


@dataclass(frozen=True, slots=True)
class KnownWorldEvent:
    event_id: EventId
    event_type: str
    occurred_at: WorldTime
    observed_at: WorldTime
    ledger_position: int
    description: str | None = None
    observation_channel: str | None = None
    subject: PrincipalId | None = None


class PlayerEventFeedStore(Protocol):
    async def list_players(self, world_id: WorldId) -> tuple[SelectablePlayer, ...]: ...
    async def selected_player(self, world_id: WorldId) -> PlayerId | None: ...
    async def selected_presence(self, world_id: WorldId) -> LocalPlayerPresence | None: ...
    async def bind_player(self, player_id: PlayerId) -> None: ...
    async def known_events(self, world_id: WorldId, limit: int) -> tuple[KnownWorldEvent, ...]: ...


class PlayerEventFeedService:
    def __init__(self, store: PlayerEventFeedStore) -> None:
        self._store = store

    async def players(self, world_id: WorldId) -> tuple[SelectablePlayer, ...]:
        return await self._store.list_players(world_id)

    async def selected_player(self, world_id: WorldId) -> PlayerId | None:
        return await self._store.selected_player(world_id)

    async def selected_presence(self, world_id: WorldId) -> LocalPlayerPresence | None:
        return await self._store.selected_presence(world_id)

    async def bind_player(self, player_id: PlayerId) -> None:
        await self._store.bind_player(player_id)

    async def known_events(self, world_id: WorldId) -> tuple[KnownWorldEvent, ...]:
        return await self._store.known_events(world_id, 100)
