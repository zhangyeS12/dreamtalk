from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from livingworld.domain.commands import CommandReceipt
from livingworld.domain.contracts import RequestId
from livingworld.domain.events import WorldEvent
from livingworld.domain.identifiers import (
    CharacterId,
    CorrelationId,
    EventId,
    KnowledgeAssertionId,
    LocationId,
    PlayerId,
    WorldId,
)
from livingworld.domain.knowledge import (
    KnowledgeAssertion,
    KnowledgeScope,
    Observation,
    ObservationChannel,
)
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


@pytest.fixture
def objects():
    world = WorldId(uuid4())
    location = LocationId(world, uuid4())
    other_location = LocationId(world, uuid4())
    player = PlayerId(world, uuid4())
    alice = CharacterId(world, uuid4())
    bob = CharacterId(world, uuid4())
    event_id = EventId(world, uuid4())
    truth_id = KnowledgeAssertionId(world, uuid4())
    now = datetime(2026, 9, 17, 12, 34, 56, 123456, tzinfo=UTC)
    # Deliberately beyond the exact integer range of IEEE-754 doubles.
    time = WorldTime(2**53 + 123)
    revision = Revision(17)
    clock = WorldClock(
        world,
        time,
        now.astimezone(timezone(timedelta(hours=8))),
        Decimal("1.234567890123456789"),
        ClockState.PAUSED,
        revision,
    )
    request = RequestId(uuid4())
    result = {
        "world": World(world, "测试世界", clock, revision),
        "location": Location(world, location, "Home", revision),
        "other_location": Location(world, other_location, "Cafe"),
        "connection": LocationConnection(world, location, other_location, revision),
        "player": Player(world, player, "Player", revision),
        "alice": Character(world, alice, "Alice", revision),
        "bob": Character(world, bob, "Bob"),
        "presence": PlayerPresence(
            world,
            player,
            location,
            PlayerActivity.INACTIVE,
            PlayerAvailability.BUSY,
            revision,
        ),
        "character_state": CharacterState(world, alice, other_location, revision),
        "relationship": Relationship(world, alice, bob, revision),
        "reverse_relationship": Relationship(world, bob, alice),
        "event": WorldEvent(
            event_id,
            world,
            "test.fact",
            time,
            {"nested": [{"text": "秘密", "value": 42}], "none": None},
            3,
            now,
            request,
            CorrelationId(uuid4()),
            "reason-1",
        ),
        "caused_event": WorldEvent(
            EventId(world, uuid4()),
            world,
            "test.consequence",
            WorldTime(-1),
            {},
            1,
            now,
            event_id,
        ),
        "truth": KnowledgeAssertion(
            truth_id,
            world,
            KnowledgeScope.TRUTH,
            None,
            "Alice",
            "visited",
            "Cafe",
            "confirmed",
            Decimal("1.000"),
            WorldTime(-10),
            time,
            event_id,
            revision=revision,
        ),
        "belief": KnowledgeAssertion(
            KnowledgeAssertionId(world, uuid4()),
            world,
            KnowledgeScope.CHARACTER_BELIEF,
            alice,
            "Alice",
            "visited",
            "Home",
            "believed",
            Decimal("0.1234567890123456789"),
            time,
            source_assertion_id=truth_id,
            revision=revision,
        ),
        "player_knowledge": KnowledgeAssertion(
            KnowledgeAssertionId(world, uuid4()),
            world,
            KnowledgeScope.PLAYER_KNOWLEDGE,
            player,
            "Alice",
            "visited",
            None,
            "uncertain",
            None,
            time,
        ),
        "observation": Observation(world, player, event_id, ObservationChannel.MESSAGE, time, now),
        "assertion_observation": Observation(
            world,
            alice,
            truth_id,
            ObservationChannel.INFERRED,
            WorldTime(-1),
        ),
        "receipt": CommandReceipt(
            request,
            world,
            "test.command",
            "stored",
            now,
            now + timedelta(microseconds=1),
            event_id,
            revision,
        ),
    }
    return result


@pytest.fixture
def populate(objects):
    async def run(database):
        store = database.store()
        for entity in objects.values():
            await store.add(entity)
        return store

    return run
