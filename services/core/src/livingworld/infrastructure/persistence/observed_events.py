"""Owner-filtered, allowlisted event projection; never return a whole event body."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Text, and_, case, func, literal, select

from livingworld.application.experience_lifecycle import group_activity_experiences
from livingworld.application.observed_events import MAX_CHARACTER_EVENTS, CharacterEventRecall
from livingworld.application.player_event_feed import KnownWorldEvent
from livingworld.domain.identifiers import CharacterId, EventId, PlayerId, WorldId
from livingworld.infrastructure.persistence.models import (
    CharacterRecord,
    LocationRecord,
    ObservationRecord,
    PlayerRecord,
    WorldEventRecord,
)

_ROUTINE_TYPES = ("CharacterRoutineStarted", "CharacterRoutineEnded", "CharacterRoutineInterrupted")
_CHARACTER_TYPES = ("CharacterPlaced", *_ROUTINE_TYPES)
_SHARED_TYPES = ("SharedActivityStarted", "SharedActivityEnded", "SharedActivityInterrupted")
_TERMINAL_TYPES = (*_ROUTINE_TYPES[1:], *_SHARED_TYPES[1:])
_PAIR_TYPES = ("CharactersMet", *_SHARED_TYPES)
_SUPPORTED_TYPES = ("PlayerMoved", "PlayerPlaced", *_PAIR_TYPES, *_CHARACTER_TYPES)


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
            reference("$.start_event_id", _TERMINAL_TYPES).label("activity_start_event_id"),
            reference("$.player_id", ("PlayerMoved", "PlayerPlaced")).label("player_id"),
            reference("$.first_character_id", _PAIR_TYPES).label("first_character_id"),
            reference("$.second_character_id", _PAIR_TYPES).label("second_character_id"),
            case((eligible, func.json_extract(safe_body, "$.purpose")), else_=None).label(
                "purpose"
            ),
            reference("$.character_id", _CHARACTER_TYPES).label("character_id"),
            case(
                (
                    and_(
                        eligible,
                        event.event_type.in_(_SHARED_TYPES),
                        func.json_extract(safe_body, "$.activity").in_(
                            ("shared_rest", "shared_leisure")
                        ),
                    ),
                    func.json_extract(safe_body, "$.activity"),
                ),
                else_=None,
            ).label("shared_activity"),
            case(
                (
                    event.event_type == "PlayerMoved",
                    reference("$.to_location_id", ("PlayerMoved",)),
                ),
                else_=reference("$.location_id", ("PlayerPlaced", *_PAIR_TYPES, *_CHARACTER_TYPES)),
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
                        event.event_type.in_(_ROUTINE_TYPES),
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
    characters = {
        _uuid(identity)
        for row in rows
        for identity in (row.character_id, row.first_character_id, row.second_character_id)
    } - {None}
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
        if row.event_type in _PAIR_TYPES:
            first, second, location = (
                _uuid(row.first_character_id),
                _uuid(row.second_character_id),
                _uuid(row.destination),
            )
            if (
                first == second
                or first not in character_names
                or second not in character_names
                or location not in location_names
                or (row.event_type == "CharactersMet" and row.purpose != "brief_greeting")
                or (
                    row.event_type in _SHARED_TYPES
                    and row.shared_activity not in {"shared_rest", "shared_leisure"}
                )
            ):
                return None
            if row.event_type in _SHARED_TYPES:
                activity = "共同休息" if row.shared_activity == "shared_rest" else "共同自由活动"
                phase = {
                    "SharedActivityStarted": "已开始",
                    "SharedActivityEnded": "已正常结束",
                    "SharedActivityInterrupted": "已中断",
                }[row.event_type]
                return (
                    f"角色「{character_names[first]}」与角色「{character_names[second]}」"
                    f"在「{location_names[location]}」的{activity}{phase}；"
                    "未记录谈话内容、物品或关系成果。"
                )
            return (
                f"角色「{character_names[first]}」与角色「{character_names[second]}」"
                f"在「{location_names[location]}」短暂碰面，打过招呼。"
            )
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
        if row.event_type in _ROUTINE_TYPES:
            activity = {"rest": "休息", "work": "工作", "leisure": "自由活动"}.get(
                row.routine_activity
            )
            if activity is None:
                return None
            if row.event_type == "CharacterRoutineEnded":
                return f"{subject}在「{target}」的{activity}时段已结束；没有记录任务成果。"
            if row.event_type == "CharacterRoutineInterrupted":
                return f"{subject}此前在「{target}」的{activity}已中断。"
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
        if text is not None and row.event_type not in _PAIR_TYPES:
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
                activity_start_event_id=EventId(world_id, start_id)
                if text is not None and (start_id := _uuid(row.activity_start_event_id)) is not None
                else None,
                participants=tuple(
                    CharacterId(world_id, identity)
                    for identity in (_uuid(row.first_character_id), _uuid(row.second_character_id))
                )
                if text is not None and row.event_type in _PAIR_TYPES
                else (),
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


@dataclass(frozen=True, slots=True)
class _ExperienceDocument:
    text: str
    event: KnownWorldEvent


class SqlAlchemyCharacterObservedEventReader:
    def __init__(self, sessions, owner: CharacterId, ranker=None) -> None:
        self._sessions = sessions
        self._owner = owner
        self._ranker = ranker

    @property
    def owner_character_id(self) -> CharacterId:
        return self._owner

    async def recent(self, *, limit: int) -> tuple[KnownWorldEvent, ...]:
        if type(limit) is not int or not 1 <= limit <= MAX_CHARACTER_EVENTS:
            raise ValueError("character_event_limit_invalid")
        owner = self._owner
        seen = character_witnessed_events(owner)
        async with self._sessions() as session:
            pool = await project_observed_events(
                session, owner.world_id, seen, limit=128, detailed_only=True
            )
        return tuple(group[-1] for group in group_activity_experiences(pool)[-limit:])

    async def recall(self, queries: tuple[str, ...], *, limit: int) -> CharacterEventRecall:
        """Rank at most 128 owner-authorized projections, never the global ledger."""
        if type(limit) is not int or not 1 <= limit <= MAX_CHARACTER_EVENTS:
            raise ValueError("character_event_limit_invalid")
        if self._ranker is None or not queries:
            return CharacterEventRecall(await self.recent(limit=limit))
        queries = tuple(
            query[:2000] for query in queries[:3] if isinstance(query, str) and query.strip()
        )
        if not queries:
            return CharacterEventRecall(await self.recent(limit=limit))
        owner = self._owner
        async with self._sessions() as session:
            pool = await project_observed_events(
                session,
                owner.world_id,
                character_witnessed_events(owner),
                limit=128,
                detailed_only=True,
            )
        # Release the database transaction before the existing bounded FTS worker.
        groups = group_activity_experiences(pool)
        pool = tuple(group[-1] for group in groups)
        documents = []
        used = 0
        for group in reversed(groups):
            # Search either authorized phase; return the actual known terminal.
            text = "\n".join(item.description for item in group)
            size = len(text.encode("utf-8"))
            if used + size > 256 * 1024:
                continue
            documents.append(_ExperienceDocument(text, group[-1]))
            used += size
        documents = tuple(documents)
        hits = await self._ranker.rank_queries(queries, documents, limit=16)
        # Keep recent grounding while allowing up to four older topic matches.
        recent_count = max(1, limit - min(4, limit // 3))
        selected = {item.event_id: item for item in pool[-recent_count:]}
        related = []
        for document in hits:
            if len(selected) >= limit:
                break
            if document.event.event_id in selected:
                continue
            selected[document.event.event_id] = document.event
            related.append(document.event.event_id)
            if len(selected) == limit:
                break
        for item in reversed(pool):
            if len(selected) == limit:
                break
            selected.setdefault(item.event_id, item)
        return CharacterEventRecall(
            tuple(
                sorted(selected.values(), key=lambda item: (item.occurred_at, item.ledger_position))
            ),
            tuple(related),
        )
