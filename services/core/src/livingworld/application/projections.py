"""Complete immutable replay output, separate from ledger/receipt/runtime metadata."""

from dataclasses import dataclass

from livingworld.domain.knowledge import KnowledgeAssertion, Observation
from livingworld.domain.participants import Character, CharacterState, Player, PlayerPresence
from livingworld.domain.relationships import Relationship
from livingworld.domain.world import Location, World


@dataclass(frozen=True, slots=True)
class ProjectionSnapshot:
    world: World
    locations: tuple[Location, ...]
    players: tuple[Player, ...]
    presences: tuple[PlayerPresence, ...]
    characters: tuple[Character, ...]
    character_states: tuple[CharacterState, ...]
    relationships: tuple[Relationship, ...]
    knowledge: tuple[KnowledgeAssertion, ...]
    observations: tuple[Observation, ...]
