"""Owner-filtered, allowlisted event projection; never return a whole event body."""

from __future__ import annotations

import unicodedata
from uuid import UUID

from sqlalchemy import Text, and_, case, func, literal, select

from livingworld.application.observed_events import MAX_CHARACTER_EVENTS
from livingworld.application.player_event_feed import KnownWorldEvent
from livingworld.domain.identifiers import CharacterId, EventId, PlayerId, WorldId
from livingworld.infrastructure.persistence.models import (
    CharacterRecord,
    LocationRecord,
    ObservationRecord,
    PlayerRecord,
    WorldEventRecord,
)

_CHARACTER_TYPES = ("CharacterPlaced", "CharacterRoutineStarted")
_SUPPORTED_TYPES = ("PlayerMoved", "PlayerPlaced", *_CHARACTER_TYPES)


def witnessed_occurrence():
    return and_(
        ObservationRecord.channel == "witnessed",
        ObservationRecord.basis == "event_occurrence",
    )


def _uuid(value: object) -> UUID | None:
    if not isinstance(value, str) or len(value) not in (32, 36):
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


async def project_observed_events(
    session, world_id: WorldId, seen, *, limit: int, detailed_only: bool = False
) -> tuple[KnownWorldEvent, ...]:
    """`seen` must already be bound in SQL to a single authorized principal."""
    event = WorldEventRecord
    supported = and_(event.payload_version == 1, event.event_type.in_(_SUPPORTED_TYPES))
    eligible = and_(supported, seen.c.witnessed == 1)
    # Invalid JSON and unknown schemas cannot break the list or yield raw content.
    safe_body = case(
        (and_(eligible, func.json_valid(event.payload)), event.payload),
        else_=literal("{}", Text),
    )

    def reference(path: str, kinds: tuple[str, ...]):
        value = func.json_extract(safe_body, path)
        return case(
            (
                and_(
                    eligible,
                    event.event_type.in_(kinds),
                    func.json_type(safe_body, path) == "text",
                    func.length(value).in_((32, 36)),
                ),
                value,
            ),
            else_=None,
        )

    query = (
        select(
            event.event_id,
            event.event_type,
            event.occurred_at,
            event.ledger_position,
            seen.c.observed_at,
            reference("$.player_id", ("PlayerMoved", "PlayerPlaced")).label("player_id"),
            reference("$.character_id", _CHARACTER_TYPES).label("character_id"),
            case(
                (
                    event.event_type == "PlayerMoved",
                    reference("$.to_location_id", ("PlayerMoved",)),
                ),
                else_=reference("$.location_id", ("PlayerPlaced", *_CHARACTER_TYPES)),
            ).label("destination"),
            case(
                (
                    event.event_type == "PlayerMoved",
                    reference("$.from_location_id", ("PlayerMoved",)),
                ),
                else_=reference("$.before_location_id", _CHARACTER_TYPES),
            ).label("origin"),
            case(
                (
                    and_(eligible, event.event_type.in_(_CHARACTER_TYPES)),
                    func.json_type(safe_body, "$.before_location_id") != "null",
                ),
                else_=and_(eligible, event.event_type == "PlayerMoved"),
            ).label("origin_required"),
            case(
                (
                    and_(
                        eligible,
                        event.event_type == "CharacterRoutineStarted",
                        func.json_extract(safe_body, "$.activity").in_(("rest", "work", "leisure")),
                    ),
                    func.json_extract(safe_body, "$.activity"),
                ),
                else_=None,
            ).label("routine_activity"),
        )
        .join(seen, and_(event.event_id == seen.c.event_id, event.world_id == world_id.value))
        .where(event.world_id == world_id.value)
        .order_by(event.occurred_at.desc(), event.ledger_position.desc())
        .limit(limit)
    )
    if detailed_only:
        query = query.where(eligible)
    rows = (await session.execute(query)).all()
    players = {_uuid(row.player_id) for row in rows} - {None}
    characters = {_uuid(row.character_id) for row in rows} - {None}
    locations = {_uuid(value) for row in rows for value in (row.origin, row.destination)} - {None}

    async def names(model, key, identities: set) -> dict[UUID, str]:
        if not identities:
            return {}
        values = (
            await session.execute(
                select(key, func.substr(model.name, 1, 160)).where(
                    model.world_id == world_id.value, key.in_(identities)
                )
            )
        ).all()
        return {
            identity: (
                "".join(c for c in name if not unicodedata.category(c).startswith("C")).strip()
            )
            for identity, name in values
        }

    player_names = await names(PlayerRecord, PlayerRecord.player_id, players)
    character_names = await names(CharacterRecord, CharacterRecord.character_id, characters)
    location_names = await names(LocationRecord, LocationRecord.location_id, locations)

    def description(row) -> str | None:
        actor = _uuid(row.character_id if row.event_type in _CHARACTER_TYPES else row.player_id)
        actor_names = character_names if row.event_type in _CHARACTER_TYPES else player_names
        destination = _uuid(row.destination)
        origin = _uuid(row.origin)
        if actor not in actor_names or destination not in location_names:
            return None
        # A missing required origin is not guessed; optional setup origins remain absent.
        if row.origin_required is None:
            return None
        if (row.origin_required or row.origin is not None) and origin not in location_names:
            return None
        who = "角色" if row.event_type in _CHARACTER_TYPES else "玩家"
        subject = f"{who}「{actor_names[actor] or who}」"
        target = location_names[destination] or "未命名地点"
        if row.event_type == "CharacterRoutineStarted":
            activity = {"rest": "休息", "work": "工作", "leisure": "自由活动"}.get(
                row.routine_activity
            )
            if activity is None:
                return None
            movement = f"来到「{target}」，" if origin != destination else f"在「{target}」"
            return f"{subject}{movement}开始{activity}。"
        if origin is not None:
            source = location_names[origin] or "未命名地点"
            return f"{subject}从「{source}」到了「{target}」。"
        return f"{subject}来到了「{target}」。"

    result: list[KnownWorldEvent] = []
    for row in reversed(rows):
        text = description(row)
        if detailed_only and text is None:
            continue
        subject = None
        if text is not None:
            identity = _uuid(
                row.character_id if row.event_type in _CHARACTER_TYPES else row.player_id
            )
            if identity is not None:
                subject = (
                    CharacterId(world_id, identity)
                    if row.event_type in _CHARACTER_TYPES
                    else PlayerId(world_id, identity)
                )
        result.append(
            KnownWorldEvent(
                EventId(world_id, row.event_id),
                row.event_type,
                row.occurred_at,
                row.observed_at,
                row.ledger_position,
                text,
                "witnessed" if text is not None else None,
                subject=subject,
            )
        )
    return tuple(result)


