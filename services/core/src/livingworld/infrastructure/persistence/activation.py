"""SQLite sparse-activation persistence, deterministic coalescing, and fidelity reads."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from livingworld.application.errors import IdempotencyConflictError
from livingworld.domain.contracts import RequestId
from livingworld.domain.identifiers import (
    ActivationId,
    CharacterId,
    EventId,
    SceneId,
    TriggerId,
    WorldId,
)
from livingworld.domain.simulation import (
    ActivationAttention,
    ActivationCandidate,
    ActivationCause,
    ActivationCauseKind,
    ActivationCausePage,
    ActivationKind,
    ActivationRequest,
    ActivationRequestResult,
    ActivationStatus,
    ActivationTarget,
    ActivationTargetKind,
    SceneActivityKind,
    SimulationActivation,
    SimulationActivationCause,
    SimulationFidelity,
    SimulationPayload,
    TriggerPriority,
)
from livingworld.domain.values import WorldTime
from livingworld.infrastructure.persistence.errors import PersistenceDataError
from livingworld.infrastructure.persistence.models import (
    CharacterStateRecord,
    SceneParticipantRecord,
    SceneRecord,
    SimulationActivationCauseRecord,
    SimulationActivationRecord,
    SimulationQueueCursorRecord,
)


async def allocate_simulation_position(session: AsyncSession, world_id: WorldId) -> int:
    allocation = (
        insert(SimulationQueueCursorRecord)
        .values(world_id=world_id.value, last_position=1)
        .on_conflict_do_update(
            index_elements=[SimulationQueueCursorRecord.world_id],
            set_={"last_position": SimulationQueueCursorRecord.last_position + 1},
        )
        .returning(SimulationQueueCursorRecord.last_position)
    )
    return (await session.execute(allocation)).scalar_one()


def activation_from_record(record: SimulationActivationRecord) -> SimulationActivation:
    world_id = WorldId(record.world_id)
    target = (
        ActivationTarget.world(world_id)
        if record.target_kind == ActivationTargetKind.WORLD.value
        else ActivationTarget.character(CharacterId(world_id, record.target_character_id))
    )
    return SimulationActivation(
        activation_id=ActivationId(world_id, record.activation_id),
        world_id=world_id,
        target=target,
        activation_kind=ActivationKind(record.activation_kind),
        activation_version=record.activation_version,
        source_trigger_id=(
            TriggerId(world_id, record.source_trigger_id)
            if record.source_trigger_id is not None
            else None
        ),
        kind=record.kind,
        payload_version=record.payload_version,
        due_at=record.due_at,
        priority=TriggerPriority(record.priority),
        enqueue_position=record.enqueue_position,
        coalescing_key=record.coalescing_key,
        attention=ActivationAttention(record.attention),
        payload=SimulationPayload(record.payload),
        status=ActivationStatus(record.status),
        materialized_at_utc=record.materialized_at_utc,
    )


def cause_from_record(record: SimulationActivationCauseRecord) -> SimulationActivationCause:
    world_id = WorldId(record.world_id)
    cause = ActivationCause(
        world_id=world_id,
        kind=ActivationCauseKind(record.cause_kind),
        source_trigger_id=(
            TriggerId(world_id, record.source_trigger_id)
            if record.source_trigger_id is not None
            else None
        ),
        source_event_id=(
            EventId(world_id, record.source_event_id)
            if record.source_event_id is not None
            else None
        ),
        source_scene_id=(
            SceneId(world_id, record.source_scene_id)
            if record.source_scene_id is not None
            else None
        ),
        scene_activity=(
            SceneActivityKind(record.scene_activity) if record.scene_activity is not None else None
        ),
        source_request_id=(
            RequestId(record.source_request_id) if record.source_request_id is not None else None
        ),
    )
    return SimulationActivationCause(
        ActivationId(world_id, record.activation_id),
        cause,
        record.position,
        record.request_fingerprint,
        record.attached_at_utc,
    )


class SqlAlchemyActivationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def request(
        self,
        request: ActivationRequest,
        fingerprint: str,
        materialized_at_utc: datetime,
    ) -> ActivationRequestResult:
        target_id, target_character_id = _target_storage(request.target)
        existing_cause = (
            await self._session.scalars(
                select(SimulationActivationCauseRecord)
                .join(
                    SimulationActivationRecord,
                    (
                        SimulationActivationRecord.world_id
                        == SimulationActivationCauseRecord.world_id
                    )
                    & (
                        SimulationActivationRecord.activation_id
                        == SimulationActivationCauseRecord.activation_id
                    ),
                )
                .where(
                    SimulationActivationCauseRecord.world_id == request.world_id.value,
                    SimulationActivationCauseRecord.cause_identity == request.cause.identity,
                    SimulationActivationRecord.target_kind == request.target.kind.value,
                    SimulationActivationRecord.target_id == target_id,
                    SimulationActivationRecord.activation_kind == request.activation_kind.value,
                    SimulationActivationRecord.activation_version == request.activation_version,
                    SimulationActivationRecord.coalescing_key == request.coalescing_key,
                )
            )
        ).one_or_none()
        if existing_cause is not None:
            if existing_cause.request_fingerprint != fingerprint:
                raise IdempotencyConflictError(
                    "activation cause identity belongs to different request semantics"
                )
            record = await self._activation_record(request.world_id, existing_cause.activation_id)
            return ActivationRequestResult(activation_from_record(record), True, True, False)

        record = await self._coalescing_target(request)
        coalesced = record is not None
        schedule_changed = False
        if record is None:
            position = await allocate_simulation_position(self._session, request.world_id)
            activation_id = uuid4()
            record = SimulationActivationRecord(
                world_id=request.world_id.value,
                activation_id=activation_id,
                source_trigger_id=(
                    request.cause.source_trigger_id.value
                    if request.cause.kind is ActivationCauseKind.SCHEDULED_TRIGGER
                    else None
                ),
                target_kind=request.target.kind.value,
                target_id=target_id,
                target_character_id=target_character_id,
                activation_kind=request.activation_kind.value,
                activation_version=request.activation_version,
                kind=request.source_contract_kind,
                payload_version=request.source_contract_version,
                due_at=request.due_at,
                priority=int(request.priority),
                enqueue_position=position,
                coalescing_key=request.coalescing_key,
                attention=request.attention.value,
                payload=request.payload.data,
                status=ActivationStatus.PENDING.value,
                materialized_at_utc=materialized_at_utc,
            )
            self._session.add(record)
            # The cause has a composite FK to its activation. Flush the parent
            # first so SQLite never observes the dependent row ahead of it.
            await self._session.flush([record])
            position_in_activation = 1
            schedule_changed = True
        else:
            old_due = record.due_at
            old_priority = record.priority
            record.due_at = min(record.due_at, request.due_at)
            record.priority = min(record.priority, int(request.priority))
            if request.attention is ActivationAttention.ACTIVE:
                record.attention = ActivationAttention.ACTIVE.value
            schedule_changed = record.due_at != old_due or record.priority != old_priority
            position_in_activation = (
                await self._session.scalar(
                    select(
                        func.coalesce(func.max(SimulationActivationCauseRecord.position), 0)
                    ).where(
                        SimulationActivationCauseRecord.world_id == request.world_id.value,
                        SimulationActivationCauseRecord.activation_id == record.activation_id,
                    )
                )
            ) + 1

        self._session.add(
            SimulationActivationCauseRecord(
                world_id=request.world_id.value,
                cause_identity=request.cause.identity,
                activation_id=record.activation_id,
                position=position_in_activation,
                cause_kind=request.cause.kind.value,
                source_trigger_id=_uuid(request.cause.source_trigger_id),
                source_event_id=_uuid(request.cause.source_event_id),
                source_scene_id=_uuid(request.cause.source_scene_id),
                scene_activity=(
                    request.cause.scene_activity.value
                    if request.cause.scene_activity is not None
                    else None
                ),
                source_request_id=(
                    request.cause.source_request_id.value
                    if request.cause.source_request_id is not None
                    else None
                ),
                request_fingerprint=fingerprint,
                attached_at_utc=materialized_at_utc,
            )
        )
        await self._session.flush()
        return ActivationRequestResult(
            activation_from_record(record), coalesced, False, schedule_changed
        )

    async def list_due_candidates(
        self, world_id: WorldId, through: WorldTime, max_items: int
    ) -> tuple[ActivationCandidate, ...]:
        records = (
            await self._session.scalars(
                select(SimulationActivationRecord)
                .where(
                    SimulationActivationRecord.world_id == world_id.value,
                    SimulationActivationRecord.status == ActivationStatus.PENDING.value,
                    SimulationActivationRecord.due_at <= through,
                )
                .order_by(
                    SimulationActivationRecord.due_at,
                    SimulationActivationRecord.priority,
                    SimulationActivationRecord.enqueue_position,
                )
                .limit(max_items)
            )
        ).all()
        candidates: list[ActivationCandidate] = []
        for record in records:
            activation = activation_from_record(record)
            fidelity = await self._fidelity(record)
            candidates.append(ActivationCandidate(activation, fidelity))
        return tuple(candidates)

    async def causes(
        self, activation_id: ActivationId, limit: int, offset: int = 0
    ) -> ActivationCausePage:
        records = (
            await self._session.scalars(
                select(SimulationActivationCauseRecord)
                .where(
                    SimulationActivationCauseRecord.world_id == activation_id.world_id.value,
                    SimulationActivationCauseRecord.activation_id == activation_id.value,
                )
                .order_by(
                    SimulationActivationCauseRecord.position,
                    SimulationActivationCauseRecord.cause_identity,
                )
                .offset(offset)
                .limit(limit + 1)
            )
        ).all()
        return ActivationCausePage(
            tuple(cause_from_record(record) for record in records[:limit]),
            len(records) > limit,
        )

    async def _coalescing_target(
        self, request: ActivationRequest
    ) -> SimulationActivationRecord | None:
        if request.coalescing_key is None:
            return None
        target_id, _ = _target_storage(request.target)
        return (
            await self._session.scalars(
                select(SimulationActivationRecord).where(
                    SimulationActivationRecord.world_id == request.world_id.value,
                    SimulationActivationRecord.target_kind == request.target.kind.value,
                    SimulationActivationRecord.target_id == target_id,
                    SimulationActivationRecord.activation_kind == request.activation_kind.value,
                    SimulationActivationRecord.activation_version == request.activation_version,
                    SimulationActivationRecord.coalescing_key == request.coalescing_key,
                    SimulationActivationRecord.status == ActivationStatus.PENDING.value,
                )
            )
        ).one_or_none()

    async def _activation_record(
        self, world_id: WorldId, activation_id: UUID
    ) -> SimulationActivationRecord:
        record = await self._session.get(
            SimulationActivationRecord, (world_id.value, activation_id)
        )
        if record is None:
            raise PersistenceDataError("activation_cause_target_missing")
        return record

    async def _fidelity(self, record: SimulationActivationRecord) -> SimulationFidelity | None:
        if record.target_kind == ActivationTargetKind.WORLD.value:
            return None
        state = await self._session.get(
            CharacterStateRecord, (record.world_id, record.target_character_id)
        )
        if state is None:
            return SimulationFidelity.DORMANT
        membership = (
            await self._session.execute(
                select(SceneParticipantRecord.scene_id)
                .join(
                    SceneRecord,
                    (SceneRecord.world_id == SceneParticipantRecord.world_id)
                    & (SceneRecord.scene_id == SceneParticipantRecord.scene_id),
                )
                .where(
                    SceneParticipantRecord.world_id == record.world_id,
                    SceneParticipantRecord.principal_kind == "character",
                    SceneParticipantRecord.principal_id == record.target_character_id,
                    SceneParticipantRecord.left_at.is_(None),
                    SceneRecord.status == "open",
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if membership is not None:
            player_present = await self._session.scalar(
                select(func.count())
                .select_from(SceneParticipantRecord)
                .where(
                    SceneParticipantRecord.world_id == record.world_id,
                    SceneParticipantRecord.scene_id == membership,
                    SceneParticipantRecord.principal_kind == "player",
                    SceneParticipantRecord.left_at.is_(None),
                )
            )
            return (
                SimulationFidelity.PLAYER_FACING
                if player_present
                else SimulationFidelity.SCENE_ACTIVE
            )
        return (
            SimulationFidelity.ACTIVE
            if record.attention == ActivationAttention.ACTIVE.value
            else SimulationFidelity.BACKGROUND
        )


def _target_storage(target: ActivationTarget) -> tuple[UUID, UUID | None]:
    if target.kind is ActivationTargetKind.WORLD:
        return target.world_id.value, None
    return target.character_id.value, target.character_id.value


def _uuid(value) -> UUID | None:
    return value.value if value is not None else None
