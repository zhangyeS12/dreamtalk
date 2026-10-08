"""SQLAlchemy capabilities sharing exactly one command transaction/session."""

import json
from datetime import UTC, datetime
from sqlite3 import SQLITE_CONSTRAINT_PRIMARYKEY, SQLITE_CONSTRAINT_UNIQUE
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from livingworld.application.errors import EntityAlreadyExistsError, IdempotencyConflictError
from livingworld.application.fingerprints import canonical_json, id_input
from livingworld.application.results import (
    ActionResult,
    CommandResult,
    MemoryResult,
    RelationshipReference,
    SceneResult,
)
from livingworld.domain.actions import ActionRejectionReason, ActionResolutionStatus
from livingworld.domain.commands import CommandReceipt
from livingworld.domain.contracts import RequestId
from livingworld.domain.errors import ConcurrencyConflictError, DomainInvariantError
from livingworld.domain.events import WorldEvent
from livingworld.domain.identifiers import (
    CharacterId,
    EventId,
    KnowledgeAssertionId,
    LocationId,
    MemoryId,
    ObservationId,
    PlayerId,
    PrincipalId,
    SceneId,
    WorldId,
)
from livingworld.domain.knowledge import KnowledgeAssertion, Observation
from livingworld.domain.participants import Character, CharacterState, Player, PlayerPresence
from livingworld.domain.relationships import Relationship
from livingworld.domain.scenes import Scene, SceneParticipant
from livingworld.domain.values import Revision, WorldTime
from livingworld.domain.world import Location, World
from livingworld.infrastructure.persistence.activation import SqlAlchemyActivationRepository
from livingworld.infrastructure.persistence.errors import (
    PersistenceConflictError,
    PersistenceDataError,
)
from livingworld.infrastructure.persistence.mapping import to_domain, to_record
from livingworld.infrastructure.persistence.memory_repository import (
    SqlAlchemyMemoryMutationRepository,
)
from livingworld.infrastructure.persistence.models import (
    CharacterRecord,
    CharacterStateRecord,
    CommandReceiptRecord,
    KnowledgeAssertionRecord,
    LocalPlayerBindingRecord,
    LocationRecord,
    ObservationRecord,
    PlayerPresenceRecord,
    PlayerRecord,
    RelationshipRecord,
    SceneParticipantRecord,
    SceneRecord,
    WorldEventRecord,
    WorldLedgerCursorRecord,
    WorldRecord,
)
from livingworld.infrastructure.persistence.offline_contact_models import (
    LocalSessionVisibilityRecord,
)


async def _add_unique(session: AsyncSession, record: object, conflict: Exception) -> None:
    session.add(record)
    try:
        await session.flush()
    except IntegrityError as error:
        # Only an actual identity UNIQUE/PK collision has these semantics.
        # Foreign-key, CHECK and other failures remain infrastructure errors.
        if getattr(error.orig, "sqlite_errorcode", None) in (
            SQLITE_CONSTRAINT_PRIMARYKEY,
            SQLITE_CONSTRAINT_UNIQUE,
        ):
            raise conflict from None
        raise


def _conflict(kind: str, identity: object, expected: Revision | None) -> ConcurrencyConflictError:
    return ConcurrencyConflictError(
        f"{kind} does not match expected existence/revision",
        resource_kind=kind,
        resource_identity=identity,
        expected_revision=expected,
    )


def _result_revision(resulting: Revision, expected: Revision) -> None:
    if resulting != expected.advance(expected):
        raise DomainInvariantError("CAS must persist exactly the next revision")


async def _cas(session: AsyncSession, statement, conflict: ConcurrencyConflictError) -> None:
    result = await session.execute(statement.execution_options(synchronize_session=False))
    if result.rowcount != 1:
        raise conflict


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
        await _add_unique(
            self._session, to_record(world), EntityAlreadyExistsError("World already exists")
        )


class LocationRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get(self, location_id: LocationId) -> Location | None:
        record = await self._session.get(
            LocationRecord, (location_id.world_id.value, location_id.value)
        )
        return to_domain(record) if record is not None else None

    async def add(self, location: Location) -> None:
        await _add_unique(
            self._session, to_record(location), EntityAlreadyExistsError("Location already exists")
        )

    async def replace(self, location: Location, expected_revision: Revision) -> None:
        result = await self._session.execute(
            update(LocationRecord)
            .where(
                LocationRecord.world_id == location.world_id.value,
                LocationRecord.location_id == location.location_id.value,
                LocationRecord.revision == expected_revision.value,
            )
            .values(name=location.name, revision=location.revision.value)
        )
        if result.rowcount != 1:
            raise _conflict("Location", location.location_id, expected_revision)


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
        await _add_unique(
            self._session, to_record(player), EntityAlreadyExistsError("Player already exists")
        )
        self._session.add(to_record(presence))
        await self._session.flush()

    async def replace_presence(self, presence: PlayerPresence, expected_revision: Revision) -> None:
        _result_revision(presence.revision, expected_revision)
        row = PlayerPresenceRecord
        await _cas(
            self._session,
            update(row)
            .where(
                row.world_id == presence.world_id.value,
                row.player_id == presence.player_id.value,
                row.revision == expected_revision.value,
            )
            .values(
                location_id=presence.location_id.value,
                activity=presence.activity.value,
                availability=presence.availability.value,
                revision=presence.revision.value,
            ),
            _conflict("PlayerPresence", presence.player_id, expected_revision),
        )

    async def at_location(self, location_id: LocationId) -> tuple[PlayerId, ...]:
        values = (
            await self._session.scalars(
                select(PlayerPresenceRecord.player_id)
                .where(
                    PlayerPresenceRecord.world_id == location_id.world_id.value,
                    PlayerPresenceRecord.location_id == location_id.value,
                    PlayerPresenceRecord.activity == "active",
                )
                .order_by(PlayerPresenceRecord.player_id)
            )
        ).all()
        visibility = await self._session.get(LocalSessionVisibilityRecord, 1)
        binding = await self._session.get(LocalPlayerBindingRecord, location_id.world_id.value)
        if (
            visibility is not None
            and binding is not None
            and (
                visibility.world_id != location_id.world_id.value
                or visibility.visible_until <= datetime.now(UTC)
            )
        ):
            values = [value for value in values if value != binding.player_id]
        return tuple(PlayerId(location_id.world_id, value) for value in values)


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
        await _add_unique(
            self._session,
            to_record(character),
            EntityAlreadyExistsError("Character already exists"),
        )

    async def put_state(self, state: CharacterState, expected_revision: Revision | None) -> None:
        conflict = _conflict("CharacterState", state.character_id, expected_revision)
        if expected_revision is None:
            if state.revision != Revision():
                raise DomainInvariantError("New CharacterState must start at revision zero")
            await _add_unique(self._session, to_record(state), conflict)
        else:
            _result_revision(state.revision, expected_revision)
            row = CharacterStateRecord
            await _cas(
                self._session,
                update(row)
                .where(
                    row.world_id == state.world_id.value,
                    row.character_id == state.character_id.value,
                    row.revision == expected_revision.value,
                )
                .values(location_id=state.location_id.value, revision=state.revision.value),
                conflict,
            )

    async def at_location(self, location_id: LocationId) -> tuple[CharacterId, ...]:
        values = (
            await self._session.scalars(
                select(CharacterStateRecord.character_id)
                .where(
                    CharacterStateRecord.world_id == location_id.world_id.value,
                    CharacterStateRecord.location_id == location_id.value,
                )
                .order_by(CharacterStateRecord.character_id)
            )
        ).all()
        return tuple(CharacterId(location_id.world_id, value) for value in values)


def _principal_columns(principal: PrincipalId) -> tuple[str, UUID]:
    return (
        ("character", principal.value)
        if isinstance(principal, CharacterId)
        else ("player", principal.value)
    )


class SceneRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get(self, scene_id: SceneId) -> Scene | None:
        record = await self._session.get(SceneRecord, (scene_id.world_id.value, scene_id.value))
        return to_domain(record) if record is not None else None

    async def add(self, scene: Scene, participants: tuple[SceneParticipant, ...]) -> None:
        await _add_unique(
            self._session, to_record(scene), EntityAlreadyExistsError("Scene already exists")
        )
        for participant in participants:
            await self.add_participant(participant)

    async def replace(self, scene: Scene, expected_revision: Revision) -> None:
        _result_revision(scene.revision, expected_revision)
        row = SceneRecord
        await _cas(
            self._session,
            update(row)
            .where(
                row.world_id == scene.world_id.value,
                row.scene_id == scene.scene_id.value,
                row.revision == expected_revision.value,
            )
            .values(
                status=scene.status.value,
                ended_at=scene.ended_at,
                revision=scene.revision.value,
            ),
            _conflict("Scene", scene.scene_id, expected_revision),
        )

    async def active_participants(self, scene_id: SceneId) -> tuple[SceneParticipant, ...]:
        records = (
            await self._session.scalars(
                select(SceneParticipantRecord)
                .where(
                    SceneParticipantRecord.world_id == scene_id.world_id.value,
                    SceneParticipantRecord.scene_id == scene_id.value,
                    SceneParticipantRecord.left_at.is_(None),
                )
                .order_by(
                    SceneParticipantRecord.principal_kind,
                    SceneParticipantRecord.principal_id,
                )
            )
        ).all()
        return tuple(to_domain(record) for record in records)

    async def active_for_principal(self, principal_id: PrincipalId) -> SceneParticipant | None:
        kind, value = _principal_columns(principal_id)
        record = (
            await self._session.scalars(
                select(SceneParticipantRecord).where(
                    SceneParticipantRecord.world_id == principal_id.world_id.value,
                    SceneParticipantRecord.principal_kind == kind,
                    SceneParticipantRecord.principal_id == value,
                    SceneParticipantRecord.left_at.is_(None),
                )
            )
        ).one_or_none()
        return to_domain(record) if record is not None else None

    async def active_characters_bounded(
        self, scene_id: SceneId, limit: int
    ) -> tuple[tuple[CharacterId, ...], bool]:
        values = (
            await self._session.scalars(
                select(SceneParticipantRecord.principal_id)
                .where(
                    SceneParticipantRecord.world_id == scene_id.world_id.value,
                    SceneParticipantRecord.scene_id == scene_id.value,
                    SceneParticipantRecord.principal_kind == "character",
                    SceneParticipantRecord.left_at.is_(None),
                )
                .order_by(SceneParticipantRecord.principal_id)
                .limit(limit + 1)
            )
        ).all()
        return (
            tuple(CharacterId(scene_id.world_id, value) for value in values[:limit]),
            len(values) > limit,
        )

    async def add_participant(self, participant: SceneParticipant) -> None:
        await _add_unique(
            self._session,
            to_record(participant),
            ConcurrencyConflictError(
                "Principal already participates in an active Scene",
                resource_kind="SceneParticipant",
                resource_identity=participant.principal_id,
            ),
        )

    async def leave_participant(self, participant: SceneParticipant) -> None:
        if participant.left_at is None:
            raise DomainInvariantError("Leaving participant requires left_at")
        row = SceneParticipantRecord
        result = await self._session.execute(
            update(row)
            .where(
                row.world_id == participant.world_id.value,
                row.participant_id == participant.participant_id.value,
                row.left_at.is_(None),
            )
            .values(left_at=participant.left_at)
        )
        if result.rowcount != 1:
            raise _conflict("SceneParticipant", participant.participant_id, None)

    async def leave_all(self, scene_id: SceneId, left_at: WorldTime) -> None:
        await self._session.execute(
            update(SceneParticipantRecord)
            .where(
                SceneParticipantRecord.world_id == scene_id.world_id.value,
                SceneParticipantRecord.scene_id == scene_id.value,
                SceneParticipantRecord.left_at.is_(None),
            )
            .values(left_at=left_at)
        )

    async def leave_active_for_principal(
        self, principal_id: PrincipalId, left_at: WorldTime
    ) -> None:
        participant = await self.active_for_principal(principal_id)
        if participant is None:
            return
        scene = await self.get(participant.scene_id)
        if scene is None:
            raise PersistenceDataError("active_scene_missing")
        await self.replace(scene.advance(scene.revision), scene.revision)
        await self.leave_participant(participant.leave(left_at))


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

    async def put(self, relationship: Relationship, expected_revision: Revision | None) -> None:
        conflict = _conflict(
            "Relationship",
            RelationshipReference(relationship.source_id, relationship.target_id),
            expected_revision,
        )
        if expected_revision is None:
            if relationship.revision != Revision(1):
                raise DomainInvariantError("First relationship delta must produce revision one")
            await _add_unique(self._session, to_record(relationship), conflict)
        else:
            _result_revision(relationship.revision, expected_revision)
            row = RelationshipRecord
            key = relationship_key(relationship.source_id, relationship.target_id)
            await _cas(
                self._session,
                update(row)
                .where(
                    row.world_id == key[0],
                    row.source_kind == key[1],
                    row.source_id == key[2],
                    row.target_kind == key[3],
                    row.target_id == key[4],
                    row.revision == expected_revision.value,
                )
                .values(
                    revision=relationship.revision.value,
                    affinity=relationship.metrics.affinity,
                    trust=relationship.metrics.trust,
                    familiarity=relationship.metrics.familiarity,
                ),
                conflict,
            )


