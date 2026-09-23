"""Enter a local World with a canonical Player initially placed at home."""

from __future__ import annotations

from uuid import uuid5

from livingworld.application.command_handler import CommandHandler
from livingworld.application.commands import CreateLocation, CreatePlayer
from livingworld.application.player_event_feed import PlayerEventFeedService
from livingworld.domain.contracts import RequestId
from livingworld.domain.identifiers import LocationId, PlayerId, WorldId


class LocalPlayerOnboardingService:
    def __init__(self, commands: CommandHandler, players: PlayerEventFeedService) -> None:
        self._execute_command = commands.execute
        self._players = players

    async def start_at_home(self, world_id: WorldId) -> PlayerId:
        selected = await self._players.selected_player(world_id)
        if selected is not None:
            return selected

        # Fixed command identities make an interrupted multi-command setup safe
        # to resume. Each canonical command still owns its normal receipt/events.
        home = LocationId(world_id, uuid5(world_id.value, "livingworld:local-home:v1"))
        player = PlayerId(world_id, uuid5(world_id.value, "livingworld:local-player:v1"))
        await self._execute_command(
            CreateLocation(
                request_id=RequestId(uuid5(world_id.value, "livingworld:local-home-command:v1")),
                world_id=world_id,
                location_id=home,
                name="家",
            )
        )
        await self._execute_command(
            CreatePlayer(
                request_id=RequestId(uuid5(world_id.value, "livingworld:local-player-command:v1")),
                world_id=world_id,
                player_id=player,
                name="我",
                initial_location_id=home,
            )
        )
        # A concurrent/manual binding takes precedence over this local default.
        selected = await self._players.selected_player(world_id)
        if selected is not None:
            return selected
        await self._players.bind_player(player)
        return player
