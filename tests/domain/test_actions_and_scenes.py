from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from livingworld.domain.actions import (
    ActionKind,
    ActionProposal,
    ActionProposer,
    MovePlayerPayload,
    ProposerKind,
)
from livingworld.domain.errors import CrossWorldReferenceError, DomainInvariantError
from livingworld.domain.identifiers import (
    CharacterId,
    LocationId,
    PlayerId,
    SceneId,
    SceneParticipantId,
    WorldId,
)
from livingworld.domain.scenes import Scene, SceneParticipant, SceneStatus
from livingworld.domain.values import Revision, WorldTime


def test_action_contract_is_immutable_typed_and_keeps_proposer_distinct_from_actor():
    world = WorldId(uuid4())
    player = PlayerId(world, uuid4())
    destination = LocationId(world, uuid4())
    proposal = ActionProposal(
        world,
        ActionKind.MOVE_PLAYER,
        1,
        ActionProposer(ProposerKind.PLAYER_INPUT, player),
        player,
        MovePlayerPayload(destination, Revision(2)),
    )
    assert proposal.proposer.principal_id == proposal.actor_id
    with pytest.raises(FrozenInstanceError):
        proposal.actor_id = None
    with pytest.raises(DomainInvariantError, match="exact principal"):
        ActionProposer(ProposerKind.CHARACTER_RUNTIME, player)


def test_scene_location_is_immutable_and_close_is_one_way():
    world = WorldId(uuid4())
    scene_id = SceneId(world, uuid4())
    location = LocationId(world, uuid4())
    scene = Scene(
        scene_id,
        world,
        location,
        SceneStatus.OPEN,
        WorldTime(10),
        None,
        Revision(),
        datetime(2026, 9, 20, tzinfo=UTC),
    )
    closed = scene.close(WorldTime(20), Revision())
    assert closed.location_id == location
    assert closed.status is SceneStatus.CLOSED and closed.revision == Revision(1)
    with pytest.raises(DomainInvariantError, match="Closed Scene"):
        closed.advance(Revision(1))


def test_scene_participant_history_requires_typed_identity_and_monotonic_time():
    world = WorldId(uuid4())
    participant = SceneParticipant(
        SceneParticipantId(world, uuid4()),
        world,
        SceneId(world, uuid4()),
        CharacterId(world, uuid4()),
        WorldTime(10),
    )
    assert participant.active
    assert participant.leave(WorldTime(11)).left_at == WorldTime(11)
    with pytest.raises(DomainInvariantError, match="precede"):
        participant.leave(WorldTime(9))


def test_scene_and_action_reject_cross_world_references():
    world = WorldId(uuid4())
    other = WorldId(uuid4())
    player = PlayerId(world, uuid4())
    with pytest.raises(CrossWorldReferenceError):
        ActionProposal(
            world,
            ActionKind.MOVE_PLAYER,
            1,
            ActionProposer(ProposerKind.PLAYER_INPUT, player),
            player,
            MovePlayerPayload(LocationId(other, uuid4()), Revision()),
        )
    with pytest.raises(CrossWorldReferenceError):
        Scene(
            SceneId(world, uuid4()),
            world,
            LocationId(other, uuid4()),
            SceneStatus.OPEN,
            WorldTime(10),
            None,
            Revision(),
            datetime(2026, 9, 20, tzinfo=UTC),
        )
