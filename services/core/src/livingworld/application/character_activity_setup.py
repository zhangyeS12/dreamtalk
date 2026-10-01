"""Explicit initial placement; neither a whereabouts feed nor a movement API."""

from dataclasses import dataclass
from typing import Protocol

from livingworld.application.chat_conversations import ChatConversationService
from livingworld.application.command_handler import CommandHandler
from livingworld.application.commands import PlaceCharacter
from livingworld.application.errors import CharacterActivitySetupError
from livingworld.application.player_event_feed import PlayerEventFeedService
from livingworld.domain.contracts import RequestId
from livingworld.domain.identifiers import CharacterId, LocationId, PlayerId, WorldId


@dataclass(frozen=True, slots=True)
class ActivityCharacter:
    character_id: CharacterId
    name: str
    initialized: bool


class CharacterActivityDirectory(Protocol):
    async def initialized(
        self, player_id: PlayerId, characters: tuple[CharacterId, ...]
    ) -> dict[CharacterId, bool]: ...


class CharacterActivitySetupService:
    def __init__(
        self,
        directory: CharacterActivityDirectory,
        chats: ChatConversationService,
        players: PlayerEventFeedService,
        commands: CommandHandler,
    ) -> None:
        self._directory, self._chats = directory, chats
        self._players, self._commands = players, commands

    async def list_characters(
        self, world_id: WorldId
    ) -> tuple[PlayerId | None, tuple[ActivityCharacter, ...]]:
        player = await self._players.selected_player(world_id)
        if player is None:
            return None, ()
        contacts = await self._chats.list_for_world(world_id)
        if any(item.player_id != player for item in contacts):
            raise CharacterActivitySetupError("activity_player_changed")
        states = await self._directory.initialized(
            player, tuple(item.character_id for item in contacts)
        )
        return player, tuple(
            ActivityCharacter(item.character_id, item.character_name, states[item.character_id])
            for item in contacts
        )

    async def initialize(
        self,
        player_id: PlayerId,
        character_id: CharacterId,
        location_id: LocationId,
        request_id: RequestId,
    ) -> None:
        if await self._players.selected_player(player_id.world_id) != player_id:
            raise CharacterActivitySetupError("activity_player_changed")
        await self._commands.execute(
            PlaceCharacter(
                request_id=request_id,
                world_id=player_id.world_id,
                character_id=character_id,
                location_id=location_id,
                expected_state_revision=None,
                activity_player_id=player_id,
            )
        )