class EventReferenceReader:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def exists(self, event_id: EventId) -> bool:
        return (
            await self._session.get(WorldEventRecord, (event_id.world_id.value, event_id.value))
            is not None
        )


class EventAppender:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def append(self, event: WorldEvent) -> None:
        cursor = WorldLedgerCursorRecord
        # One SQLite atomic write: concurrent adapters cannot both allocate a position.
        statement = (
            insert(cursor)
            .values(world_id=event.world_id.value, last_position=1)
            .on_conflict_do_update(
                index_elements=[cursor.world_id], set_={"last_position": cursor.last_position + 1}
            )
            .returning(cursor.last_position)
        )
        position = (await self._session.execute(statement)).scalar_one()
        record = to_record(event)
        record.ledger_position = position
        await _add_unique(
            self._session,
            record,
            IdempotencyConflictError("Canonical event identity already committed"),
        )


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
        await _add_unique(
            self._session,
            to_record(assertion),
            EntityAlreadyExistsError("KnowledgeAssertion already exists"),
        )


class ObservationAppender:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def add(self, observation: Observation) -> None:
        self._session.add(to_record(observation))
        await self._session.flush()

    async def has_event_access(self, character_id: CharacterId, event_id: EventId) -> bool:
        if character_id.world_id != event_id.world_id:
            return False
        value = await self._session.scalar(
            select(ObservationRecord.observation_id)
            .where(
                ObservationRecord.world_id == character_id.world_id.value,
                ObservationRecord.principal_kind == "character",
                ObservationRecord.principal_id == character_id.value,
                ObservationRecord.target_kind == "event",
                ObservationRecord.target_event_id == event_id.value,
                ObservationRecord.basis == "event_occurrence",
            )
            .limit(1)
        )
        return value is not None


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
        await _add_unique(
            self._session,
            record,
            IdempotencyConflictError("CommandReceipt identity already committed"),
        )

    async def _typed_record(
        self, request_id: RequestId, fingerprint: str
    ) -> CommandReceiptRecord | None:
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
        return records[0]

    async def existing_action(self, request_id: RequestId, fingerprint: str) -> ActionResult | None:
        record = await self._typed_record(request_id, fingerprint)
        if record is None:
            return None
        try:
            value = json.loads(record.result_payload)
            if value["result_version"] != 2:
                raise ValueError("Unknown action result version")
            world = WorldId(record.world_id)
            return ActionResult(
                request_id,
                ActionResolutionStatus(value["status"]),
                ActionRejectionReason(value["reason"]) if value["reason"] is not None else None,
                tuple(EventId(world, UUID(event_id)) for event_id in value["event_ids"]),
                Revision(value["resulting_revision"])
                if value["resulting_revision"] is not None
                else None,
            )
        except (ValueError, KeyError, TypeError):
            raise PersistenceDataError("invalid_action_result") from None

    async def add_action(
        self, receipt: CommandReceipt, fingerprint: str, result: ActionResult
    ) -> None:
        record = to_record(receipt)
        record.command_fingerprint = fingerprint
        record.result_payload = canonical_json(
            {
                "result_version": 2,
                "status": result.status.value,
                "reason": result.reason.value if result.reason is not None else None,
                "event_ids": [str(event_id.value) for event_id in result.event_ids],
                "resulting_revision": (
                    result.resulting_revision.value
                    if result.resulting_revision is not None
                    else None
                ),
            }
        )
        await _add_unique(
            self._session,
            record,
            IdempotencyConflictError("CommandReceipt identity already committed"),
        )

    async def existing_scene(self, request_id: RequestId, fingerprint: str) -> SceneResult | None:
        record = await self._typed_record(request_id, fingerprint)
        if record is None:
            return None
        try:
            value = json.loads(record.result_payload)
            if value["result_version"] != 3:
                raise ValueError("Unknown scene result version")
            world = WorldId(record.world_id)
            return SceneResult(
                request_id,
                SceneId(world, UUID(value["scene_id"])),
                Revision(value["resulting_revision"]),
            )
        except (ValueError, KeyError, TypeError):
            raise PersistenceDataError("invalid_scene_result") from None

    async def add_scene(
        self, receipt: CommandReceipt, fingerprint: str, result: SceneResult
    ) -> None:
        record = to_record(receipt)
        record.command_fingerprint = fingerprint
        record.result_payload = canonical_json(
            {
                "result_version": 3,
                "scene_id": str(result.scene_id.value),
                "resulting_revision": result.resulting_revision.value,
            }
        )
        await _add_unique(
            self._session,
            record,
            IdempotencyConflictError("CommandReceipt identity already committed"),
        )

    async def existing_memory(self, request_id: RequestId, fingerprint: str) -> MemoryResult | None:
        record = await self._typed_record(request_id, fingerprint)
        if record is None:
            return None
        try:
            value = json.loads(record.result_payload)
            if value["result_version"] != 4:
                raise ValueError("Unknown memory result version")
            return MemoryResult(
                request_id,
                MemoryId(WorldId(record.world_id), UUID(value["memory_id"])),
            )
        except (ValueError, KeyError, TypeError):
            raise PersistenceDataError("invalid_memory_result") from None

    async def add_memory(
        self, receipt: CommandReceipt, fingerprint: str, result: MemoryResult
    ) -> None:
        record = to_record(receipt)
        record.command_fingerprint = fingerprint
        record.result_payload = canonical_json(
            {
                "result_version": 4,
                "memory_id": str(result.memory_id.value),
            }
        )
        await _add_unique(
            self._session,
            record,
            IdempotencyConflictError("CommandReceipt identity already committed"),
        )


