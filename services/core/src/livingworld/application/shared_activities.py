"""Kernel-owned two-person leisure lifecycle; proposals never imply completed results."""

from dataclasses import replace
from hashlib import sha256
from uuid import uuid5

from livingworld.application.errors import (
    EntityNotFoundError,
    IdempotencyConflictError,
    WorldRuntimeUnavailableError,
)
from livingworld.application.fingerprints import canonical_json
from livingworld.application.results import ActionResult
from livingworld.domain.actions import (
    ActionRejectionReason,
    ActionResolutionStatus,
    AudienceSelector,
    AudienceSelectorKind,
    PerceptionAudience,
)
from livingworld.domain.commands import CommandReceipt
from livingworld.domain.contracts import RequestId
from livingworld.domain.events import WorldEvent
from livingworld.domain.identifiers import (
    CharacterId,
    CorrelationId,
    EventId,
    LocationId,
    ObservationId,
)
from livingworld.domain.knowledge import Observation, ObservationBasis, ObservationChannel
from livingworld.domain.values import WorldTime, utc_timestamp
from livingworld.domain.world import ClockState

SHARED_EVENT_TYPES = ("SharedActivityStarted", "SharedActivityEnded", "SharedActivityInterrupted")
SHARED_REASONS = frozenset(
    (
        "interval_elapsed",
        "presence_changed",
        "activity_changed",
        "consent_or_plan_changed",
        "continuity_unconfirmed",
    )
)


def shared_request(candidate, terminal=False):
    return RequestId(
        uuid5(candidate, "kernel-shared-terminal" if terminal else "kernel-shared-start")
    )


def shared_event(candidate, terminal=False):
    return uuid5(shared_request(candidate, terminal).value, "shared-activity")


async def _record(uow, world, row, now, created, *, terminal=False, reason=None):
    from livingworld.application.action_resolution import AudienceResolver

    if terminal and reason not in SHARED_REASONS:
        raise WorldRuntimeUnavailableError("director_execution_failed")
    request = shared_request(row.candidate_id, terminal)
    fingerprint = sha256(
        canonical_json(
            {
                "fingerprint_version": 1,
                "command_type": "ResolveSharedActivityTerminal"
                if terminal
                else "ResolveSharedActivityStart",
                "world_id": str(world.value),
                "candidate_id": str(row.candidate_id),
            }
        ).encode()
    ).hexdigest()
    existing = await uow.receipts.existing_action(request, fingerprint)
    if existing is not None:
        raise WorldRuntimeUnavailableError("director_execution_failed")
    kind = (
        "SharedActivityStarted"
        if not terminal
        else "SharedActivityEnded"
        if reason == "interval_elapsed"
        else "SharedActivityInterrupted"
    )
    owners = tuple(
        CharacterId(world, identity)
        for identity in (row.first_character_id, row.second_character_id)
    )
    selectors = [AudienceSelector(AudienceSelectorKind.EXPLICIT_PRINCIPALS, principals=owners)]
    presences = [await uow.characters.state(owner) for owner in owners]
    if all(
        presence is not None and presence.location_id.value == row.location_id
        for presence in presences
    ):
        selectors.append(
            AudienceSelector(
                AudienceSelectorKind.LOCATION_PRESENT,
                location_id=LocationId(world, row.location_id),
            )
        )
    observers = await AudienceResolver().resolve(
        uow, PerceptionAudience(tuple(selectors)), actor_id=None, world_id=world
    )
    payload = {
        "candidate_id": str(row.candidate_id),
        "first_character_id": str(row.first_character_id),
        "second_character_id": str(row.second_character_id),
        "location_id": str(row.location_id),
        "first_routine_id": str(row.first_routine_id),
        "second_routine_id": str(row.second_routine_id),
        "first_revision": row.first_revision,
        "second_revision": row.second_revision,
        "activity": row.activity,
        "started_at": row.started_at,
        "planned_end": row.planned_end,
    }
    if terminal:
        payload.update(start_event_id=str(shared_event(row.candidate_id)), reason=reason)
    event_id = EventId(world, shared_event(row.candidate_id, terminal))
    event = WorldEvent(
        event_id,
        world,
        kind,
        now,
        payload,
        1,
        created,
        request,
        CorrelationId(request.value),
        f"{request}:shared:0",
    )
    await uow.events.append(event)
    for observer in observers:
        await uow.observations.add(
            Observation(
                world,
                observer,
                event_id,
                ObservationChannel.WITNESSED,
                now,
                created,
                observation_id=ObservationId(world, uuid5(event_id.value, str(observer.value))),
                basis=ObservationBasis.EVENT_OCCURRENCE,
            )
        )
    if terminal:
        row.state, row.reason = ("ended" if reason == "interval_elapsed" else "interrupted"), reason
    result = ActionResult(request, ActionResolutionStatus.ACCEPTED, None, (event_id,), None)
    command = "ResolveSharedActivityTerminal" if terminal else "ResolveSharedActivityStart"
    await uow.receipts.add_action(
        CommandReceipt(request, world, command, "committed", created, created, event_id),
        fingerprint,
        result,
    )
    return result


