from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from livingworld.domain.errors import (
    ConcurrencyConflictError,
    CrossWorldReferenceError,
    DomainInvariantError,
    InvalidPresenceError,
)
from livingworld.domain.identifiers import CharacterId, LocationId, PlayerId, WorldId
from livingworld.domain.participants import (
    Character,
    CharacterState,
    Player,
    PlayerActivity,
    PlayerAvailability,
    PlayerPresence,
)
from livingworld.domain.relationships import Relationship
from livingworld.domain.values import Revision, WorldTime
from livingworld.domain.world import ClockState, Location, LocationConnection, World, WorldClock


@pytest.mark.parametrize("invalid", [0.5, 1.0, True, "1", datetime(2026, 9, 16, tzinfo=UTC)])
def test_world_time_never_accepts_wall_time_or_nonintegers(invalid):
    with pytest.raises(DomainInvariantError):
        WorldTime(invalid)


def test_world_time_is_immutable_exact_coordinate_not_identity():
    coordinate = WorldTime(10**30 + 1)
    assert coordinate.microseconds == 10**30 + 1
    assert WorldTime(-1) < WorldTime(0) < coordinate
    with pytest.raises(FrozenInstanceError):
        coordinate.microseconds = 2
    with pytest.raises(TypeError):
        _ = coordinate < datetime.now(UTC)
    assert not hasattr(coordinate, "advance")
    assert not hasattr(coordinate, "to_datetime")


def test_world_clock_normalizes_only_its_wall_timestamp(world_id):
    local = datetime(2026, 9, 16, 14, tzinfo=timezone(timedelta(hours=2)))
    clock = WorldClock(world_id, WorldTime(123), local, Decimal("2.5"), ClockState.PAUSED)
    assert clock.observed_wall_time_utc == datetime(2026, 9, 16, 12, tzinfo=UTC)
    assert clock.observed_wall_time_utc.tzinfo is UTC
    assert clock.logical_time == WorldTime(123)
    assert clock.state is ClockState.PAUSED
    assert not hasattr(clock, "advance")
    with pytest.raises(DomainInvariantError):
        replace(clock, observed_wall_time_utc=local.replace(tzinfo=None))
    with pytest.raises(DomainInvariantError):
        replace(clock, logical_time=local)


@pytest.mark.parametrize("scale", [Decimal("NaN"), Decimal("Infinity"), Decimal("-1"), 1.5])
def test_world_clock_rejects_invalid_scale(world_id, wall_time, scale):
    with pytest.raises(DomainInvariantError):
        WorldClock(world_id, WorldTime(0), wall_time, scale, ClockState.RUNNING)


def test_world_rejects_a_different_worlds_clock(world_id, other_world_id, wall_time):
    clock = WorldClock(other_world_id, WorldTime(0), wall_time, Decimal(1), ClockState.RUNNING)
    with pytest.raises(CrossWorldReferenceError):
        World(world_id, "test", clock)


@pytest.mark.parametrize("model", [Location, Player, Character])
def test_static_definitions_reject_identity_from_another_world(world_id, other_world_id, model):
    identity_type = {Location: LocationId, Player: PlayerId, Character: CharacterId}[model]
    with pytest.raises(CrossWorldReferenceError):
        model(world_id, identity_type(other_world_id, uuid4()), "test")


def test_topology_link_cannot_join_worlds(world_id, other_world_id, location_id):
    with pytest.raises(CrossWorldReferenceError):
        LocationConnection(world_id, location_id, LocationId(other_world_id, uuid4()))


def test_inactive_presence_keeps_position_and_has_independent_availability(
    world_id, player_id, location_id
):
    active = PlayerPresence(
        world_id,
        player_id,
        location_id,
        PlayerActivity.ACTIVE,
        PlayerAvailability.BUSY,
        Revision(4),
    )
    inactive = active.with_activity(PlayerActivity.INACTIVE, expected_revision=Revision(4))
    assert inactive.location_id == active.location_id == location_id
    assert inactive.availability is PlayerAvailability.BUSY
    assert inactive.revision == Revision(5)
    assert active.activity is PlayerActivity.ACTIVE
    assert active.revision == Revision(4)
    with pytest.raises(ConcurrencyConflictError):
        inactive.with_activity(PlayerActivity.ACTIVE, expected_revision=Revision(4))


