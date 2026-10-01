"""Bounded observations supplied only to the authorized speaking Character."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Protocol

from livingworld.application.errors import EntityNotFoundError
from livingworld.application.player_event_feed import KnownWorldEvent
from livingworld.domain.identifiers import CharacterId

MAX_CHARACTER_EVENTS = 12
MAX_CHARACTER_EVENT_BYTES = 8 * 1024


class CharacterObservedEventReader(Protocol):
    @property
    def owner_character_id(self) -> CharacterId: ...
    async def recent(self, *, limit: int) -> tuple[KnownWorldEvent, ...]: ...


async def character_observed_events(
    reader_factory: Callable[[CharacterId], CharacterObservedEventReader] | None,
    owner: CharacterId,
) -> list[dict[str, str]]:
    if reader_factory is None:
        return []
    reader = reader_factory(owner)
    if reader.owner_character_id != owner:
        raise EntityNotFoundError("chat_event_owner_invalid")
    events = await reader.recent(limit=MAX_CHARACTER_EVENTS)
    result: list[dict[str, str]] = []
    used = 2
    # Retain the most recent complete items when the aggregate bound is reached.
    for event in reversed(events):
        if event.event_id.world_id != owner.world_id:
            raise EntityNotFoundError("chat_event_world_invalid")
        if not event.description or event.observation_channel != "witnessed":
            continue
        item = {
            "event_id": str(event.event_id.value),
            "description": event.description,
            "occurred_at": str(event.occurred_at.microseconds),
            "observed_at": str(event.observed_at.microseconds),
            "ledger_position": str(event.ledger_position),
            "observation_channel": "witnessed",
        }
        if event.subject is not None:
            if event.subject.world_id != owner.world_id:
                raise EntityNotFoundError("chat_event_subject_world_invalid")
            item["subject_kind"] = (
                "character" if isinstance(event.subject, CharacterId) else "player"
            )
            item["subject_id"] = str(event.subject.value)
            item["participation"] = "actor" if event.subject == owner else "witness"
        size = len(json.dumps(item, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        if used + size + 1 > MAX_CHARACTER_EVENT_BYTES:
            continue
        result.append(item)
        used += size + 1
        if len(result) == MAX_CHARACTER_EVENTS:
            break
    return list(reversed(result))
