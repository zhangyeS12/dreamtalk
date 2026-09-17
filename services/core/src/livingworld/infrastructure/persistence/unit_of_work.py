"""SQLAlchemy capabilities sharing exactly one command transaction/session."""

import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from livingworld.application.errors import IdempotencyConflictError
from livingworld.application.fingerprints import canonical_json, id_input
from livingworld.application.results import CommandResult, RelationshipReference
from livingworld.domain.commands import CommandReceipt
from livingworld.domain.contracts import RequestId
from livingworld.domain.events import WorldEvent
from livingworld.domain.identifiers import (
    CharacterId,
    KnowledgeAssertionId,
    LocationId,
    ObservationId,
    PlayerId,
    PrincipalId,
    WorldId,
)
from livingworld.domain.knowledge import KnowledgeAssertion, Observation
from livingworld.domain.participants import Character, CharacterState, Player, PlayerPresence
from livingworld.domain.relationships import Relationship
from livingworld.domain.values import Revision
from livingworld.domain.world import Location, World
from livingworld.infrastructure.persistence.errors import (
    PersistenceConflictError,
    PersistenceDataError,
)
from livingworld.infrastructure.persistence.mapping import to_domain, to_record
from livingworld.infrastructure.persistence.models import (
    CharacterRecord,
    CharacterStateRecord,
    CommandReceiptRecord,
    KnowledgeAssertionRecord,
    LocationRecord,
    PlayerPresenceRecord,
    PlayerRecord,
    RelationshipRecord,
    WorldRecord,
)


class WorldRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get(self, world_id: WorldId) -> World | None:
        record = (
            await self._session.scalars(
                select(WorldRecord)
                .options(selectinload(WorldRecord.clock))
                .where(WorldRecord.world_id == world_id.value)
            )
        ).one_or_none()
        return to_domain(record) if record is not None else None

    async def add(self, world: World) -> None:
        self._session.add(to_record(world))
        await self._session.flush()


class LocationRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get(self, location_id: LocationId) -> Location | None:
        record = await self._session.get(
            LocationRecord, (location_id.world_id.value, location_id.value)
        )
        return to_domain(record) if record is not None else None

    async def add(self, location: Location) -> None:
        self._session.add(to_record(location))
        await self._session.flush()


class PlayerRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get(self, player_id: PlayerId) -> Player | None:
        record = await self._session.get(PlayerRecord, (player_id.world_id.value, player_id.value))
        return to_domain(record) if record is not None else None

    async def presence(self, player_id: PlayerId) -> PlayerPresence | None:
        record = await self._session.get(
            PlayerPresenceRecord, (player_id.world_id.value, player_id.value)
        )
        return to_domain(record) if record is not None else None

    async def add(self, player: Player, presence: PlayerPresence) -> None:
        self._session.add(to_record(player))
        await self._session.flush()
        self._session.add(to_record(presence))
        await self._session.flush()

    async def replace_presence(self, presence: PlayerPresence) -> None:
        await self._session.merge(to_record(presence))
        await self._session.flush()


class CharacterRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get(self, character_id: CharacterId) -> Character | None:
        record = await self._session.get(
            CharacterRecord, (character_id.world_id.value, character_id.value)
        )
        return to_domain(record) if record is not None else None

    async def state(self, character_id: CharacterId) -> CharacterState | None:
        record = await self._session.get(
            CharacterStateRecord, (character_id.world_id.value, character_id.value)
        )
        return to_domain(record) if record is not None else None

    async def add(self, character: Character) -> None:
        self._session.add(to_record(character))
        await self._session.flush()

    async def put_state(self, state: CharacterState) -> None:
        await self._session.merge(to_record(state))
        await self._session.flush()


def relationship_key(source: PrincipalId, target: PrincipalId) -> tuple:
    return (
        source.world_id.value,
        "character" if isinstance(source, CharacterId) else "player",
        source.value,
        "character" if isinstance(target, CharacterId) else "player",
        target.value,
    )


class RelationshipRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get(self, source: PrincipalId, target: PrincipalId) -> Relationship | None:
        record = await self._session.get(RelationshipRecord, relationship_key(source, target))
        return to_domain(record) if record is not None else None

    async def put(self, relationship: Relationship) -> None:
        await self._session.merge(to_record(relationship))
        await self._session.flush()


