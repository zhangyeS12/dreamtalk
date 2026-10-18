"""Relationships command validation and projection writes; the caller owns commit."""

from livingworld.application.command_mutation import CommandMutation, MutationContext
from livingworld.application.command_support import expect_revision, metrics_payload
from livingworld.application.commands import (
    ChangeRelationship,
)
from livingworld.application.errors import (
    EntityNotFoundError,
)
from livingworld.application.fingerprints import id_input
from livingworld.application.results import RelationshipReference
from livingworld.domain.identifiers import (
    CharacterId,
)
from livingworld.domain.relationships import Relationship
from livingworld.domain.values import same_world


async def change_relationship(
    context: MutationContext, command: ChangeRelationship
) -> CommandMutation:
    uow = context.uow
    world = context.world
    observation_id = None
    same_world(world.world_id, command.source_id, command.target_id)
    for identity in (command.source_id, command.target_id):
        participant = (
            await uow.characters.get(identity)
            if isinstance(identity, CharacterId)
            else await uow.players.get(identity)
        )
        if participant is None:
            raise EntityNotFoundError("Relationship participant does not exist")
    before = await uow.relationships.get(command.source_id, command.target_id)
    expect_revision(
        "Relationship",
        RelationshipReference(command.source_id, command.target_id),
        before.revision if before else None,
        command.expected_relationship_revision,
    )
    initial = before or Relationship(world.world_id, command.source_id, command.target_id)
    after = initial.change(
        command.affinity_delta,
        command.trust_delta,
        command.familiarity_delta,
        expected_revision=initial.revision,
    )
    events = [
        (
            "RelationshipChanged",
            {
                "source": id_input(after.source_id),
                "target": id_input(after.target_id),
                "source_character_id": str(after.source_id.value)
                if isinstance(after.source_id, CharacterId)
                else None,
                "target_character_id": str(after.target_id.value)
                if isinstance(after.target_id, CharacterId)
                else None,
                "edge_existed": before is not None,
                "before": metrics_payload(initial.metrics),
                "delta": {
                    "affinity": command.affinity_delta,
                    "trust": command.trust_delta,
                    "familiarity": command.familiarity_delta,
                },
                "after": metrics_payload(after.metrics),
                "revision": after.revision.value,
            },
        )
    ]
    reference = RelationshipReference(after.source_id, after.target_id)
    revision = after.revision

    async def apply() -> None:
        await uow.relationships.put(after, command.expected_relationship_revision)

    return CommandMutation(events, reference, revision, apply, observation_id)
