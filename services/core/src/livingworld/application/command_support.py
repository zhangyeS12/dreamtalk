"""Shared command payloads and revision validation; no commits."""

from uuid import uuid5

from livingworld.application.commands import (
    WorldCommand,
)
from livingworld.application.fingerprints import decimal_input, id_input
from livingworld.domain.errors import ConcurrencyConflictError
from livingworld.domain.identifiers import (
    EventId,
)
from livingworld.domain.knowledge import (
    KnowledgeAssertion,
)
from livingworld.domain.relationships import RelationshipMetrics
from livingworld.domain.values import Revision

EVENT_PAYLOAD_VERSION = 1


def event_identity(command: WorldCommand, ordinal: int) -> EventId:
    return EventId(
        command.world_id,
        uuid5(command.request_id.value, f"livingworld:{command.world_id.value}:{ordinal}"),
    )


def assertion_payload(assertion: KnowledgeAssertion) -> dict:
    return {
        "assertion_id": str(assertion.assertion_id.value),
        "scope": assertion.scope.value,
        "owner": id_input(assertion.owner) if assertion.owner is not None else None,
        "subject": assertion.subject,
        "predicate": assertion.predicate,
        "value": assertion.value,
        "epistemic_status": assertion.epistemic_status,
        "confidence": decimal_input(assertion.confidence),
        "valid_from": assertion.valid_from.microseconds,
        "valid_to": assertion.valid_to.microseconds if assertion.valid_to is not None else None,
        "source_assertion_id": str(assertion.source_assertion_id.value)
        if assertion.source_assertion_id is not None
        else None,
        "provenance_event_id": str(assertion.provenance_event_id.value)
        if assertion.provenance_event_id is not None
        else None,
        "revision": assertion.revision.value,
    }


def metrics_payload(metrics: RelationshipMetrics) -> dict[str, int]:
    return {
        "affinity": metrics.affinity,
        "trust": metrics.trust,
        "familiarity": metrics.familiarity,
    }


def expect_revision(
    kind: str, identity: object, actual: Revision | None, expected: Revision | None
) -> None:
    if actual != expected:
        raise ConcurrencyConflictError(
            f"{kind} does not match expected existence/revision",
            resource_kind=kind,
            resource_identity=identity,
            expected_revision=expected,
            actual_revision=actual,
        )
