"""Focused application capabilities implemented by infrastructure."""

from datetime import datetime
from typing import Protocol, Self

from livingworld.application.results import CommandResult
from livingworld.domain.commands import CommandReceipt
from livingworld.domain.contracts import RequestId
from livingworld.domain.events import WorldEvent
from livingworld.domain.identifiers import CharacterId, LocationId, PlayerId, PrincipalId, WorldId
from livingworld.domain.participants import Character, CharacterState, Player, PlayerPresence
from livingworld.domain.relationships import Relationship
from livingworld.domain.world import Location, World


class WallClock(Protocol):
    def now_utc(self) -> datetime: ...


class WorldRepository(Protocol):
    async def get(self, world_id: WorldId) -> World | None: ...
    async def add(self, world: World) -> None: ...


class LocationRepository(Protocol):
    async def get(self, location_id: LocationId) -> Location | None: ...
    async def add(self, location: Location) -> None: ...


class PlayerRepository(Protocol):
    async def get(self, player_id: PlayerId) -> Player | None: ...
    async def presence(self, player_id: PlayerId) -> PlayerPresence | None: ...
    async def add(self, player: Player, presence: PlayerPresence) -> None: ...
    async def replace_presence(self, presence: PlayerPresence) -> None: ...


class CharacterRepository(Protocol):
    async def get(self, character_id: CharacterId) -> Character | None: ...
    async def state(self, character_id: CharacterId) -> CharacterState | None: ...
    async def add(self, character: Character) -> None: ...
    async def put_state(self, state: CharacterState) -> None: ...


class RelationshipRepository(Protocol):
    async def get(self, source: PrincipalId, target: PrincipalId) -> Relationship | None: ...
    async def put(self, relationship: Relationship) -> None: ...


class EventAppender(Protocol):
    async def append(self, event: WorldEvent) -> None: ...


class CommandReceiptRepository(Protocol):
    async def existing(self, request_id: RequestId, fingerprint: str) -> CommandResult | None: ...
    async def add(
        self, receipt: CommandReceipt, fingerprint: str, result: CommandResult
    ) -> None: ...


class UnitOfWork(Protocol):
    worlds: WorldRepository
    locations: LocationRepository
    players: PlayerRepository
    characters: CharacterRepository
    relationships: RelationshipRepository
    events: EventAppender
    receipts: CommandReceiptRepository

    async def __aenter__(self) -> Self: ...
    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None: ...
    async def commit(self) -> None: ...