class SharedActivityKernel:
    def __init__(self, actions):
        self._actions = actions

    async def execute(self, world, candidate_id):
        if self._actions._mutation_barrier is not None:
            await self._actions._mutation_barrier.assert_mutation_allowed(world)
        request = shared_request(candidate_id)
        fingerprint = sha256(
            canonical_json(
                {
                    "fingerprint_version": 1,
                    "command_type": "ResolveSharedActivityStart",
                    "world_id": str(world.value),
                    "candidate_id": str(candidate_id),
                }
            ).encode()
        ).hexdigest()
        try:
            return await self._execute(world, candidate_id, request, fingerprint)
        except IdempotencyConflictError:
            async with self._actions._uow_factory() as uow:
                existing = await uow.receipts.existing_action(request, fingerprint)
                if existing is not None:
                    return replace(existing, replayed=True)
            raise

    async def _execute(self, world, candidate_id, request, fingerprint):
        async with self._actions._uow_factory() as uow:
            existing = await uow.receipts.existing_action(request, fingerprint)
            if existing is not None:
                return replace(existing, replayed=True)
            state = await uow.worlds.get(world)
            if state is None:
                raise EntityNotFoundError("world_not_found")
            if state.clock.state is ClockState.PAUSED:
                raise WorldRuntimeUnavailableError("director_world_paused")
            now = self._actions._world_time_source.read(state.clock)
            created = utc_timestamp(self._actions._clock.now_utc(), "shared activity wall clock")
            row = await uow.director.shared_candidate(world, candidate_id)
            reason = "candidate_unavailable"
            if row is not None and row.state == "pending":
                reason, routines, presences, plan = await uow.director.shared_current(
                    world, row, uow.characters
                )
                if reason is None and not row.due_at <= now.microseconds < row.start_deadline:
                    reason = "window_elapsed"
                end = now.microseconds + row.duration_us
                if reason is None and (
                    end > plan.window_end
                    or any(
                        not routine.due_at <= now.microseconds < routine.end_at
                        or end > routine.end_at
                        for routine in routines
                    )
                ):
                    reason = "activity_changed"
                if reason is None:
                    reason = await uow.director.shared_pacing(row, now.microseconds)
                if reason is None:
                    row.state, row.started_at, row.planned_end = "active", now.microseconds, end
                    row.first_revision, row.second_revision = (
                        presence.revision.value for presence in presences
                    )
                    result = await _record(uow, world, row, now, created)
                    await uow.commit()
                    return result
                row.state, row.reason = (
                    ("expired" if reason == "window_elapsed" else "cancelled"),
                    reason,
                )
            result = ActionResult(
                request,
                ActionResolutionStatus.REJECTED,
                ActionRejectionReason.PRECONDITION_FAILED,
                (),
                None,
            )
            await uow.receipts.add_action(
                CommandReceipt(
                    request, world, "ResolveSharedActivityStart", "rejected", created, created
                ),
                fingerprint,
                result,
            )
            await uow.commit()
            return result


async def settle_shared_activities(uow, world, now, created, *, character=None, interrupt=False):
    rows = await uow.director.active_shared(world, character)
    deadline = None
    for row in rows:
        reason, routines, _, _ = await uow.director.shared_current(world, row, uow.characters)
        if row.continuity_lost or now.microseconds > row.planned_end + 300_000_000:
            reason = "continuity_unconfirmed"
        elif interrupt:
            reason = "presence_changed"
        if reason is None:
            # Ledger order catches departure/return or terminal routines even at the same WorldTime.
            if await uow.director.shared_continuity_changed(
                world, row, shared_event(row.candidate_id)
            ):
                reason = "activity_changed"
        if reason is None and now.microseconds < row.planned_end:
            if any(now.microseconds >= routine.end_at for routine in routines):
                reason = "activity_changed"
            else:
                end = WorldTime(row.planned_end)
                deadline = min(deadline, end) if deadline is not None else end
                continue
        reason = reason or "interval_elapsed"
        await _record(uow, world, row, now, created, terminal=True, reason=reason)
    return deadline
