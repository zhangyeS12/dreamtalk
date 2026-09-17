"""Authorization is in SQL before any assertion is materialized."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from livingworld.domain.identifiers import CharacterId, KnowledgeAssertionId, PlayerId, WorldId
from livingworld.domain.knowledge import KnowledgeAssertion, KnowledgeScope
from livingworld.domain.values import require_type, same_world
from livingworld.infrastructure.persistence.mapping import to_domain
from livingworld.infrastructure.persistence.models import KnowledgeAssertionRecord as Record


class _ScopedKnowledgeReader:
    def __init__(self, sessions: async_sessionmaker, world_id: WorldId, statement):
        self._sessions = sessions
        self._world_id = world_id
        self._statement = statement

    async def get(self, assertion_id: KnowledgeAssertionId) -> KnowledgeAssertion | None:
        require_type(assertion_id, KnowledgeAssertionId, "assertion_id")
        same_world(self._world_id, assertion_id)
        async with self._sessions() as session:
            record = (
                await session.scalars(
                    self._statement.where(Record.assertion_id == assertion_id.value)
                )
            ).one_or_none()
            return to_domain(record) if record is not None else None

    async def list(self) -> tuple[KnowledgeAssertion, ...]:
        async with self._sessions() as session:
            records = (await session.scalars(self._statement.order_by(Record.assertion_id))).all()
            return tuple(to_domain(record) for record in records)


class WorldTruthReader(_ScopedKnowledgeReader):
    def __init__(self, sessions: async_sessionmaker, world_id: WorldId):
        require_type(world_id, WorldId, "world_id")
        super().__init__(
            sessions,
            world_id,
            select(Record).where(
                Record.world_id == world_id.value,
                Record.scope == KnowledgeScope.TRUTH.value,
                Record.owner_character_id.is_(None),
                Record.owner_player_id.is_(None),
            ),
        )


class CharacterKnowledgeReader(_ScopedKnowledgeReader):
    def __init__(self, sessions: async_sessionmaker, character_id: CharacterId):
        require_type(character_id, CharacterId, "character_id")
        super().__init__(
            sessions,
            character_id.world_id,
            select(Record).where(
                Record.world_id == character_id.world_id.value,
                Record.scope == KnowledgeScope.CHARACTER_BELIEF.value,
                Record.owner_character_id == character_id.value,
                Record.owner_player_id.is_(None),
            ),
        )


class PlayerKnowledgeReader(_ScopedKnowledgeReader):
    def __init__(self, sessions: async_sessionmaker, player_id: PlayerId):
        require_type(player_id, PlayerId, "player_id")
        super().__init__(
            sessions,
            player_id.world_id,
            select(Record).where(
                Record.world_id == player_id.world_id.value,
                Record.scope == KnowledgeScope.PLAYER_KNOWLEDGE.value,
                Record.owner_player_id == player_id.value,
                Record.owner_character_id.is_(None),
            ),
        )
