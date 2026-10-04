"""Shared activity preconditions under the existing Kernel writer; return fixed labels only."""

from sqlalchemy import case, func, or_, select

from livingworld.application.encounter_policy import (
    MAX_ENCOUNTERS_PER_BATCH,
    NEW_CONTACT_WINDOW_US,
    PAIR_COOLDOWN_US,
)
from livingworld.application.errors import WorldRuntimeUnavailableError
from livingworld.domain.identifiers import CharacterId
from livingworld.infrastructure.persistence.director_models import (
    DirectorCandidateRecord as Routine,
)
from livingworld.infrastructure.persistence.director_models import DirectorPlanRecord as Plan
from livingworld.infrastructure.persistence.director_models import (
    DirectorSettingsRecord as Settings,
)
from livingworld.infrastructure.persistence.encounter_models import (
    EncounterCandidateRecord as Meeting,
)
from livingworld.infrastructure.persistence.encounter_models import (
    EncounterSettingsRecord as EncounterSettings,
)
from livingworld.infrastructure.persistence.models import LocalPlayerBindingRecord
from livingworld.infrastructure.persistence.models import WorldEventRecord as Event
from livingworld.infrastructure.persistence.shared_activity_models import (
    SharedActivityRecord as Shared,
)
from livingworld.infrastructure.persistence.shared_activity_models import (
    SharedActivitySettingsRecord as SharedSettings,
)


async def _current(session, characters, world, row):
    binding = await session.get(LocalPlayerBindingRecord, world.value)
    config = await session.get(Settings, world.value)
    consent = await session.get(SharedSettings, world.value)
    encounters = await session.get(EncounterSettings, world.value)
    plan = await session.get(Plan, (world.value, row.plan_id))
    if not (
        binding
        and config
        and config.enabled
        and config.state == "ready"
        and consent
        and consent.enabled
        and encounters
        and encounters.enabled
        and encounters.revision == row.encounter_revision
        and encounters.player_id == binding.player_id
        and consent.player_id == binding.player_id == config.player_id
        and consent.revision == row.consent_revision
        and config.plan_id == row.plan_id
        and plan
        and plan.state == "ready"
        and plan.generation == config.revision
    ):
        return "consent_or_plan_changed", (), (), plan
    routines = tuple(
        [
            await session.get(Routine, (world.value, identity))
            for identity in (row.first_routine_id, row.second_routine_id)
        ]
    )
    owners = tuple(
        CharacterId(world, identity)
        for identity in (row.first_character_id, row.second_character_id)
    )
    presences = tuple([await characters.state(owner) for owner in owners])
    activity = "rest" if row.activity == "shared_rest" else "leisure"
    if any(
        routine is None
        or routine.state != "active"
        or routine.plan_id != row.plan_id
        or routine.character_id != owner.value
        or routine.location_id != row.location_id
        or routine.activity != activity
        for routine, owner in zip(routines, owners, strict=True)
    ):
        return "activity_changed", routines, presences, plan
    if any(
        presence is None
        or presence.location_id.value != row.location_id
        or presence.revision.value != routine.expected_revision + 1
        for presence, routine in zip(presences, routines, strict=True)
    ):
        return "presence_changed", routines, presences, plan
    if row.started_at is not None and any(
        presence.revision.value != revision
        for presence, revision in zip(
            presences, (row.first_revision, row.second_revision), strict=True
        )
    ):
        return "presence_changed", routines, presences, plan
    return None, routines, presences, plan


async def social_count(session, row):
    ordinary = await session.scalar(
        select(func.count())
        .select_from(Meeting)
        .where(
            Meeting.world_id == row.world_id,
            Meeting.plan_id == row.plan_id,
            Meeting.state == "finished",
        )
    )
    joint = await session.scalar(
        select(func.count())
        .select_from(Shared)
        .where(
            Shared.world_id == row.world_id,
            Shared.plan_id == row.plan_id,
            Shared.started_at.is_not(None),
        )
    )
    return ordinary + joint


async def _pacing(session, row, now):
    if await social_count(session, row) >= MAX_ENCOUNTERS_PER_BATCH:
        return "batch_social_limit"
    met = await session.scalar(
        select(Meeting.candidate_id)
        .where(
            Meeting.world_id == row.world_id,
            Meeting.state == "finished",
            Meeting.first_character_id == row.first_character_id,
            Meeting.second_character_id == row.second_character_id,
        )
        .limit(1)
    )
    if met is None:
        return "previous_meeting_required"
    recent = await session.scalar(
        select(Shared.candidate_id)
        .where(
            Shared.world_id == row.world_id,
            Shared.started_at > now - NEW_CONTACT_WINDOW_US,
            Shared.started_at <= now,
            or_(
                Shared.first_character_id.in_((row.first_character_id, row.second_character_id)),
                Shared.second_character_id.in_((row.first_character_id, row.second_character_id)),
            ),
        )
        .limit(1)
    )
    if recent is not None:
        return "shared_daily_limit"
    for model, timestamp, extra in (
        (Meeting, Meeting.executed_at, (Meeting.state == "finished",)),
        (Shared, Shared.started_at, ()),
    ):
        recent_pair = await session.scalar(
            select(model.candidate_id)
            .where(
                model.world_id == row.world_id,
                model.first_character_id == row.first_character_id,
                model.second_character_id == row.second_character_id,
                timestamp > now - PAIR_COOLDOWN_US,
                timestamp <= now,
                *extra,
            )
            .limit(1)
        )
        if recent_pair is not None:
            return "pair_cooldown"
    return None


class SharedKernelMixin:
    async def shared_candidate(self, world, candidate):
        return await self.session.get(Shared, (world.value, candidate))

    async def shared_current(self, world, row, characters):
        return await _current(self.session, characters, world, row)

    async def shared_pacing(self, row, now):
        return await _pacing(self.session, row, now)

    async def active_shared(self, world, character=None):
        query = select(Shared).where(Shared.world_id == world.value, Shared.state == "active")
        if character is not None:
            query = query.where(
                or_(
                    Shared.first_character_id == character.value,
                    Shared.second_character_id == character.value,
                )
            )
        return tuple(
            (
                await self.session.scalars(
                    query.order_by(Shared.planned_end, Shared.candidate_id).limit(64)
                )
            ).all()
        )

    async def shared_continuity_changed(self, world, row, start_event_id):
        position = await self.session.scalar(
            select(Event.ledger_position).where(
                Event.world_id == world.value, Event.event_id == start_event_id
            )
        )
        if position is None:
            raise WorldRuntimeUnavailableError("director_execution_failed")
        safe = case((func.json_valid(Event.payload), Event.payload), else_="{}")
        changed = await self.session.scalar(
            select(Event.event_id)
            .where(
                Event.world_id == world.value,
                Event.ledger_position > position,
                Event.event_type.in_(
                    (
                        "CharacterPlaced",
                        "CharacterRoutineStarted",
                        "CharacterRoutineEnded",
                        "CharacterRoutineInterrupted",
                    )
                ),
                func.json_extract(safe, "$.character_id").in_(
                    (
                        str(row.first_character_id),
                        str(row.second_character_id),
                        row.first_character_id.hex,
                        row.second_character_id.hex,
                    )
                ),
            )
            .limit(1)
        )
        return changed is not None
