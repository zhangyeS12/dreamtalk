from datetime import UTC, datetime
from uuid import uuid4

import pytest
from livingworld.domain.errors import (
    CrossWorldReferenceError,
    DomainInvariantError,
    UnsupportedMemoryKindError,
)
from livingworld.domain.identifiers import CharacterId, MemoryId, ObservationId, WorldId
from livingworld.domain.memory import (
    MAX_EPISODIC_MEMORY_CONTENT_BYTES,
    EpisodicMemory,
    MemoryContentFormat,
    MemoryKind,
    MemoryProvenanceKind,
    MemorySalience,
)
from livingworld.domain.values import WorldTime


def memory(**changes):
    world = changes.pop("world_id", WorldId(uuid4()))
    values = {
        "memory_id": MemoryId(world, uuid4()),
        "world_id": world,
        "owner_character_id": CharacterId(world, uuid4()),
        "content": "I remember the rain beginning.",
        "experienced_from": WorldTime(100),
        "experienced_to": WorldTime(120),
        "formed_at": WorldTime(130),
        "created_at_utc": datetime(2026, 9, 21, tzinfo=UTC),
        "source_observation_ids": (ObservationId(world, uuid4()),),
    }
    values.update(changes)
    return EpisodicMemory(**values)


def test_episodic_memory_is_immutable_and_keeps_time_provenance_distinct():
    value = memory(salience=MemorySalience(0))
    assert value.experienced_from == WorldTime(100)
    assert value.experienced_to == WorldTime(120)
    assert value.formed_at == WorldTime(130)
    assert value.salience == MemorySalience(0)
    assert value.kind is MemoryKind.EPISODIC
    assert value.content_format is MemoryContentFormat.PLAIN_TEXT
    assert value.provenance_kind is MemoryProvenanceKind.OBSERVATION_EVIDENCE
    with pytest.raises(AttributeError):
        value.content = "rewritten"


@pytest.mark.parametrize("salience", [-1, 101, 1.5, True])
def test_salience_is_exact_bounded_integer_and_none_remains_distinct(salience):
    with pytest.raises(DomainInvariantError):
        MemorySalience(salience)
    assert memory(salience=None).salience is None
    assert memory(salience=MemorySalience(0)).salience != memory(salience=None).salience


def test_memory_requires_bounded_nonempty_content_and_ordered_unique_evidence():
    with pytest.raises(DomainInvariantError, match="nonempty"):
        memory(content="   ")
    with pytest.raises(DomainInvariantError, match="size"):
        memory(content="界" * (MAX_EPISODIC_MEMORY_CONTENT_BYTES // 3 + 1))
    with pytest.raises(DomainInvariantError, match="requires Observation"):
        memory(source_observation_ids=())
    source = memory().source_observation_ids[0]
    with pytest.raises(DomainInvariantError, match="unique"):
        memory(source_observation_ids=(source, source))


def test_memory_rejects_cross_world_evidence_and_impossible_chronology():
    value = memory()
    other = WorldId(uuid4())
    with pytest.raises(CrossWorldReferenceError):
        memory(
            world_id=value.world_id,
            source_observation_ids=(ObservationId(other, uuid4()),),
        )
    with pytest.raises(DomainInvariantError, match="reversed"):
        memory(experienced_from=WorldTime(121), experienced_to=WorldTime(120))
    with pytest.raises(DomainInvariantError, match="before"):
        memory(formed_at=WorldTime(119))


@pytest.mark.parametrize(
    "changes",
    [
        {"kind": MemoryKind.REFLECTION},
        {"kind": MemoryKind.CONSOLIDATED},
        {"kind_version": 2},
        {"content_version": 2},
        {"provenance_version": 2},
    ],
)
def test_reserved_or_unknown_memory_versions_fail_typed(changes):
    with pytest.raises(UnsupportedMemoryKindError):
        memory(**changes)


def test_memory_requires_utc_aware_audit_time():
    with pytest.raises(DomainInvariantError, match="timezone-aware"):
        memory(created_at_utc=datetime(2026, 9, 21))
