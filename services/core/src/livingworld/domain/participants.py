"""Static identities and separately versioned physical/runtime state snapshots."""

from dataclasses import dataclass, replace
from enum import StrEnum

from livingworld.domain.errors import InvalidPresenceError
from livingworld.domain.identifiers import CharacterId, LocationId, PlayerId, WorldId
from livingworld.domain.values import Revision, require_text, require_type, same_world


class PlayerActivity(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class PlayerAvailability(StrEnum):
    BUSY = "busy"
    AVAILABLE = "available"


@dataclass(frozen=True, slots=True)
class Player:
    world_id: WorldId
    player_id: PlayerId
    name: str
    revision: Revision = Revision()

    def __post_init__(self) -> None:
        require_type(self.player_id, PlayerId, "player_id")
        same_world(self.world_id, self.player_id)
        require_text(self.name, "name")
        require_type(self.revision, Revision, "revision")


@dataclass(frozen=True, slots=True)
class PlayerPresence:
    world_id: WorldId
    player_id: PlayerId
    location_id: LocationId
    activity: PlayerActivity
    availability: PlayerAvailability
    revision: Revision = Revision()

    def __post_init__(self) -> None:
        require_type(self.player_id, PlayerId, "player_id")
        if not isinstance(self.location_id, LocationId):
            raise InvalidPresenceError("PlayerPresence requires exactly one LocationId")
        same_world(self.world_id, self.player_id, self.location_id)
        require_type(self.activity, PlayerActivity, "activity")
        require_type(self.availability, PlayerAvailability, "availability")
        require_type(self.revision, Revision, "revision")

    def with_activity(
        self, activity: PlayerActivity, *, expected_revision: Revision
    ) -> "PlayerPresence":
        return replace(self, activity=activity, revision=self.revision.advance(expected_revision))

    def at_location(
        self, location_id: LocationId, *, expected_revision: Revision
    ) -> "PlayerPresence":
        """Replace one position; movement authorization/execution belongs to a later layer."""
        return replace(
            self, location_id=location_id, revision=self.revision.advance(expected_revision)
        )


@dataclass(frozen=True, slots=True)
class Character:
    world_id: WorldId
    character_id: CharacterId
    name: str
    revision: Revision = Revision()

    def __post_init__(self) -> None:
        require_type(self.character_id, CharacterId, "character_id")
        same_world(self.world_id, self.character_id)
        require_text(self.name, "name")
        require_type(self.revision, Revision, "revision")


@dataclass(frozen=True, slots=True)
class CharacterState:
    world_id: WorldId
    character_id: CharacterId
    location_id: LocationId
    revision: Revision = Revision()

    def __post_init__(self) -> None:
        require_type(self.character_id, CharacterId, "character_id")
        require_type(self.location_id, LocationId, "location_id")
        same_world(self.world_id, self.character_id, self.location_id)
        require_type(self.revision, Revision, "revision")
