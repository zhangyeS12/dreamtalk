"""Knowledge command validation and projection writes; the caller owns commit."""

from uuid import uuid4

from livingworld.application.command_mutation import CommandMutation, MutationContext
from livingworld.application.command_support import assertion_payload, event_identity
from livingworld.application.commands import (
    AcquireKnowledge,
    AssertWorldTruth,
    FormCharacterBelief,
)
from livingworld.application.errors import (
    EntityAlreadyExistsError,
    EntityNotFoundError,
)
from livingworld.application.fingerprints import id_input
from livingworld.domain.errors import DomainInvariantError
from livingworld.domain.identifiers import (
    CharacterId,
    ObservationId,
)
from livingworld.domain.knowledge import (
    KnowledgeAssertion,
    KnowledgeScope,
    Observation,
    ObservationChannel,
)


async def form_character_belief(
    context: MutationContext, command: FormCharacterBelief
) -> CommandMutation:
    uow = context.uow
    world = context.world
    observation_id = None
    if await uow.characters.get(command.character_id) is None:
        raise EntityNotFoundError("Belief owner does not exist")
    if await uow.knowledge.get(command.assertion_id) is not None:
        raise EntityAlreadyExistsError("KnowledgeAssertion already exists")
    if (
        command.source_assertion_id is not None
        and await uow.knowledge.get(command.source_assertion_id) is None
    ):
        raise EntityNotFoundError("Source KnowledgeAssertion does not exist")
    if command.provenance_event_id is not None and (
        not await uow.event_references.exists(command.provenance_event_id)
    ):
        raise EntityNotFoundError("Provenance WorldEvent does not exist")
    assertion = KnowledgeAssertion(
        command.assertion_id,
        world.world_id,
        KnowledgeScope.CHARACTER_BELIEF,
        command.character_id,
        command.subject,
        command.predicate,
        command.value,
        command.epistemic_status,
        command.confidence,
        command.valid_from,
        command.valid_to,
        provenance_event_id=command.provenance_event_id,
        source_assertion_id=command.source_assertion_id,
    )
    events = [("CharacterBeliefFormed", assertion_payload(assertion))]
    reference, revision = (assertion.assertion_id, assertion.revision)

    async def apply() -> None:
        await uow.knowledge.add(assertion)

    return CommandMutation(events, reference, revision, apply, observation_id)


async def assert_world_truth(
    context: MutationContext, command: AssertWorldTruth
) -> CommandMutation:
    uow = context.uow
    world = context.world
    logical_time = context.logical_time
    observation_id = None
    if await uow.knowledge.get(command.assertion_id) is not None:
        raise EntityAlreadyExistsError("KnowledgeAssertion already exists")
    assertion = KnowledgeAssertion(
        command.assertion_id,
        world.world_id,
        KnowledgeScope.TRUTH,
        None,
        command.subject,
        command.predicate,
        command.value,
        command.epistemic_status,
        command.confidence,
        command.valid_from if command.valid_from is not None else logical_time,
        command.valid_to,
        provenance_event_id=event_identity(command, 0),
    )
    events = [("WorldTruthAsserted", assertion_payload(assertion))]
    reference, revision = (assertion.assertion_id, assertion.revision)

    async def apply() -> None:
        await uow.knowledge.add(assertion)

    return CommandMutation(events, reference, revision, apply, observation_id)


async def acquire_knowledge(context: MutationContext, command: AcquireKnowledge) -> CommandMutation:
    uow = context.uow
    world = context.world
    now = context.now
    logical_time = context.logical_time
    # Command.__post_init__ normalizes the channel-specific default before dispatch.
    assert command.epistemic_status is not None
    observation_id = None
    if command.channel is ObservationChannel.INFERRED:
        raise DomainInvariantError(
            "Inferred acquisition requires a future explicit reasoning policy"
        )
    participant = (
        await uow.characters.get(command.receiver_id)
        if isinstance(command.receiver_id, CharacterId)
        else await uow.players.get(command.receiver_id)
    )
    if participant is None:
        raise EntityNotFoundError("Knowledge receiver does not exist")
    source = await uow.knowledge.get(command.source_assertion_id)
    if source is None:
        raise EntityNotFoundError("Source KnowledgeAssertion does not exist")
    if await uow.knowledge.get(command.assertion_id) is not None:
        raise EntityAlreadyExistsError("KnowledgeAssertion already exists")
    observation_id = ObservationId(world.world_id, uuid4())
    observation = Observation(
        world.world_id,
        command.receiver_id,
        source.assertion_id,
        command.channel,
        logical_time,
        now,
        observation_id=observation_id,
    )
    assertion = KnowledgeAssertion(
        command.assertion_id,
        world.world_id,
        KnowledgeScope.CHARACTER_BELIEF
        if isinstance(command.receiver_id, CharacterId)
        else KnowledgeScope.PLAYER_KNOWLEDGE,
        command.receiver_id,
        source.subject,
        source.predicate,
        source.value,
        command.epistemic_status,
        command.confidence,
        logical_time,
        provenance_event_id=event_identity(command, 1),
        source_assertion_id=source.assertion_id,
    )
    observation_payload = {
        "observation_id": str(observation_id.value),
        "receiver": id_input(command.receiver_id),
        "source_assertion_id": str(source.assertion_id.value),
        "channel": command.channel.value,
        "observed_at": observation.observed_at.microseconds,
        "created_at": now.isoformat(),
    }
    events = [
        ("ObservationRecorded", observation_payload),
        ("KnowledgeAcquired", assertion_payload(assertion) | observation_payload),
    ]
    reference, revision = (assertion.assertion_id, assertion.revision)

    async def apply() -> None:
        await uow.observations.add(observation)
        await uow.knowledge.add(assertion)

    return CommandMutation(events, reference, revision, apply, observation_id)
