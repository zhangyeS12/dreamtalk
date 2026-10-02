"""Kernel-owned routine termination; no LLM, task outcomes or new polling loop."""

from uuid import uuid4, uuid5

from livingworld.application.errors import WorldRuntimeUnavailableError
from livingworld.domain.actions import AudienceSelector, AudienceSelectorKind, PerceptionAudience
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
from livingworld.domain.values import WorldTime


async def settle_routines(uow, world_id, now, created_at, *, character=None, interrupt=False):
    # Imported here to reuse the existing authority resolver without a module cycle.
    from livingworld.application.action_resolution import AudienceResolver

    next_time = None
    for row in await uow.director.active(world_id, character):
        owner = CharacterId(world_id, row.character_id)
        presence = await uow.characters.state(owner)
        if presence is None:
            raise WorldRuntimeUnavailableError("director_execution_failed")
        changed = (
            presence.revision.value != row.expected_revision + 1
            or presence.location_id.value != row.location_id
        )
        expired = now.microseconds >= row.end_at
        if not expired and not changed and not interrupt:
            end = WorldTime(row.end_at)
            next_time = min(next_time, end) if next_time is not None else end
            continue
        request = RequestId(uuid5(row.candidate_id, "kernel-routine"))
        start = EventId(world_id, uuid5(request.value, f"livingworld:action:{world_id.value}:0"))
        if not await uow.event_references.exists(start):
            raise WorldRuntimeUnavailableError("director_execution_failed")
        interrupted = changed or (interrupt and not expired)
        reason = "presence_changed" if interrupted else "interval_elapsed"
        end_id = EventId(world_id, uuid5(row.candidate_id, "kernel-routine-ended-v1"))
        # Candidate and its one terminal event are written in this same physical writer.
        # A crash rolls both back; a committed terminal candidate is never selected again.
        if await uow.event_references.exists(end_id):
            raise WorldRuntimeUnavailableError("director_execution_failed")
        event = WorldEvent(
            end_id,
            world_id,
            "CharacterRoutineInterrupted" if interrupted else "CharacterRoutineEnded",
            now,
            {
                "character_id": str(owner.value),
                "candidate_id": str(row.candidate_id),
                "start_event_id": str(start.value),
                "activity": row.activity,
                "location_id": str(row.location_id),
                "before_location_id": None,
                "current_location_id": str(presence.location_id.value),
                "revision": presence.revision.value,
                "planned_until": row.end_at,
                "reason": reason,
            },
            1,
            created_at,
            start,
            CorrelationId(request.value),
            f"routine:{row.candidate_id}:ended:1",
        )
        selectors = [AudienceSelector(AudienceSelectorKind.ACTOR_ONLY)]
        # If an external placement already changed presence, only the actor can attest
        # to the earlier interruption. Never grant old-location bystanders new access.
        if not changed:
            selectors.append(
                AudienceSelector(
                    AudienceSelectorKind.LOCATION_PRESENT,
                    location_id=LocationId(world_id, row.location_id),
                )
            )
        observers = await AudienceResolver().resolve(
            uow,
            PerceptionAudience(tuple(selectors)),
            actor_id=owner,
            world_id=world_id,
        )
        await uow.events.append(event)
        for observer in observers:
            await uow.observations.add(
                Observation(
                    world_id,
                    observer,
                    end_id,
                    ObservationChannel.WITNESSED,
                    now,
                    created_at,
                    observation_id=ObservationId(world_id, uuid4()),
                    basis=ObservationBasis.EVENT_OCCURRENCE,
                )
            )
        uow.director.finish(row, interrupted)
    return next_time
