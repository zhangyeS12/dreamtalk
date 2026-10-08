"""Persist opportunities in the planning claim, arrivals only in Kernel writes."""

from uuid import UUID

from livingworld.application.character_mobility import (
    DAY_US,
    RETURN_COOLDOWN_US,
    WINDOW_US,
    movement_route,
    unit_draw,
)
from livingworld.infrastructure.persistence.location_policy_models import CharacterMobilityRecord
from livingworld.infrastructure.persistence.location_rules import LocationRules


async def mobility_record(session, world, character):
    record = await session.get(CharacterMobilityRecord, (world, character))
    if record is None:
        record = CharacterMobilityRecord(
            world_id=world,
            character_id=character,
            next_draw_at=0,
            cooldown_until=0,
        )
        session.add(record)
    return record


def record_arrival(record, rules, destination, initial, now):
    if destination == initial:
        record.away_since = None
    elif record.away_since is None:
        record.away_since = now
    if rules.region(destination) != rules.region(initial):
        if record.far_since is None:
            record.far_since = now
    elif record.far_since is not None:
        record.far_since = None
        record.cooldown_until = max(record.cooldown_until, now + RETURN_COOLDOWN_US)


async def plan_mobility(session, world, state, rules, initial, locked, allowed, now):
    record = await mobility_record(session, world, state.character_id)
    # Observe current canonical presence, never backfill a trip or duration.
    record_arrival(record, rules, state.location_id, initial, now)
    foreign = any(rules.region(node) != rules.region(initial) for node in allowed)
    opportunity = False
    if not locked and foreign and now >= record.next_draw_at:
        record.next_draw_at = now + DAY_US
        opportunity = (
            now >= record.cooldown_until
            and record.far_since is None
            and unit_draw(f"{world}:{state.character_id}:{now // DAY_US}", "far") < 0.01
        )
    residency = rules.residencies.get(state.character_id, "strong")
    route, mode = (
        movement_route(
            initial=initial,
            current=state.location_id,
            allowed=allowed,
            region=rules.region,
            distance=rules.distance,
            residency=residency,
            now=now,
            away_since=record.away_since,
            far_opportunity=opportunity,
            seed=f"{world}:{state.character_id}:{now // WINDOW_US}",
        )
        if not locked
        else ((initial,), "locked")
    )
    return {
        "residency": residency,
        "mobility_route_ids": [str(node) for node in route],
        "mobility_mode": mode,
        "mobility_signature": await rules.movement_signature(session, world, state.character_id),
    }


async def mobility_is_current(session, world, snapshot, rules=None):
    if rules is None:
        rules = await LocationRules.load(session, world)

    from livingworld.infrastructure.persistence.authored_lifecycle import removed_character_ids

    removed = await removed_character_ids(session, world)
    for item in snapshot["characters"]:
        if UUID(item["character_id"]) in removed:
            return False
        signature = item.get("mobility_signature")
        if signature is not None and signature != await rules.movement_signature(
            session,
            world,
            UUID(item["character_id"]),
        ):
            return False
    return True
