"""SQL filters the local Player's Observations before selecting WorldEvents."""

from sqlalchemy import and_, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from livingworld.application.player_event_feed import (
    KnownWorldEvent,
    LocalPlayerPresence,
    SelectablePlayer,
)
from livingworld.domain.identifiers import EventId, PlayerId, WorldId
from livingworld.domain.participants import PlayerAvailability
from livingworld.domain.values import Revision
from livingworld.infrastructure.persistence.models import (
    LocalPlayerBindingRecord,
    ObservationRecord,
    PlayerPresenceRecord,
    PlayerRecord,
    WorldEventRecord,
)


class SqlAlchemyPlayerEventFeedStore:
    def __init__(self, sessions) -> None:
        self._sessions = sessions

    async def list_players(self, world_id: WorldId) -> tuple[SelectablePlayer, ...]:
        async with self._sessions() as session:
            rows = (
                await session.scalars(
                    select(PlayerRecord)
                    .where(PlayerRecord.world_id == world_id.value)
                    .order_by(PlayerRecord.name, PlayerRecord.player_id)
                )
            ).all()
            return tuple(
                SelectablePlayer(PlayerId(world_id, row.player_id), row.name) for row in rows
            )

    async def selected_player(self, world_id: WorldId) -> PlayerId | None:
        async with self._sessions() as session:
            value = await session.scalar(
                select(LocalPlayerBindingRecord.player_id).where(
                    LocalPlayerBindingRecord.world_id == world_id.value
                )
            )
            return PlayerId(world_id, value) if value is not None else None

    async def selected_presence(self, world_id: WorldId) -> LocalPlayerPresence | None:
        async with self._sessions() as session:
            row = (
                await session.execute(
                    select(PlayerPresenceRecord)
                    .join(
                        LocalPlayerBindingRecord,
                        (LocalPlayerBindingRecord.world_id == PlayerPresenceRecord.world_id)
                        & (LocalPlayerBindingRecord.player_id == PlayerPresenceRecord.player_id),
                    )
                    .where(LocalPlayerBindingRecord.world_id == world_id.value)
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            return LocalPlayerPresence(
                PlayerId(world_id, row.player_id),
                PlayerAvailability(row.availability),
                Revision(row.revision),
            )

    async def bind_player(self, player_id: PlayerId) -> None:
        async with self._sessions() as session, session.begin():
            exists = await session.scalar(
                select(PlayerRecord.player_id).where(
                    PlayerRecord.world_id == player_id.world_id.value,
                    PlayerRecord.player_id == player_id.value,
                )
            )
            if exists is None:
                raise ValueError("player_not_found_in_world")
            insert = sqlite_insert(LocalPlayerBindingRecord).values(
                world_id=player_id.world_id.value, player_id=player_id.value
            )
            await session.execute(
                insert.on_conflict_do_update(
                    index_elements=[LocalPlayerBindingRecord.world_id],
                    set_={"player_id": player_id.value},
                )
            )

    async def known_events(self, world_id: WorldId, limit: int) -> tuple[KnownWorldEvent, ...]:
        async with self._sessions() as session:
            seen = (
                select(
                    ObservationRecord.target_event_id.label("event_id"),
                    func.min(ObservationRecord.observed_at).label("observed_at"),
                )
                .join(
                    LocalPlayerBindingRecord,
                    and_(
                        LocalPlayerBindingRecord.world_id == ObservationRecord.world_id,
                        LocalPlayerBindingRecord.player_id == ObservationRecord.principal_player_id,
                    ),
                )
                .where(
                    ObservationRecord.world_id == world_id.value,
                    ObservationRecord.principal_kind == "player",
                    ObservationRecord.target_kind == "event",
                    ObservationRecord.target_event_id.is_not(None),
                )
                .group_by(ObservationRecord.target_event_id)
                .subquery()
            )
            rows = (
                await session.execute(
                    select(
                        WorldEventRecord.event_id,
                        WorldEventRecord.event_type,
                        WorldEventRecord.occurred_at,
                        WorldEventRecord.ledger_position,
                        seen.c.observed_at,
                    )
                    .join(
                        seen,
                        and_(
                            WorldEventRecord.event_id == seen.c.event_id,
                            WorldEventRecord.world_id == world_id.value,
                        ),
                    )
                    .order_by(
                        WorldEventRecord.occurred_at.desc(),
                        WorldEventRecord.ledger_position.desc(),
                    )
                    .limit(limit)
                )
            ).all()
            return tuple(
                KnownWorldEvent(
                    EventId(world_id, event_id), event_type, occurred_at, observed_at, position
                )
                for event_id, event_type, occurred_at, position, observed_at in reversed(rows)
            )
