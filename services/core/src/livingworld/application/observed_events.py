"""Bounded observations supplied only to the authorized speaking Character."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from livingworld.application.errors import EntityNotFoundError
from livingworld.application.player_event_feed import KnownWorldEvent
from livingworld.domain.identifiers import CharacterId, EventId

MAX_CHARACTER_EVENTS = 12
MAX_CHARACTER_EVENT_BYTES = 8 * 1024


@dataclass(frozen=True, slots=True)
class CharacterEventRecall:
    events: tuple[KnownWorldEvent, ...]
    related_ids: tuple[EventId, ...] = ()


def experience_queries(current, transcript) -> tuple[str, ...]:
    """Use the current question and two already permitted preceding utterances."""
    previous = [
        item.text[:1000] for item in reversed(transcript) if item.position < current.position
    ]
    return tuple(dict.fromkeys((current.text[:2000], *previous[:2])))


class CharacterObservedEventReader(Protocol):
    @property
    def owner_character_id(self) -> CharacterId: ...
    async def recent(self, *, limit: int) -> tuple[KnownWorldEvent, ...]: ...


async def character_observed_events(
    reader_factory: Callable[[CharacterId], CharacterObservedEventReader] | None,
    owner: CharacterId,
    *,
    query_texts: tuple[str, ...] = (),
) -> list[dict[str, object]]:
    if reader_factory is None:
        return []
    reader = reader_factory(owner)
    if reader.owner_character_id != owner:
        raise EntityNotFoundError("chat_event_owner_invalid")
    recall = getattr(reader, "recall", None)
    selection = (
        await recall(query_texts, limit=MAX_CHARACTER_EVENTS)
        if recall is not None and query_texts
        else CharacterEventRecall(await reader.recent(limit=MAX_CHARACTER_EVENTS))
    )
    related = frozenset(selection.related_ids)
    if any(identity.world_id != owner.world_id for identity in related):
        raise EntityNotFoundError("chat_event_world_invalid")
    events = selection.events
    result: list[dict[str, object]] = []
    used = 2
    # Related older evidence competes before recency within the same byte ceiling.
    ordered = sorted(
        events,
        key=lambda event: (event.event_id in related, event.occurred_at, event.ledger_position),
        reverse=True,
    )
    included_ids = set()
    for event in ordered:
        if event.event_id.world_id != owner.world_id:
            raise EntityNotFoundError("chat_event_world_invalid")
        if event.event_id in included_ids:
            continue
        if not event.description or event.observation_channel != "witnessed":
            continue
        item: dict[str, object] = {
            "event_id": str(event.event_id.value),
            "description": event.description,
            "event_type": event.event_type,
            "occurred_at": str(event.occurred_at.microseconds),
            "observed_at": str(event.observed_at.microseconds),
            "ledger_position": str(event.ledger_position),
            "observation_channel": "witnessed",
            "recall_basis": "topic_match" if event.event_id in related else "recent",
        }
        if event.subject is not None:
            if event.subject.world_id != owner.world_id:
                raise EntityNotFoundError("chat_event_subject_world_invalid")
            item["subject_kind"] = (
                "character" if isinstance(event.subject, CharacterId) else "player"
            )
            item["subject_id"] = str(event.subject.value)
            item["participation"] = "actor" if event.subject == owner else "witness"
        if event.participants:
            if any(identity.world_id != owner.world_id for identity in event.participants):
                raise EntityNotFoundError("chat_event_subject_world_invalid")
            item["participant_character_ids"] = [
                str(identity.value) for identity in event.participants
            ]
            item["participation"] = "participant" if owner in event.participants else "witness"
        size = len(json.dumps(item, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        if used + size + 1 > MAX_CHARACTER_EVENT_BYTES:
            continue
        result.append(item)
        included_ids.add(event.event_id)
        used += size + 1
        if len(result) == MAX_CHARACTER_EVENTS:
            break
    return sorted(result, key=lambda item: (int(item["occurred_at"]), int(item["ledger_position"])))
