"""Read-only, evidence-backed activity context for the verified speaking Character."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from livingworld.application.errors import EntityNotFoundError
from livingworld.application.player_event_feed import KnownWorldEvent
from livingworld.domain.identifiers import CharacterId
from livingworld.domain.values import WorldTime

MAX_ACTIVITY_CONTEXT_BYTES = 2 * 1024


@dataclass(frozen=True, slots=True)
class CharacterActivitySnapshot:
    owner_character_id: CharacterId
    current_world_time: WorldTime
    world_paused: bool
    last_start: KnownWorldEvent | None = None
    planned_until: WorldTime | None = None
    presence_unchanged: bool = False


class CharacterActivityContextReader(Protocol):
    @property
    def owner_character_id(self) -> CharacterId: ...
    async def snapshot(self) -> CharacterActivitySnapshot | None: ...


async def character_activity_context(
    reader_factory: Callable[[CharacterId], CharacterActivityContextReader] | None,
    owner: CharacterId,
) -> dict[str, object] | None:
    if reader_factory is None:
        return None
    reader = reader_factory(owner)
    if reader.owner_character_id != owner:
        raise EntityNotFoundError("chat_activity_owner_invalid")
    snapshot = await reader.snapshot()
    if snapshot is None:
        return None
    if snapshot.owner_character_id != owner:
        raise EntityNotFoundError("chat_activity_owner_invalid")
    data: dict[str, object] = {
        "world_time_microseconds": str(snapshot.current_world_time.microseconds),
        "world_paused": snapshot.world_paused,
    }
    event = snapshot.last_start
    if event is None:
        return data
    if event.event_id.world_id != owner.world_id:
        raise EntityNotFoundError("chat_activity_world_invalid")
    if (
        event.event_type != "CharacterRoutineStarted"
        or event.observation_channel != "witnessed"
        or not event.description
        or event.occurred_at > snapshot.current_world_time
        or snapshot.planned_until is None
        or snapshot.planned_until <= event.occurred_at
    ):
        return data
    # Interval expiry frees occupancy; it is never evidence of an achieved outcome.
    phase = "changed_since_start"
    if snapshot.presence_unchanged:
        phase = (
            "within_planned_interval"
            if snapshot.current_world_time < snapshot.planned_until
            else "planned_interval_elapsed"
        )
    data["last_own_activity_start"] = {
        "event_id": str(event.event_id.value),
        "description": event.description,
        "elapsed_world_minutes": str(
            (snapshot.current_world_time.microseconds - event.occurred_at.microseconds)
            // 60_000_000
        ),
        "phase": phase,
    }
    size = len(json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    if size > MAX_ACTIVITY_CONTEXT_BYTES:
        del data["last_own_activity_start"]
    return data
