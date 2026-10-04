"""Reuse durable accepted encounters and canonical departures inside the Kernel UoW."""

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import aliased

from livingworld.application.encounter_policy import (
    MAX_ENCOUNTERS_PER_BATCH,
    NEW_CONTACT_WINDOW_US,
    PAIR_COOLDOWN_US,
    encounter_event_uuid,
)
from livingworld.infrastructure.persistence.encounter_models import (
    EncounterCandidateRecord as Encounter,
)
from livingworld.infrastructure.persistence.models import WorldEventRecord as Event


async def pacing_rejection(session, row, now):
    """Return a fixed reason, never history text; called under the single writer."""
    finished = (Encounter.world_id == row.world_id, Encounter.state == "finished")
    count = await session.scalar(
        select(func.count())
        .select_from(Encounter)
        .where(
            *finished,
            Encounter.plan_id == row.plan_id,
        )
    )
    if count >= MAX_ENCOUNTERS_PER_BATCH:
        return "batch_encounter_limit"
    previous = await session.scalar(
        select(Encounter)
        .where(
            *finished,
            Encounter.first_character_id == row.first_character_id,
            Encounter.second_character_id == row.second_character_id,
        )
        .order_by(Encounter.executed_at.desc(), Encounter.candidate_id)
        .limit(1)
    )
    if previous is None:
        # Count a counterpart only on their first successful recorded pair meeting.
        # Reunions with old contacts do not spend the new-counterpart allowance.
        older = aliased(Encounter)
        had_met = (
            select(older.candidate_id)
            .where(
                older.world_id == Encounter.world_id,
                older.state == "finished",
                older.first_character_id == Encounter.first_character_id,
                older.second_character_id == Encounter.second_character_id,
                older.executed_at < Encounter.executed_at,
            )
            .correlate(Encounter)
            .exists()
        )
        principals = (row.first_character_id, row.second_character_id)
        recent_new = await session.scalar(
            select(Encounter.candidate_id)
            .where(
                *finished,
                Encounter.executed_at > now - NEW_CONTACT_WINDOW_US,
                Encounter.executed_at <= now,
                or_(
                    Encounter.first_character_id.in_(principals),
                    Encounter.second_character_id.in_(principals),
                ),
                ~had_met,
            )
            .limit(1)
        )
        return "new_counterpart_daily_limit" if recent_new is not None else None
    if previous.executed_at > now - PAIR_COOLDOWN_US:
        return "pair_cooldown"
    # The canonical event is the episode boundary. Ledger order also distinguishes
    # departing and returning at the same WorldTime; UTC or presence revision cannot.
    position = await session.scalar(
        select(Event.ledger_position).where(
            Event.world_id == row.world_id,
            Event.event_id == encounter_event_uuid(previous.candidate_id),
            Event.event_type == "CharactersMet",
            Event.payload_version == 1,
        )
    )
    if position is None:
        return "encounter_history_unavailable"
    safe = case((func.json_valid(Event.payload), Event.payload), else_="{}")
    actor = func.json_extract(safe, "$.character_id")
    destination = func.json_extract(safe, "$.location_id")
    principal_ids = tuple(
        value
        for identity in (row.first_character_id, row.second_character_id)
        for value in (str(identity), identity.hex)
    )
    old_place = (str(previous.location_id), previous.location_id.hex)
    departed = await session.scalar(
        select(Event.event_id)
        .where(
            Event.world_id == row.world_id,
            Event.ledger_position > position,
            Event.event_type.in_(("CharacterPlaced", "CharacterRoutineStarted")),
            Event.payload_version == 1,
            actor.in_(principal_ids),
            func.json_type(safe, "$.location_id") == "text",
            destination.not_in(old_place),
        )
        .limit(1)
    )
    return None if departed is not None else "continuous_copresence"
