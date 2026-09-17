"""Directional internal simulation metrics; never normal player-facing scores."""

from dataclasses import dataclass, replace

from livingworld.domain.errors import DomainInvariantError
from livingworld.domain.identifiers import CharacterId, PlayerId, PrincipalId, WorldId
from livingworld.domain.values import Revision, require_type, same_world


@dataclass(frozen=True, slots=True)
class RelationshipMetrics:
    affinity: int = 0
    trust: int = 0
    familiarity: int = 0

    def __post_init__(self) -> None:
        for name, minimum, maximum in (
            ("affinity", -100, 100),
            ("trust", -100, 100),
            ("familiarity", 0, 100),
        ):
            value = getattr(self, name)
            if type(value) is not int or not minimum <= value <= maximum:
                raise DomainInvariantError(f"{name} requires an integer in [{minimum}, {maximum}]")

    def apply_delta(self, affinity: int, trust: int, familiarity: int) -> "RelationshipMetrics":
        if any(type(value) is not int for value in (affinity, trust, familiarity)):
            raise DomainInvariantError("Relationship deltas require integers")
        if (affinity, trust, familiarity) == (0, 0, 0):
            raise DomainInvariantError("At least one relationship delta must be non-zero")
        return RelationshipMetrics(
            self.affinity + affinity, self.trust + trust, self.familiarity + familiarity
        )


@dataclass(frozen=True, slots=True)
class Relationship:
    world_id: WorldId
    source_id: PrincipalId
    target_id: PrincipalId
    revision: Revision = Revision()
    metrics: RelationshipMetrics = RelationshipMetrics()

    def __post_init__(self) -> None:
        require_type(self.source_id, (CharacterId, PlayerId), "source_id")
        require_type(self.target_id, (CharacterId, PlayerId), "target_id")
        same_world(self.world_id, self.source_id, self.target_id)
        require_type(self.revision, Revision, "revision")
        require_type(self.metrics, RelationshipMetrics, "metrics")

    def change(
        self,
        affinity_delta: int,
        trust_delta: int,
        familiarity_delta: int,
        *,
        expected_revision: Revision,
    ) -> "Relationship":
        return replace(
            self,
            metrics=self.metrics.apply_delta(affinity_delta, trust_delta, familiarity_delta),
            revision=self.revision.advance(expected_revision),
        )