def character_witnessed_events(owner: CharacterId, *, event_id: UUID | None = None):
    """Bind event-time access to one Character before any event payload is selected."""
    query = (
        select(
            ObservationRecord.target_event_id.label("event_id"),
            func.min(ObservationRecord.observed_at).label("observed_at"),
            literal(1).label("witnessed"),
        )
        .where(
            ObservationRecord.world_id == owner.world_id.value,
            ObservationRecord.principal_kind == "character",
            ObservationRecord.principal_character_id == owner.value,
            ObservationRecord.target_kind == "event",
            ObservationRecord.target_event_id.is_not(None),
            witnessed_occurrence(),
        )
        .group_by(ObservationRecord.target_event_id)
    )
    if event_id is not None:
        query = query.where(ObservationRecord.target_event_id == event_id)
    return query.subquery()


class SqlAlchemyCharacterObservedEventReader:
    def __init__(self, sessions, owner: CharacterId) -> None:
        self._sessions = sessions
        self._owner = owner

    @property
    def owner_character_id(self) -> CharacterId:
        return self._owner

    async def recent(self, *, limit: int) -> tuple[KnownWorldEvent, ...]:
        if type(limit) is not int or not 1 <= limit <= MAX_CHARACTER_EVENTS:
            raise ValueError("character_event_limit_invalid")
        owner = self._owner
        seen = character_witnessed_events(owner)
        async with self._sessions() as session:
            return await project_observed_events(
                session, owner.world_id, seen, limit=limit, detailed_only=True
            )
