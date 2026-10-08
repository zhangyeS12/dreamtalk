"""Local authored location directory; never a view of character whereabouts."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol
from unicodedata import category, normalize
from uuid import uuid5

from livingworld.application.commands import ConfigureLocation, CreateLocation
from livingworld.domain.contracts import RequestId
from livingworld.domain.errors import DomainInvariantError
from livingworld.domain.identifiers import CharacterId, LocationId, PlayerId, WorldId
from livingworld.domain.values import Revision

if TYPE_CHECKING:
    from livingworld.application.command_handler import CommandHandler


class LocationCatalogError(DomainInvariantError):
    pass


def location_name_key(name: str) -> str:
    if (
        not isinstance(name, str)
        or not name.strip()
        or len(name) > 120
        or any(category(char) in {"Cc", "Cs"} for char in name)
    ):
        raise LocationCatalogError("invalid_location_name")
    key = normalize("NFKC", name).casefold().strip()
    if not key or len(key.encode("utf-8")) > 4096:
        raise LocationCatalogError("invalid_location_name")
    if key == "家":
        raise LocationCatalogError("location_home_reserved")
    return key


@dataclass(frozen=True, slots=True)
class LocalLocation:
    location_id: LocationId
    name: str
    is_home: bool = False
    parent_id: LocationId | None = None
    hidden: bool = False
    allowed_characters: tuple[CharacterId, ...] = ()
    revision: int = 0
    is_region: bool = False


class LocalLocationDirectory(Protocol):
    async def list_locations(self, world_id: WorldId) -> tuple[LocalLocation, ...]: ...
    async def remove_location(self, location_id: LocationId, expected_revision: int) -> None: ...


class LocalLocationCatalog(Protocol):
    async def check_new(self, world_id: WorldId, name: str) -> None: ...
    async def add(self, location_id: LocationId, name: str) -> None: ...
    async def check_initial_activity(
        self, character_id: CharacterId, location_id: LocationId, player_id: PlayerId
    ) -> None: ...
    async def check_options(self, location_id, parent_id, hidden, allowed_characters) -> None: ...
    async def check_edit(self, location_id, name) -> None: ...
    async def configure(
        self, location_id, name, parent_id, hidden, allowed_characters, is_region=False
    ) -> None: ...
    async def check_character_config(
        self, character_id, location_id, player_id, policy_revision
    ) -> None: ...
    async def configure_character(
        self, character_id, location_id, locked, residency="strong", now=None
    ) -> None: ...
    async def config_destination(self, character_id, root, locked, before): ...


class WorldLocationsService:
    def __init__(self, directory: LocalLocationDirectory, commands: "CommandHandler") -> None:
        self._directory, self._commands = directory, commands

    async def list_locations(self, world_id: WorldId) -> tuple[LocalLocation, ...]:
        return await self._directory.list_locations(world_id)

    async def remove(self, location_id: LocationId, expected_revision: int) -> None:
        await self._directory.remove_location(location_id, expected_revision)

    async def create(
        self,
        world_id: WorldId,
        name: str,
        request_id: RequestId,
        *,
        parent_id=None,
        hidden=False,
        allowed_characters=(),
        is_region=False,
    ) -> LocalLocation:
        name = name.strip()
        location_name_key(name)
        identity = LocationId(
            world_id, uuid5(world_id.value, f"livingworld:local-location:v1:{request_id.value}")
        )
        await self._commands.execute(
            CreateLocation(
                request_id=request_id,
                world_id=world_id,
                location_id=identity,
                name=name,
                list_locally=True,
                parent_id=parent_id,
                hidden=hidden,
                allowed_characters=allowed_characters,
                is_region=is_region,
            )
        )
        return LocalLocation(
            identity,
            name,
            parent_id=parent_id,
            hidden=hidden,
            allowed_characters=allowed_characters,
            is_region=is_region,
        )

    async def edit(
        self,
        world_id,
        location_id,
        name,
        revision,
        request_id,
        *,
        parent_id=None,
        hidden=False,
        allowed_characters=(),
        is_region=False,
    ):
        name = name.strip()
        location_name_key(name)
        await self._commands.execute(
            ConfigureLocation(
                request_id=request_id,
                world_id=world_id,
                location_id=location_id,
                name=name,
                expected_revision=Revision(revision),
                parent_id=parent_id,
                hidden=hidden,
                allowed_characters=allowed_characters,
                is_region=is_region,
            )
        )
        # Retry response describes the committed request, never a later edit.
        return LocalLocation(
            location_id,
            name,
            parent_id=parent_id,
            hidden=hidden,
            allowed_characters=allowed_characters,
            revision=revision + 1,
            is_region=is_region,
        )
