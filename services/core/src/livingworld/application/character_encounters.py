"""Typed encounter consumer; actual co-presence and consent precede every fact."""

from dataclasses import dataclass, replace
from hashlib import sha256
from uuid import UUID, uuid5

from livingworld.application.action_resolution import AudienceResolver
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
    WorldId,
)
from livingworld.domain.knowledge import Observation, ObservationBasis, ObservationChannel
from livingworld.domain.values import require_type, utc_timestamp
from livingworld.domain.world import ClockState


@dataclass(frozen=True, slots=True)
class EncounterProposal:
    world_id: WorldId
    candidate_id: UUID

    def __post_init__(self):
        require_type(self.world_id, WorldId, "encounter world")
        require_type(self.candidate_id, UUID, "encounter candidate")


class EncounterKernel:
    def __init__(self, actions):
        # Share the existing Kernel writer, clock and temporal mutation barrier.
        self._actions = actions
        self._audiences = AudienceResolver()

    async def execute(self, world, candidate_id):
        proposal = EncounterProposal(world, candidate_id)
        request_id = RequestId(uuid5(candidate_id, "kernel-encounter"))
        fingerprint = sha256(
            canonical_json(
                {
                    "fingerprint_version": 1,
                    "command_type": "ResolveEncounter",
                    "world_id": str(world.value),
                    "candidate_id": str(proposal.candidate_id),
                }
            ).encode()
        ).hexdigest()
        barrier = self._actions._mutation_barrier
        if barrier is not None:
            await barrier.assert_mutation_allowed(world)
        try:
            return await self._execute(proposal, request_id, fingerprint)
        except IdempotencyConflictError:
            async with self._actions._uow_factory() as uow:
                existing = await uow.receipts.existing_action(request_id, fingerprint)
                if existing is not None:
                    return replace(existing, replayed=True)
            raise

    @staticmethod
    async def _reject(uow, request_id, proposal, fingerprint, reason, created):
        result = ActionResult(request_id, ActionResolutionStatus.REJECTED, reason, (), None)
        receipt = CommandReceipt(
            request_id, proposal.world_id, "ResolveEncounter", "rejected", created, created
        )
        await uow.receipts.add_action(receipt, fingerprint, result)
        await uow.commit()
        return result

    async def _execute(self, proposal, request_id, fingerprint):
        world = proposal.world_id
        async with self._actions._uow_factory() as uow:
            existing = await uow.receipts.existing_action(request_id, fingerprint)
            if existing is not None:
                return replace(existing, replayed=True)
            state = await uow.worlds.get(world)
            if state is None:
                raise EntityNotFoundError("World does not exist")
            if state.clock.state is ClockState.PAUSED:
                raise WorldRuntimeUnavailableError("director_world_paused")
            now = self._actions._world_time_source.read(state.clock)
            created = utc_timestamp(self._actions._clock.now_utc(), "encounter wall clock")
            candidate, routines = await uow.director.encounter_candidate(
                world, proposal.candidate_id, now
            )
            reason = ActionRejectionReason.PRECONDITION_FAILED
            if candidate is None or routines is None:
                return await self._reject(uow, request_id, proposal, fingerprint, reason, created)
            participants = (
                CharacterId(world, candidate.first_character_id),
                CharacterId(world, candidate.second_character_id),
            )
            location = LocationId(world, candidate.location_id)
            presences = [await uow.characters.state(owner) for owner in participants]
            if await uow.locations.get(location) is None or any(
                presence is None
                or presence.location_id != location
                or presence.revision.value != routine.expected_revision + 1
                for presence, routine in zip(presences, routines, strict=True)
            ):
                candidate.state, candidate.reason = "invalid", "presence_changed"
                return await self._reject(uow, request_id, proposal, fingerprint, reason, created)
            observers = await self._audiences.resolve(
                uow,
                PerceptionAudience(
                    (
                        AudienceSelector(
                            AudienceSelectorKind.EXPLICIT_PRINCIPALS, principals=participants
                        ),
                        AudienceSelector(
                            AudienceSelectorKind.LOCATION_PRESENT, location_id=location
                        ),
                    )
                ),
                actor_id=None,
                world_id=world,
            )
            event_id = EventId(world, uuid5(request_id.value, "characters-met"))
            event = WorldEvent(
                event_id,
                world,
                "CharactersMet",
                now,
                {
                    "first_character_id": str(participants[0].value),
                    "second_character_id": str(participants[1].value),
                    "location_id": str(location.value),
                    "first_routine_id": str(candidate.first_routine_id),
                    "second_routine_id": str(candidate.second_routine_id),
                    "first_revision": presences[0].revision.value,
                    "second_revision": presences[1].revision.value,
                    "candidate_id": str(candidate.candidate_id),
                    "purpose": "brief_greeting",
                    "encounter_due_at": candidate.due_at,
                    "encounter_end_at": candidate.end_at,
                },
                1,
                created,
                request_id,
                CorrelationId(request_id.value),
                f"{request_id}:encounter:0",
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
                        observation_id=ObservationId(
                            world, uuid5(event_id.value, str(observer.value))
                        ),
                        basis=ObservationBasis.EVENT_OCCURRENCE,
                    )
                )
            candidate.state, candidate.executed_at, candidate.reason = (
                "finished",
                now.microseconds,
                None,
            )
            result = ActionResult(
                request_id, ActionResolutionStatus.ACCEPTED, None, (event_id,), None
            )
            await uow.receipts.add_action(
                CommandReceipt(
                    request_id, world, "ResolveEncounter", "committed", created, created, event_id
                ),
                fingerprint,
                result,
            )
            await uow.commit()
            return result
