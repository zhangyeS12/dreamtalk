"""Group only linked, already authorized activity evidence; never query for more."""

from __future__ import annotations

from collections import defaultdict

from livingworld.application.player_event_feed import KnownWorldEvent
from livingworld.domain.identifiers import CharacterId, EventId

_TERMINAL_STARTS = {
    "CharacterRoutineEnded": "CharacterRoutineStarted",
    "CharacterRoutineInterrupted": "CharacterRoutineStarted",
    "SharedActivityEnded": "SharedActivityStarted",
    "SharedActivityInterrupted": "SharedActivityStarted",
}


def _linked(start: KnownWorldEvent, terminal: KnownWorldEvent) -> bool:
    if (
        _TERMINAL_STARTS.get(terminal.event_type) != start.event_type
        or terminal.activity_start_event_id != start.event_id
        or start.event_id.world_id != terminal.event_id.world_id
        or start.observation_channel != "witnessed"
        or terminal.observation_channel != "witnessed"
        or not start.description
        or not terminal.description
        or start.occurred_at > terminal.occurred_at
        or start.ledger_position >= terminal.ledger_position
    ):
        return False
    if start.event_type == "CharacterRoutineStarted":
        return (
            isinstance(start.subject, CharacterId)
            and start.subject.world_id == start.event_id.world_id
            and start.subject == terminal.subject
            and not start.participants
            and not terminal.participants
        )
    return (
        start.subject is None
        and terminal.subject is None
        and len(start.participants) == 2
        and len(terminal.participants) == 2
        and len(set(start.participants)) == 2
        and all(person.world_id == start.event_id.world_id for person in start.participants)
        and frozenset(start.participants) == frozenset(terminal.participants)
    )


def group_activity_experiences(
    events: tuple[KnownWorldEvent, ...],
) -> tuple[tuple[KnownWorldEvent, ...], ...]:
    """Each group's last event is its known state, not a claim about current presence.

    A terminal replaces its earlier start only when both are in this permission-filtered
    window. Missing, conflicting or mismatched links remain separate. Raw history stays
    intact; callers may rank both descriptions but send just the actual terminal event.
    """
    by_id = {event.event_id: event for event in events}
    terminals: dict[EventId, list[KnownWorldEvent]] = defaultdict(list)
    for event in by_id.values():
        if event.event_type in _TERMINAL_STARTS and event.activity_start_event_id is not None:
            terminals[event.activity_start_event_id].append(event)
    groups: dict[EventId, tuple[KnownWorldEvent, ...]] = {
        identity: (event,) for identity, event in by_id.items()
    }
    for start_id, endings in terminals.items():
        start = by_id.get(start_id)
        # A conflicting history has no safe unique terminal representative.
        if start is None or len(endings) != 1 or not _linked(start, endings[0]):
            continue
        terminal = endings[0]
        groups.pop(start_id)
        groups[terminal.event_id] = (start, terminal)
    return tuple(
        sorted(
            groups.values(), key=lambda group: (group[-1].occurred_at, group[-1].ledger_position)
        )
    )
