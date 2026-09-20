"""SQLite WAL implementation of the durable simulation queue."""

from __future__ import annotations

from datetime import datetime
from sqlite3 import SQLITE_CONSTRAINT_PRIMARYKEY, SQLITE_CONSTRAINT_UNIQUE
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from livingworld.application.errors import (
    EntityAlreadyExistsError,
    EntityNotFoundError,
    IdempotencyConflictError,
    TriggerAlreadyFiredError,
)
from livingworld.application.scheduler import (
    DrainResult,
    ScheduleResult,
    ScheduleTrigger,
    TriggerKindRegistry,
)
from livingworld.domain.contracts import RequestId
from livingworld.domain.identifiers import ActivationId, CorrelationId, TriggerId, WorldId
from livingworld.domain.simulation import (
    ActivationStatus,
    ScheduledSimulationTrigger,
    SimulationActivation,
    SimulationPayload,
    TriggerPriority,
    TriggerStatus,
)
from livingworld.domain.values import Revision, WorldTime
from livingworld.domain.world import World
from livingworld.infrastructure.persistence.errors import PersistenceConflictError
from livingworld.infrastructure.persistence.mapping import to_domain
from livingworld.infrastructure.persistence.models import (
    ScheduledSimulationTriggerRecord,
    SimulationActivationRecord,
    SimulationQueueCursorRecord,
    SimulationScheduleReceiptRecord,
    WorldRecord,
)


def _trigger(record: ScheduledSimulationTriggerRecord) -> ScheduledSimulationTrigger:
    world_id = WorldId(record.world_id)
    return ScheduledSimulationTrigger(
        trigger_id=TriggerId(world_id, record.trigger_id),
        world_id=world_id,
        due_at=record.due_at,
        priority=TriggerPriority(record.priority),
        enqueue_position=record.enqueue_position,
        kind=record.kind,
        payload_version=record.payload_version,
        payload=SimulationPayload(record.payload),
        status=TriggerStatus(record.status),
        created_at_utc=record.created_at_utc,
        fired_at_utc=record.fired_at_utc,
        cancelled_at_utc=record.cancelled_at_utc,
        revision=Revision(record.revision),
        causation_request_id=(
            RequestId(record.causation_request_id) if record.causation_request_id else None
        ),
        correlation_id=CorrelationId(record.correlation_id) if record.correlation_id else None,
    )


def _activation(record: SimulationActivationRecord) -> SimulationActivation:
    world_id = WorldId(record.world_id)
    return SimulationActivation(
        activation_id=ActivationId(world_id, record.activation_id),
        world_id=world_id,
        source_trigger_id=TriggerId(world_id, record.source_trigger_id),
        kind=record.kind,
        payload_version=record.payload_version,
        due_at=record.due_at,
        payload=SimulationPayload(record.payload),
        status=ActivationStatus(record.status),
        materialized_at_utc=record.materialized_at_utc,
    )


async def _begin_write(session: AsyncSession) -> None:
    await session.begin()
    await session.connection(execution_options={"livingworld_write_intent": True})


