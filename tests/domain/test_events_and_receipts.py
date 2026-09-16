from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from livingworld.domain.commands import CommandReceipt
from livingworld.domain.contracts import RequestId
from livingworld.domain.errors import CrossWorldReferenceError, DomainInvariantError
from livingworld.domain.identifiers import CorrelationId, EventId, KnowledgeAssertionId
from livingworld.domain.values import WorldTime


def test_event_is_immutable_including_nested_payload_and_owns_a_copy(event_factory):
    original = {"nested": {"items": [{"value": "original"}]}}
    event = event_factory(payload=original)
    original["nested"]["items"][0]["value"] = "changed"
    original["nested"]["items"].append({"value": "extra"})
    assert event.payload["nested"]["items"][0]["value"] == "original"
    assert len(event.payload["nested"]["items"]) == 1
    with pytest.raises(FrozenInstanceError):
        event.event_type = "changed"
    with pytest.raises(FrozenInstanceError):
        del event.payload
    with pytest.raises(TypeError):
        event.payload["nested"]["items"][0]["value"] = "changed"
    with pytest.raises(AttributeError):
        event.payload["nested"]["items"].append("changed")
    assert not hasattr(event, "update") and not hasattr(event, "delete")


def test_same_world_coordinate_does_not_merge_event_identity(event_factory):
    first = event_factory(occurred_at=WorldTime(100))
    second = event_factory(occurred_at=WorldTime(100))
    assert first.occurred_at == second.occurred_at
    assert first.event_id != second.event_id
    assert first != second


def test_event_logical_occurrence_and_wall_creation_are_independent(event_factory):
    created = datetime(2026, 9, 16, 14, tzinfo=timezone(timedelta(hours=2)))
    event = event_factory(occurred_at=WorldTime(-1), created_at=created)
    assert event.occurred_at == WorldTime(-1)
    assert event.created_at == datetime(2026, 9, 16, 12, tzinfo=UTC)
    assert event.created_at.tzinfo is UTC
    with pytest.raises(DomainInvariantError):
        event_factory(created_at=created.replace(tzinfo=None))
    with pytest.raises(DomainInvariantError):
        event_factory(occurred_at=created)


@pytest.mark.parametrize("version", [0, -1, True, 1.5])
def test_event_payload_requires_explicit_positive_integer_version(event_factory, version):
    with pytest.raises(DomainInvariantError):
        event_factory(payload_version=version)


@pytest.mark.parametrize(
    "payload", [{1: "value"}, {"value": float("nan")}, {"value": object()}, []]
)
def test_event_rejects_non_json_or_non_object_payload(event_factory, payload):
    with pytest.raises(DomainInvariantError):
        event_factory(payload=payload)


def test_event_rejects_cyclic_payload(event_factory):
    cycle = {}
    cycle["cycle"] = cycle
    with pytest.raises(DomainInvariantError):
        event_factory(payload=cycle)


@pytest.mark.parametrize("field", ["event_id", "causation_id"])
def test_event_world_scoped_ids_cannot_cross_worlds(event_factory, other_world_id, field):
    with pytest.raises(CrossWorldReferenceError):
        event_factory(**{field: EventId(other_world_id, uuid4())})


def test_event_metadata_uses_typed_cause_and_correlation_without_executing_deduplication(
    event_factory,
):
    request = RequestId(uuid4())
    correlation = CorrelationId(uuid4())
    first = event_factory(
        causation_id=request, correlation_id=correlation, idempotency_key="test.key"
    )
    second = event_factory(
        causation_id=request, correlation_id=correlation, idempotency_key="test.key"
    )
    assert first.causation_id == second.causation_id == request
    assert first.correlation_id == second.correlation_id == correlation
    assert first.event_id != second.event_id
    with pytest.raises(DomainInvariantError):
        event_factory(causation_id="raw-string")


def test_receipt_normalizes_wall_times_and_validates_completion_order(world_id, wall_time):
    receipt = CommandReceipt(
        RequestId(uuid4()),
        world_id,
        "test.command",
        "test.status",
        wall_time,
        completed_at=wall_time.astimezone(timezone(timedelta(hours=2))),
    )
    assert receipt.created_at.tzinfo is UTC and receipt.completed_at.tzinfo is UTC
    assert receipt.completed_at == receipt.created_at
    with pytest.raises(DomainInvariantError):
        replace(receipt, completed_at=wall_time - timedelta(microseconds=1))
    for field in ("created_at", "completed_at"):
        with pytest.raises(DomainInvariantError):
            replace(receipt, **{field: wall_time.replace(tzinfo=None)})
    assert not hasattr(receipt, "execute")


@pytest.mark.parametrize("reference_type", [EventId, KnowledgeAssertionId])
def test_receipt_result_reference_stays_inside_world(
    world_id, other_world_id, wall_time, reference_type
):
    with pytest.raises(CrossWorldReferenceError):
        CommandReceipt(
            RequestId(uuid4()),
            world_id,
            "test.command",
            "test.status",
            wall_time,
            result_reference=reference_type(other_world_id, uuid4()),
        )


def test_receipt_reuses_existing_validated_request_id_boundary(world_id, wall_time):
    with pytest.raises(DomainInvariantError):
        CommandReceipt(RequestId("not-a-uuid"), world_id, "test.command", "test.status", wall_time)
