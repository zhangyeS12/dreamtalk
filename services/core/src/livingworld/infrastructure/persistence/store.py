"""Read-only snapshot inspection; production mutations use command UnitOfWork."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import selectinload

from livingworld.domain.commands import CommandReceipt
from livingworld.domain.events import WorldEvent
from livingworld.domain.identifiers import CharacterId, EventId
from livingworld.domain.knowledge import KnowledgeAssertion, Observation
from livingworld.domain.participants import Character, CharacterState, Player, PlayerPresence
from livingworld.domain.relationships import Relationship
from livingworld.domain.world import Location, LocationConnection, World, WorldClock
from livingworld.infrastructure.persistence.mapping import DomainObject, to_domain
from livingworld.infrastructure.persistence.models import (
    CharacterRecord,
    CharacterStateRecord,
    CommandReceiptRecord,
    KnowledgeAssertionRecord,
    LocationConnectionRecord,
    LocationRecord,
    ObservationRecord,
    PlayerPresenceRecord,
    PlayerRecord,
    RelationshipRecord,
    WorldClockRecord,
    WorldEventRecord,
    WorldRecord,
)


class PersistenceStore:
    """Reload snapshots without exposing AsyncSession or ORM records."""

    def __init__(self, sessions: async_sessionmaker):
        self._sessions = sessions

    async def reload(self, entity: DomainObject) -> DomainObject | None:
        model, key = self._identity(entity)
        async with self._sessions() as session:
            if model is WorldRecord:
                statement = (
                    select(WorldRecord)
                    .options(selectinload(WorldRecord.clock))
                    .where(WorldRecord.world_id == key)
                )
                record = (await session.scalars(statement)).one_or_none()
            else:
                record = await session.get(model, key)
            return to_domain(record) if record is not None else None

    @staticmethod
    def _identity(entity: DomainObject):
        world = entity.world_id.value
        if isinstance(entity, World):
            return WorldRecord, world
        if isinstance(entity, WorldClock):
            return WorldClockRecord, world
        if isinstance(entity, Location):
            return LocationRecord, (world, entity.location_id.value)
        if isinstance(entity, LocationConnection):
            return LocationConnectionRecord, (world, entity.source_id.value, entity.target_id.value)
        if isinstance(entity, Player):
            return PlayerRecord, (world, entity.player_id.value)
        if isinstance(entity, PlayerPresence):
            return PlayerPresenceRecord, (world, entity.player_id.value)
        if isinstance(entity, Character):
            return CharacterRecord, (world, entity.character_id.value)
        if isinstance(entity, CharacterState):
            return CharacterStateRecord, (world, entity.character_id.value)
        if isinstance(entity, Relationship):
            source_kind = "character" if isinstance(entity.source_id, CharacterId) else "player"
            target_kind = "character" if isinstance(entity.target_id, CharacterId) else "player"
            return RelationshipRecord, (
                world,
                source_kind,
                entity.source_id.value,
                target_kind,
                entity.target_id.value,
            )
        if isinstance(entity, WorldEvent):
            return WorldEventRecord, (world, entity.event_id.value)
        if isinstance(entity, KnowledgeAssertion):
            return KnowledgeAssertionRecord, (world, entity.assertion_id.value)
        if isinstance(entity, Observation):
            principal_kind = (
                "character" if isinstance(entity.principal_id, CharacterId) else "player"
            )
            target_kind = "event" if isinstance(entity.target_id, EventId) else "assertion"
            return ObservationRecord, (
                world,
                principal_kind,
                entity.principal_id.value,
                target_kind,
                entity.target_id.value,
                entity.channel.value,
                entity.observed_at,
            )
        if isinstance(entity, CommandReceipt):
            return CommandReceiptRecord, (world, entity.request_id.value)
        raise TypeError(f"No persistence identity for {type(entity).__name__}")
