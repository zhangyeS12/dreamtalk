"""Immutable canonical ledger envelope; allocation belongs to infrastructure."""

from dataclasses import dataclass

from livingworld.domain.errors import DomainInvariantError
from livingworld.domain.events import WorldEvent
from livingworld.domain.values import require_type


@dataclass(frozen=True, slots=True)
class CanonicalEvent:
    event: WorldEvent
    ledger_position: int

    def __post_init__(self) -> None:
        require_type(self.event, WorldEvent, "event")
        if type(self.ledger_position) is not int or self.ledger_position <= 0:
            raise DomainInvariantError("ledger_position requires a positive integer")