class EventAppender:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def append(self, event: WorldEvent) -> None:
        self._session.add(to_record(event))
        await self._session.flush()


class KnowledgeMutationRepository:
    """Exact-source lookup for trusted acquisition, not a principal query port."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get(self, assertion_id: KnowledgeAssertionId) -> KnowledgeAssertion | None:
        record = await self._session.get(
            KnowledgeAssertionRecord, (assertion_id.world_id.value, assertion_id.value)
        )
        return to_domain(record) if record is not None else None

    async def add(self, assertion: KnowledgeAssertion) -> None:
        self._session.add(to_record(assertion))
        await self._session.flush()


class ObservationAppender:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def add(self, observation: Observation) -> None:
        self._session.add(to_record(observation))
        await self._session.flush()


def _decode_id(value: dict):
    identity = UUID(value["id"])
    if value["kind"] == "WorldId":
        return WorldId(identity)
    world = WorldId(UUID(value["world_id"]))
    types = {
        "LocationId": LocationId,
        "PlayerId": PlayerId,
        "CharacterId": CharacterId,
        "KnowledgeAssertionId": KnowledgeAssertionId,
        "ObservationId": ObservationId,
    }
    return types[value["kind"]](world, identity)


def _encode_result(result: CommandResult) -> str:
    reference = result.entity_reference
    entity = (
        {
            "kind": "Relationship",
            "source": id_input(reference.source_id),
            "target": id_input(reference.target_id),
        }
        if isinstance(reference, RelationshipReference)
        else id_input(reference)
    )
    return canonical_json(
        {
            "result_version": 1,
            "entity_reference": entity,
            "resulting_revision": result.resulting_revision.value,
            "observation_id": id_input(result.observation_id)
            if result.observation_id is not None
            else None,
        }
    )


class CommandReceiptRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def existing(self, request_id: RequestId, fingerprint: str) -> CommandResult | None:
        records = (
            await self._session.scalars(
                select(CommandReceiptRecord).where(
                    CommandReceiptRecord.request_id == request_id.value
                )
            )
        ).all()
        if not records:
            return None
        if len(records) != 1 or records[0].command_fingerprint != fingerprint:
            raise IdempotencyConflictError(
                "RequestId has different or unverifiable command semantics"
            )
        record = records[0]
        try:
            receipt = to_domain(record)
            if receipt.status != "committed" or receipt.completed_at is None:
                raise ValueError("Incomplete command receipt")
            value = json.loads(record.result_payload)
            if value["result_version"] != 1:
                raise ValueError("Unknown result version")
            entity = value["entity_reference"]
            reference = (
                RelationshipReference(_decode_id(entity["source"]), _decode_id(entity["target"]))
                if entity["kind"] == "Relationship"
                else _decode_id(entity)
            )
            return CommandResult(
                request_id,
                receipt.command_type,
                reference,
                Revision(value["resulting_revision"]),
                observation_id=_decode_id(value["observation_id"])
                if value.get("observation_id") is not None
                else None,
            )
        except (ValueError, KeyError, TypeError):
            raise PersistenceDataError("invalid_command_result") from None

    async def add(self, receipt: CommandReceipt, fingerprint: str, result: CommandResult) -> None:
        record = to_record(receipt)
        record.command_fingerprint = fingerprint
        record.result_payload = _encode_result(result)
        self._session.add(record)
        await self._session.flush()


class SqlAlchemyUnitOfWork:
    def __init__(self, sessions: async_sessionmaker):
        self._sessions = sessions

    async def __aenter__(self):
        self._session = self._sessions()
        await self._session.begin()
        self.worlds = WorldRepository(self._session)
        self.locations = LocationRepository(self._session)
        self.players = PlayerRepository(self._session)
        self.characters = CharacterRepository(self._session)
        self.relationships = RelationshipRepository(self._session)
        self.knowledge = KnowledgeMutationRepository(self._session)
        self.observations = ObservationAppender(self._session)
        self.events = EventAppender(self._session)
        self.receipts = CommandReceiptRepository(self._session)
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        try:
            await self._session.rollback()
        finally:
            await self._session.close()
        if exc_type is not None and issubclass(exc_type, IntegrityError):
            raise PersistenceConflictError("command_persistence_conflict") from None

    async def commit(self) -> None:
        await self._session.commit()
