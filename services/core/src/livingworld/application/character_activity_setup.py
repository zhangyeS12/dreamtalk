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
from livingworld.domain.values import Revision


@dataclass(frozen=True, slots=True)
class ActivityCharacter:
    character_id: CharacterId
    name: str
    initialized: bool
    root_import_id: str = ""
    initial_location_id: str | None = None
    current_location_id: str | None = None
    locked: bool = False
    revision: int | None = None
    policy_revision: int = 0
    residency: str = "strong"


class CharacterActivityDirectory(Protocol):
    async def locations(self, player_id, characters) -> dict: ...
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
        locations = await self._directory.locations(
            player, tuple(item.character_id for item in contacts)
        )
        characters = []
        for item in contacts:
            initial, current, locked, revision, policy_revision, residency = locations.get(
                item.character_id, (None, None, False, None, 0, "strong")
            )
            characters.append(
                ActivityCharacter(
                    character_id=item.character_id,
                    name=item.character_name,
                    initialized=current is not None,
                    root_import_id=str(item.root_import_id),
                    initial_location_id=str(initial) if initial else None,
                    current_location_id=str(current) if current else None,
                    locked=locked,
                    revision=revision,
                    policy_revision=policy_revision,
                    residency=residency,
                )
            )
        return player, tuple(characters)

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

    async def configure(
        self,
        player_id,
        character_id,
        location_id,
        locked,
        revision,
        request_id,
        policy_revision,
        residency="strong",
    ):
        if await self._players.selected_player(player_id.world_id) != player_id:
            raise CharacterActivitySetupError("activity_player_changed")
        await self._commands.execute(
            PlaceCharacter(
                request_id=request_id,
                world_id=player_id.world_id,
                character_id=character_id,
                location_id=location_id,
                expected_state_revision=Revision(revision) if revision is not None else None,
                activity_player_id=player_id,
                activity_configure=True,
                activity_locked=locked,
                activity_residency=residency,
                expected_location_policy_revision=policy_revision,
            )
        )