@pytest.mark.parametrize("invalid_location", [None, "test", (), ["one", "two"], uuid4()])
def test_presence_cannot_silently_create_a_missing_or_multiple_location(
    world_id, player_id, invalid_location
):
    with pytest.raises(InvalidPresenceError):
        PlayerPresence(
            world_id,
            player_id,
            invalid_location,
            PlayerActivity.INACTIVE,
            PlayerAvailability.AVAILABLE,
        )


def test_presence_location_cannot_be_another_identity_type(world_id, player_id):
    with pytest.raises(InvalidPresenceError):
        PlayerPresence(
            world_id, player_id, player_id, PlayerActivity.ACTIVE, PlayerAvailability.AVAILABLE
        )


def test_position_replacement_is_atomic_and_rejects_cross_world(
    world_id, other_world_id, player_id, location_id
):
    initial = PlayerPresence(
        world_id, player_id, location_id, PlayerActivity.INACTIVE, PlayerAvailability.AVAILABLE
    )
    with pytest.raises(CrossWorldReferenceError):
        initial.at_location(LocationId(other_world_id, uuid4()), expected_revision=Revision())
    assert initial.location_id == location_id and initial.revision == Revision()
    target = LocationId(world_id, uuid4())
    changed = initial.at_location(target, expected_revision=Revision())
    assert changed.location_id == target
    assert changed.activity is PlayerActivity.INACTIVE
    assert changed.revision == Revision(1)
    assert initial.location_id == location_id


def test_presence_rejects_a_different_worlds_player(world_id, other_world_id, location_id):
    with pytest.raises(CrossWorldReferenceError):
        PlayerPresence(
            world_id,
            PlayerId(other_world_id, uuid4()),
            location_id,
            PlayerActivity.ACTIVE,
            PlayerAvailability.AVAILABLE,
        )


def test_character_identity_is_separate_from_runtime_location(
    world_id, other_world_id, character_id, location_id
):
    definition = Character(world_id, character_id, "test")
    state = CharacterState(world_id, character_id, location_id, Revision(3))
    assert not hasattr(definition, "location_id")
    assert definition.character_id == state.character_id
    with pytest.raises(CrossWorldReferenceError):
        replace(state, location_id=LocationId(other_world_id, uuid4()))
    with pytest.raises(CrossWorldReferenceError):
        replace(state, character_id=CharacterId(other_world_id, uuid4()))


@pytest.mark.parametrize(
    "source_type,target_type",
    [
        (CharacterId, CharacterId),
        (CharacterId, PlayerId),
        (PlayerId, CharacterId),
        (PlayerId, PlayerId),
    ],
)
def test_relationship_direction_and_isolation(world_id, other_world_id, source_type, target_type):
    source, target = source_type(world_id, uuid4()), target_type(world_id, uuid4())
    forward = Relationship(world_id, source, target)
    reverse = Relationship(world_id, target, source)
    assert forward != reverse
    assert forward.source_id == reverse.target_id
    assert not hasattr(forward, "affinity")
    with pytest.raises(CrossWorldReferenceError):
        Relationship(world_id, source, target_type(other_world_id, uuid4()))


@pytest.mark.parametrize("invalid", [-1, 0.5, True])
def test_revision_rejects_invalid_values(invalid):
    with pytest.raises(DomainInvariantError):
        Revision(invalid)


def test_revision_transition_only_increments_matching_current_revision():
    current = Revision(9)
    assert current.advance(Revision(9)) == Revision(10)
    for stale_or_future in (Revision(8), Revision(10)):
        with pytest.raises(ConcurrencyConflictError):
            current.advance(stale_or_future)
    assert current == Revision(9)


def test_typed_ids_cannot_be_confused_or_created_from_raw_strings(world_id):
    value = uuid4()
    assert LocationId(world_id, value) != PlayerId(world_id, value)
    with pytest.raises(DomainInvariantError):
        WorldId(str(value))
    with pytest.raises(DomainInvariantError):
        LocationId(str(world_id.value), value)
