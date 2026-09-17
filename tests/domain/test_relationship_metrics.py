from dataclasses import FrozenInstanceError
from uuid import uuid4

import pytest
from livingworld.domain.errors import ConcurrencyConflictError, DomainInvariantError
from livingworld.domain.identifiers import CharacterId, WorldId
from livingworld.domain.relationships import Relationship, RelationshipMetrics
from livingworld.domain.values import Revision


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("affinity", -101),
        ("affinity", 101),
        ("trust", -101),
        ("trust", 101),
        ("familiarity", -1),
        ("familiarity", 101),
        ("affinity", True),
        ("trust", 1.0),
    ],
)
def test_metrics_reject_invalid_ranges_and_non_integer_values(name, value):
    with pytest.raises(DomainInvariantError, match=name):
        RelationshipMetrics(**{name: value})


def test_metrics_and_directional_change_are_immutable_and_versioned():
    world = WorldId(uuid4())
    relationship = Relationship(world, CharacterId(world, uuid4()), CharacterId(world, uuid4()))
    with pytest.raises(FrozenInstanceError):
        relationship.metrics.affinity = 1
    updated = relationship.change(-100, 100, 100, expected_revision=Revision())
    assert updated.metrics == RelationshipMetrics(-100, 100, 100)
    assert updated.revision == Revision(1)
    assert relationship.metrics == RelationshipMetrics() and relationship.revision == Revision()
    with pytest.raises(ConcurrencyConflictError):
        updated.change(1, 0, 0, expected_revision=Revision())
    with pytest.raises(DomainInvariantError):
        updated.change(-1, 0, 0, expected_revision=updated.revision)
