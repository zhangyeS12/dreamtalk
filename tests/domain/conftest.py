from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from livingworld.domain.events import WorldEvent
from livingworld.domain.identifiers import (
    CharacterId,
    EventId,
    KnowledgeAssertionId,
    LocationId,
    PlayerId,
    WorldId,
)
from livingworld.domain.knowledge import KnowledgeAssertion, KnowledgeScope
from livingworld.domain.values import WorldTime


@pytest.fixture
def world_id():
    return WorldId(uuid4())


@pytest.fixture
def other_world_id():
    return WorldId(uuid4())


@pytest.fixture
def location_id(world_id):
    return LocationId(world_id, uuid4())


@pytest.fixture
def player_id(world_id):
    return PlayerId(world_id, uuid4())


@pytest.fixture
def character_id(world_id):
    return CharacterId(world_id, uuid4())


@pytest.fixture
def wall_time():
    return datetime(2026, 9, 16, 12, tzinfo=UTC)


@pytest.fixture
def event_factory(world_id, wall_time):
    def build(**overrides):
        fields = dict(
            event_id=EventId(world_id, uuid4()),
            world_id=world_id,
            event_type="test.event",
            occurred_at=WorldTime(50),
            payload={"nested": {"participants": ["one", "two"]}},
            payload_version=1,
            created_at=wall_time,
        )
        fields.update(overrides)
        return WorldEvent(**fields)

    return build


@pytest.fixture
def assertion_factory(world_id):
    def build(**overrides):
        fields = dict(
            assertion_id=KnowledgeAssertionId(world_id, uuid4()),
            world_id=world_id,
            scope=KnowledgeScope.TRUTH,
            owner=None,
            subject="test.subject",
            predicate="test.predicate",
            value=True,
            epistemic_status="test.status",
            confidence=Decimal("0.8"),
            valid_from=WorldTime(50),
        )
        fields.update(overrides)
        return KnowledgeAssertion(**fields)

    return build
