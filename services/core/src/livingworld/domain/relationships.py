"""Directed relationship seam; no affinity scores or player-facing projection."""

from dataclasses import dataclass

from livingworld.domain.identifiers import CharacterId, PlayerId, PrincipalId, WorldId
from livingworld.domain.values import Revision, require_type, same_world


@dataclass(frozen=True, slots=True)
class Relationship:
    world_id: WorldId
    source_id: PrincipalId
    target_id: PrincipalId
    revision: Revision = Revision()

    def __post_init__(self) -> None:
        require_type(self.source_id, (CharacterId, PlayerId), "source_id")
        require_type(self.target_id, (CharacterId, PlayerId), "target_id")
        same_world(self.world_id, self.source_id, self.target_id)
        require_type(self.revision, Revision, "revision")
