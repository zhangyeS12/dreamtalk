from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

import pytest
from livingworld.domain.errors import (
    CrossWorldReferenceError,
    DomainInvariantError,
    InvalidKnowledgeOwnershipError,
)
from livingworld.domain.identifiers import CharacterId, EventId, KnowledgeAssertionId, PlayerId
from livingworld.domain.knowledge import KnowledgeScope, Observation, ObservationChannel
from livingworld.domain.values import WorldTime


@pytest.mark.parametrize(
    "scope,owner_kind",
    [
        (KnowledgeScope.TRUTH, "character"),
        (KnowledgeScope.TRUTH, "player"),
        (KnowledgeScope.TRUTH, "both"),
        (KnowledgeScope.CHARACTER_BELIEF, "none"),
        (KnowledgeScope.CHARACTER_BELIEF, "player"),
        (KnowledgeScope.CHARACTER_BELIEF, "both"),
        (KnowledgeScope.PLAYER_KNOWLEDGE, "none"),
        (KnowledgeScope.PLAYER_KNOWLEDGE, "character"),
        (KnowledgeScope.PLAYER_KNOWLEDGE, "both"),
    ],
)
def test_scope_requires_exactly_its_owner(
    assertion_factory, character_id, player_id, scope, owner_kind
):
    owners = {
        "none": None,
        "character": character_id,
        "player": player_id,
        "both": (character_id, player_id),
    }
    with pytest.raises(InvalidKnowledgeOwnershipError):
        assertion_factory(scope=scope, owner=owners[owner_kind])


def test_belief_may_conflict_with_truth_without_being_corrected(
    assertion_factory, character_id, player_id
):
    truth = assertion_factory(value=True)
    belief = assertion_factory(
        scope=KnowledgeScope.CHARACTER_BELIEF, owner=character_id, value=False
    )
    player_knowledge = assertion_factory(
        scope=KnowledgeScope.PLAYER_KNOWLEDGE,
        owner=player_id,
        value=False,
        source_assertion_id=belief.assertion_id,
    )
    assert truth.subject == belief.subject == player_knowledge.subject
    assert truth.predicate == belief.predicate == player_knowledge.predicate
    assert truth.value is True and belief.value is False and player_knowledge.value is False
    assert (
        truth.owner is None and belief.owner == character_id and player_knowledge.owner == player_id
    )


@pytest.mark.parametrize(
    "scope,owner_type",
    [(KnowledgeScope.CHARACTER_BELIEF, CharacterId), (KnowledgeScope.PLAYER_KNOWLEDGE, PlayerId)],
)
def test_valid_owner_type_still_cannot_cross_worlds(
    assertion_factory, other_world_id, scope, owner_type
):
    with pytest.raises(CrossWorldReferenceError):
        assertion_factory(scope=scope, owner=owner_type(other_world_id, uuid4()))


@pytest.mark.parametrize(
    "field,identity_type",
    [
        ("assertion_id", KnowledgeAssertionId),
        ("provenance_event_id", EventId),
        ("source_assertion_id", KnowledgeAssertionId),
    ],
)
def test_assertion_references_cannot_cross_worlds(
    assertion_factory, other_world_id, field, identity_type
):
    with pytest.raises(CrossWorldReferenceError):
        assertion_factory(**{field: identity_type(other_world_id, uuid4())})


def test_knowledge_validity_uses_world_axis_and_checks_order(assertion_factory, wall_time):
    assertion = assertion_factory(valid_from=WorldTime(100), valid_to=WorldTime(101))
    assert assertion.valid_to > assertion.valid_from
    assert assertion_factory(valid_to=None).valid_to is None
    with pytest.raises(DomainInvariantError):
        replace(assertion, valid_to=WorldTime(99))
    for field in ("valid_from", "valid_to"):
        with pytest.raises(DomainInvariantError):
            replace(assertion, **{field: wall_time})


@pytest.mark.parametrize(
    "confidence", [Decimal("-0.1"), Decimal("1.1"), Decimal("NaN"), Decimal("Infinity"), 0.5]
)
def test_knowledge_confidence_has_finite_explicit_bounds(assertion_factory, confidence):
    with pytest.raises(DomainInvariantError):
        assertion_factory(confidence=confidence)


def test_assertion_value_is_a_defensive_structured_copy(assertion_factory):
    original = {"evidence": ["original"]}
    assertion = assertion_factory(value=original, confidence=None)
    original["evidence"].append("changed")
    assert assertion.value["evidence"] == ("original",)
    with pytest.raises(TypeError):
        assertion.value["evidence"] = ()


@pytest.mark.parametrize("channel", list(ObservationChannel))
@pytest.mark.parametrize("target_type", [EventId, KnowledgeAssertionId])
def test_explicit_observation_accepts_supported_channel_and_typed_target(
    world_id, player_id, channel, target_type
):
    observation = Observation(
        world_id, player_id, target_type(world_id, uuid4()), channel, WorldTime(100)
    )
    assert observation.channel is channel and observation.observed_at == WorldTime(100)
    assert not hasattr(observation, "propagate")


@pytest.mark.parametrize("channel", ["telepathy", "witnessed", None])
def test_observation_requires_valid_channel_enum(world_id, player_id, channel):
    with pytest.raises(DomainInvariantError):
        Observation(world_id, player_id, EventId(world_id, uuid4()), channel, WorldTime(1))


@pytest.mark.parametrize(
    "field,identity_type",
    [
        ("principal_id", PlayerId),
        ("principal_id", CharacterId),
        ("target_id", EventId),
        ("target_id", KnowledgeAssertionId),
    ],
)
def test_observation_cannot_bridge_worlds(
    world_id, other_world_id, player_id, field, identity_type
):
    fields = dict(
        world_id=world_id,
        principal_id=player_id,
        target_id=EventId(world_id, uuid4()),
        channel=ObservationChannel.TOLD,
        observed_at=WorldTime(1),
    )
    fields[field] = identity_type(other_world_id, uuid4())
    with pytest.raises(CrossWorldReferenceError):
        Observation(**fields)


def test_observation_uses_logical_time_and_optional_utc_audit(world_id, character_id, wall_time):
    observation = Observation(
        world_id,
        character_id,
        EventId(world_id, uuid4()),
        ObservationChannel.NEWS,
        WorldTime(1),
        created_at=wall_time,
    )
    assert observation.created_at.tzinfo is wall_time.tzinfo
    with pytest.raises(DomainInvariantError):
        replace(observation, created_at=wall_time.replace(tzinfo=None))
    with pytest.raises(DomainInvariantError):
        replace(observation, observed_at=wall_time)