class SqlAlchemyUnitOfWork:
    def __init__(self, sessions: async_sessionmaker):
        self._sessions = sessions

    async def __aenter__(self):
        self._session = self._sessions()
        try:
            await self._session.begin()
            # Reserve SQLite's physical writer before any reads. CAS still protects each
            # resource independently; this is not a World revision or semantic lock.
            await self._session.connection(execution_options={"livingworld_write_intent": True})
        except BaseException:
            await self._session.close()
            raise
        from livingworld.infrastructure.persistence.director import DirectorKernelRepository
        from livingworld.infrastructure.persistence.world_locations import (
            SqlAlchemyLocalLocationCatalog,
        )
        from livingworld.infrastructure.persistence.world_story import WorldNewsKernelRepository

        self.world_news = WorldNewsKernelRepository(self._session)
        self.director = DirectorKernelRepository(self._session)
        self.local_locations = SqlAlchemyLocalLocationCatalog(self._session)
        self.worlds = WorldRepository(self._session)
        self.locations = LocationRepository(self._session)
        self.players = PlayerRepository(self._session)
        self.characters = CharacterRepository(self._session)
        self.relationships = RelationshipRepository(self._session)
        self.scenes = SceneRepository(self._session)
        self.knowledge = KnowledgeMutationRepository(self._session)
        self.observations = ObservationAppender(self._session)
        self.memories = SqlAlchemyMemoryMutationRepository(self._session)
        self.activations = SqlAlchemyActivationRepository(self._session)
        self.events = EventAppender(self._session)
        self.event_references = EventReferenceReader(self._session)
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
