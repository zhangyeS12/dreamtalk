"""Versioned character-card overlays exposed by the authenticated API."""

from typing import Literal, TypedDict


class CharacterEvolutionEntry(TypedDict):
    entry_id: str
    field: Literal["description", "personality", "background", "scenario", "speech_guidance"]
    scope: str
    text: str
    quote: str | None
    confidence: float | None
    state: Literal["active", "inactive"]
    selected: bool
    locked: bool
    source: Literal["user", "model", "import"]
    created_at_utc: str