class SqlAlchemySimulationSchedulerStore:
    def __init__(self, sessions: async_sessionmaker, registry: TriggerKindRegistry) -> None:
        self._sessions = sessions
        self._registry = registry

    async def schedule(
        self, request: ScheduleTrigger, fingerprint: str, created_at_utc: datetime
    ) -> ScheduleResult:
        async with self._sessions() as session:
            await _begin_write(session)
            try:
                receipt = (
                    await session.scalars(
                        select(SimulationScheduleReceiptRecord).where(
                            SimulationScheduleReceiptRecord.request_id == request.request_id.value
                        )
                    )
                ).one_or_none()
                if receipt is not None:
                    if receipt.fingerprint != fingerprint:
                        raise IdempotencyConflictError(
                            "request_id already belongs to different scheduling semantics"
                        )
                    record = await session.get(
                        ScheduledSimulationTriggerRecord,
                        (receipt.world_id, receipt.trigger_id),
                    )
                    if record is None:
                        raise PersistenceConflictError("schedule_receipt_target_missing")
                    result = _trigger(record)
                    await session.rollback()
                    return ScheduleResult(result, replayed=True)
                self._registry.validate(request.kind, request.payload_version, request.payload)
                if await session.get(WorldRecord, request.world_id.value) is None:
                    raise EntityNotFoundError("World does not exist")
                allocation = (
                    insert(SimulationQueueCursorRecord)
                    .values(world_id=request.world_id.value, last_position=1)
                    .on_conflict_do_update(
                        index_elements=[SimulationQueueCursorRecord.world_id],
                        set_={"last_position": SimulationQueueCursorRecord.last_position + 1},
                    )
                    .returning(SimulationQueueCursorRecord.last_position)
                )
                position = (await session.execute(allocation)).scalar_one()
                trigger = ScheduledSimulationTrigger(
                    trigger_id=request.trigger_id,
                    world_id=request.world_id,
                    due_at=request.due_at,
                    priority=request.priority,
                    enqueue_position=position,
                    kind=request.kind,
                    payload_version=request.payload_version,
                    payload=request.payload,
                    status=TriggerStatus.PENDING,
                    created_at_utc=created_at_utc,
                    causation_request_id=request.request_id,
                    correlation_id=request.correlation_id,
                )
                session.add(
                    ScheduledSimulationTriggerRecord(
                        world_id=request.world_id.value,
                        trigger_id=request.trigger_id.value,
                        due_at=request.due_at,
                        priority=int(request.priority),
                        enqueue_position=position,
                        kind=request.kind,
                        payload_version=request.payload_version,
                        payload=request.payload.data,
                        status=TriggerStatus.PENDING.value,
                        created_at_utc=created_at_utc,
                        fired_at_utc=None,
                        cancelled_at_utc=None,
                        revision=0,
                        causation_request_id=request.request_id.value,
                        correlation_id=request.correlation_id.value
                        if request.correlation_id
                        else None,
                    )
                )
                session.add(
                    SimulationScheduleReceiptRecord(
                        world_id=request.world_id.value,
                        request_id=request.request_id.value,
                        fingerprint=fingerprint,
                        trigger_id=request.trigger_id.value,
                        created_at_utc=created_at_utc,
                    )
                )
                await session.commit()
                return ScheduleResult(trigger)
            except IntegrityError as error:
                await session.rollback()
                if getattr(error.orig, "sqlite_errorcode", None) in (
                    SQLITE_CONSTRAINT_PRIMARYKEY,
                    SQLITE_CONSTRAINT_UNIQUE,
                ):
                    raise EntityAlreadyExistsError("Trigger identity already exists") from None
                raise PersistenceConflictError("simulation_schedule_persistence_conflict") from None
            except BaseException:
                await session.rollback()
                raise

    async def cancel(
        self, trigger_id: TriggerId, cancelled_at_utc: datetime
    ) -> ScheduledSimulationTrigger:
        async with self._sessions() as session:
            await _begin_write(session)
            try:
                record = await session.get(
                    ScheduledSimulationTriggerRecord,
                    (trigger_id.world_id.value, trigger_id.value),
                )
                if record is None:
                    raise EntityNotFoundError("Scheduled trigger does not exist")
                if record.status == TriggerStatus.FIRED.value:
                    raise TriggerAlreadyFiredError("trigger already fired")
                if record.status == TriggerStatus.CANCELLED.value:
                    result = _trigger(record)
                    await session.rollback()
                    return result
                record.status = TriggerStatus.CANCELLED.value
                record.cancelled_at_utc = cancelled_at_utc
                record.revision += 1
                await session.commit()
                return _trigger(record)
            except BaseException:
                await session.rollback()
                raise

    async def get(self, trigger_id: TriggerId) -> ScheduledSimulationTrigger | None:
        async with self._sessions() as session:
            record = await session.get(
                ScheduledSimulationTriggerRecord,
                (trigger_id.world_id.value, trigger_id.value),
            )
            return _trigger(record) if record is not None else None

    async def peek_next(self, world_id: WorldId) -> ScheduledSimulationTrigger | None:
        async with self._sessions() as session:
            record = (await session.scalars(self._ordered_pending(world_id).limit(1))).one_or_none()
            return _trigger(record) if record is not None else None

    async def list_due(
        self, world_id: WorldId, through: WorldTime, max_items: int
    ) -> tuple[ScheduledSimulationTrigger, ...]:
        async with self._sessions() as session:
            records = (
                await session.scalars(
                    self._ordered_pending(world_id)
                    .where(ScheduledSimulationTriggerRecord.due_at <= through)
                    .limit(max_items)
                )
            ).all()
            return tuple(_trigger(record) for record in records)

    async def drain_due(
        self,
        world_id: WorldId,
        through: WorldTime,
        max_items: int,
        materialized_at_utc: datetime,
    ) -> DrainResult:
        async with self._sessions() as session:
            await _begin_write(session)
            try:
                records = (
                    await session.scalars(
                        self._ordered_pending(world_id)
                        .where(ScheduledSimulationTriggerRecord.due_at <= through)
                        .limit(max_items + 1)
                    )
                ).all()
                more_due = len(records) > max_items
                activations: list[SimulationActivation] = []
                for record in records[:max_items]:
                    trigger = _trigger(record)
                    self._registry.validate(trigger.kind, trigger.payload_version, trigger.payload)
                    activation = self._new_activation(trigger, materialized_at_utc)
                    session.add(
                        SimulationActivationRecord(
                            world_id=world_id.value,
                            activation_id=activation.activation_id.value,
                            source_trigger_id=trigger.trigger_id.value,
                            kind=trigger.kind,
                            payload_version=trigger.payload_version,
                            due_at=trigger.due_at,
                            payload=trigger.payload.data,
                            status=activation.status.value,
                            materialized_at_utc=materialized_at_utc,
                        )
                    )
                    record.status = TriggerStatus.FIRED.value
                    record.fired_at_utc = materialized_at_utc
                    record.revision += 1
                    activations.append(activation)
                await session.flush()
                await self._before_materialization_commit(session)
                await session.commit()
                return DrainResult(tuple(activations), more_due)
            except IntegrityError:
                await session.rollback()
                raise PersistenceConflictError("simulation_materialization_conflict") from None
            except BaseException:
                await session.rollback()
                raise

    async def world(self, world_id: WorldId) -> World | None:
        async with self._sessions() as session:
            record = (
                await session.scalars(
                    select(WorldRecord)
                    .options(selectinload(WorldRecord.clock))
                    .where(WorldRecord.world_id == world_id.value)
                )
            ).one_or_none()
            return to_domain(record) if record is not None else None

    async def list_activations(self, world_id: WorldId) -> tuple[SimulationActivation, ...]:
        async with self._sessions() as session:
            records = (
                await session.scalars(
                    select(SimulationActivationRecord)
                    .where(SimulationActivationRecord.world_id == world_id.value)
                    .order_by(
                        SimulationActivationRecord.due_at, SimulationActivationRecord.activation_id
                    )
                )
            ).all()
            return tuple(_activation(record) for record in records)

    @staticmethod
    def _ordered_pending(world_id: WorldId):
        row = ScheduledSimulationTriggerRecord
        return (
            select(row)
            .where(row.world_id == world_id.value, row.status == TriggerStatus.PENDING.value)
            .order_by(row.due_at, row.priority, row.enqueue_position)
        )

    @staticmethod
    def _new_activation(
        trigger: ScheduledSimulationTrigger, materialized_at_utc: datetime
    ) -> SimulationActivation:
        return SimulationActivation(
            activation_id=ActivationId(trigger.world_id, uuid4()),
            world_id=trigger.world_id,
            source_trigger_id=trigger.trigger_id,
            kind=trigger.kind,
            payload_version=trigger.payload_version,
            due_at=trigger.due_at,
            payload=trigger.payload,
            status=ActivationStatus.PENDING,
            materialized_at_utc=materialized_at_utc,
        )

    async def _before_materialization_commit(self, session: AsyncSession) -> None:
        """Test seam after writes are flushed but before the atomic commit."""
