"""Only a speaker's actually observed own routine may inform their current activity."""

from __future__ import annotations

from sqlalchemy import Text, and_, case, func, literal, select

from livingworld.application.character_activity_context import CharacterActivitySnapshot
from livingworld.application.ports import WorldTimeSource
from livingworld.domain.actions import RoutineActivity
from livingworld.domain.identifiers import CharacterId
from livingworld.domain.values import WorldTime
from livingworld.domain.world import ClockState
from livingworld.infrastructure.persistence.mapping import to_domain
from livingworld.infrastructure.persistence.models import (
    CharacterStateRecord,
    WorldClockRecord,
    WorldEventRecord,
)
from livingworld.infrastructure.persistence.observed_events import (
    character_witnessed_events,
    project_observed_events,
)


class SqlAlchemyCharacterActivityContextReader:
    def __init__(self, sessions, owner: CharacterId, world_time_source: WorldTimeSource) -> None:
        self._sessions = sessions
        self._owner = owner
        self._time_source = world_time_source

    @property
    def owner_character_id(self) -> CharacterId:
        return self._owner

    async def snapshot(self) -> CharacterActivitySnapshot | None:
        owner = self._owner
        event = WorldEventRecord
        state = CharacterStateRecord
        seen = character_witnessed_events(owner)
        body = case((func.json_valid(event.payload), event.payload), else_=literal("{}", Text))
        # No plans, pending candidates, other actors or whole payloads are materialized.
        own_start = (
            select(
                event.event_id.label("event_id"),
                func.json_extract(body, "$.activity").label("activity"),
                func.json_extract(body, "$.revision").label("revision"),
                func.json_extract(body, "$.location_id").label("location_id"),
                func.json_extract(body, "$.planned_until").label("planned_until"),
            )
            .join(seen, event.event_id == seen.c.event_id)
            .where(
                event.world_id == owner.world_id.value,
                event.event_type == "CharacterRoutineStarted",
                event.payload_version == 1,
                func.json_extract(body, "$.character_id") == str(owner.value),
                func.json_type(body, "$.revision") == "integer",
                func.json_type(body, "$.planned_until") == "integer",
                func.typeof(func.json_extract(body, "$.planned_until")) == "integer",
                func.typeof(func.json_extract(body, "$.revision")) == "integer",
                func.json_extract(body, "$.activity").in_(("rest", "work", "leisure")),
            )
            .order_by(event.occurred_at.desc(), event.ledger_position.desc())
            .limit(1)
            .subquery()
        )
        # Capture clock, last committed start and own current revision in one SQL snapshot.
        query = (
            select(
                WorldClockRecord,
                own_start.c.event_id,
                own_start.c.activity,
                own_start.c.planned_until,
                and_(
                    state.revision == own_start.c.revision,
                    func.replace(own_start.c.location_id, "-", "") == state.location_id,
                ).label("presence_unchanged"),
            )
            .select_from(WorldClockRecord)
            .outerjoin(own_start, literal(True))
            .outerjoin(
                state,
                and_(state.world_id == owner.world_id.value, state.character_id == owner.value),
            )
            .where(WorldClockRecord.world_id == owner.world_id.value)
        )
        async with self._sessions() as session:
            row = (await session.execute(query)).one_or_none()
            if row is None:
                return None
            clock = to_domain(row[0])
            now = self._time_source.read(clock)
            if row.event_id is None:
                return CharacterActivitySnapshot(owner, now, clock.state is ClockState.PAUSED)
            events = await project_observed_events(
                session,
                owner.world_id,
                character_witnessed_events(owner, event_id=row.event_id),
                limit=1,
                detailed_only=True,
            )
            return CharacterActivitySnapshot(
                owner,
                now,
                clock.state is ClockState.PAUSED,
                last_start=events[0] if events else None,
                planned_until=WorldTime(row.planned_until),
                presence_unchanged=row.presence_unchanged is True,
                activity=RoutineActivity(row.activity),
            )
