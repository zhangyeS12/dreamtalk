"""Participants command validation and projection writes; the caller owns commit."""

from uuid import uuid4

from livingworld.application.command_mutation import CommandMutation, MutationContext
from livingworld.application.command_support import event_identity, expect_revision
from livingworld.application.commands import (
    CreateCharacter,
    CreatePlayer,
    PlaceCharacter,
    SetPlayerAvailability,
)
from livingworld.application.errors import (
    EntityAlreadyExistsError,
    EntityNotFoundError,
)
from livingworld.application.routine_lifecycle import settle_routines
from livingworld.domain.errors import DomainInvariantError
from livingworld.domain.identifiers import (
    ObservationId,
)
from livingworld.domain.knowledge import (
    Observation,
    ObservationBasis,
    ObservationChannel,
)
from livingworld.domain.participants import Character, CharacterState, Player, PlayerPresence
from livingworld.domain.values import Revision, same_world


async def create_player(context: MutationContext, command: CreatePlayer) -> CommandMutation:
    uow = context.uow
    world = context.world
    observation_id = None
    player = Player(world.world_id, command.player_id, command.name)
    await context.location(command.initial_location_id)
    presence = PlayerPresence(
        world.world_id,
        player.player_id,
        command.initial_location_id,
        command.activity_state,
        command.availability_state,
    )
    if await uow.players.get(player.player_id) is not None:
        raise EntityAlreadyExistsError("Player already exists")
    events = [
        (
            "PlayerCreated",
            {"player_id": str(player.player_id.value), "name": player.name, "revision": 0},
        ),
        (
            "PlayerPlaced",
            {
                "player_id": str(player.player_id.value),
                "location_id": str(presence.location_id.value),
                "activity": presence.activity.value,
                "availability": presence.availability.value,
                "revision": 0,
            },
        ),
    ]
    reference, revision = (player.player_id, presence.revision)

    async def apply() -> None:
        await uow.players.add(player, presence)

    return CommandMutation(events, reference, revision, apply, observation_id)


async def set_player_availability(
    context: MutationContext, command: SetPlayerAvailability
) -> CommandMutation:
    uow = context.uow
    observation_id = None
    player = await uow.players.get(command.player_id)
    before = await uow.players.presence(command.player_id)
    if player is None or before is None:
        raise EntityNotFoundError("Player does not exist")
    expect_revision(
        "PlayerPresence", command.player_id, before.revision, command.expected_presence_revision
    )
    if before.availability is command.availability_state:
        raise DomainInvariantError("Player availability is already set")
    after = before.with_availability(
        command.availability_state, expected_revision=command.expected_presence_revision
    )
    events = [
        (
            "PlayerAvailabilityChanged",
            {
                "player_id": str(after.player_id.value),
                "before_availability": before.availability.value,
                "availability": after.availability.value,
                "revision": after.revision.value,
            },
        )
    ]
    reference, revision = (after.player_id, after.revision)

    async def apply() -> None:
        await uow.players.replace_presence(after, command.expected_presence_revision)

    return CommandMutation(events, reference, revision, apply, observation_id)


async def create_character(context: MutationContext, command: CreateCharacter) -> CommandMutation:
    uow = context.uow
    world = context.world
    observation_id = None
    character = Character(world.world_id, command.character_id, command.name)
    if await uow.characters.get(character.character_id) is not None:
        raise EntityAlreadyExistsError("Character already exists")
    events = [
        (
            "CharacterCreated",
            {
                "character_id": str(character.character_id.value),
                "name": character.name,
                "revision": 0,
            },
        )
    ]
    reference, revision = (character.character_id, character.revision)

    async def apply() -> None:
        await uow.characters.add(character)

    return CommandMutation(events, reference, revision, apply, observation_id)


async def place_character(context: MutationContext, command: PlaceCharacter) -> CommandMutation:
    uow = context.uow
    world = context.world
    now = context.now
    logical_time = context.logical_time
    observation_id = None
    same_world(world.world_id, command.character_id, command.location_id)
    if command.activity_player_id is not None:
        if command.activity_configure:
            await uow.local_locations.check_character_config(
                command.character_id,
                command.location_id,
                command.activity_player_id,
                command.expected_location_policy_revision,
            )
        else:
            await uow.local_locations.check_initial_activity(
                command.character_id, command.location_id, command.activity_player_id
            )
    if await uow.characters.get(command.character_id) is None:
        raise EntityNotFoundError("Character does not exist")
    await context.location(command.location_id)
    before = await uow.characters.state(command.character_id)
    expect_revision(
        "CharacterState",
        command.character_id,
        before.revision if before else None,
        command.expected_state_revision,
    )
    destination = command.location_id
    if command.activity_configure:
        destination = await uow.local_locations.config_destination(
            command.character_id, command.location_id, command.activity_locked, before
        )
        if before and destination == before.location_id:

            async def apply_config() -> None:
                await uow.local_locations.configure_character(
                    command.character_id,
                    command.location_id,
                    command.activity_locked,
                    command.activity_residency,
                    logical_time.microseconds,
                )

            return CommandMutation(
                [
                    (
                        "CharacterLocationConfigured",
                        {
                            "character_id": str(command.character_id.value),
                            "initial_location_id": str(command.location_id.value),
                            "locked": command.activity_locked,
                            "revision": before.revision.value,
                        },
                    )
                ],
                command.character_id,
                before.revision,
                apply_config,
            )
    if before is not None:
        await settle_routines(
            uow, world.world_id, logical_time, now, character=command.character_id, interrupt=True
        )
    revision = before.revision.advance(before.revision) if before else Revision()
    state = CharacterState(world.world_id, command.character_id, destination, revision)
    events = [
        (
            "CharacterPlaced",
            {
                "character_id": str(state.character_id.value),
                "before_location_id": str(before.location_id.value) if before else None,
                "location_id": str(state.location_id.value),
                "revision": revision.value,
            },
        )
    ]
    reference = state.character_id

    async def apply() -> None:
        await uow.characters.put_state(state, command.expected_state_revision)
        if command.activity_player_id is not None:
            await uow.local_locations.configure_character(
                command.character_id,
                command.location_id,
                command.activity_locked,
                command.activity_residency,
                logical_time.microseconds,
            )
            await uow.observations.add(
                Observation(
                    world.world_id,
                    state.character_id,
                    event_identity(command, 0),
                    ObservationChannel.WITNESSED,
                    logical_time,
                    now,
                    observation_id=ObservationId(world.world_id, uuid4()),
                    basis=ObservationBasis.EVENT_OCCURRENCE,
                )
            )
        if before is not None and before.location_id != state.location_id:
            await uow.scenes.leave_active_for_principal(state.character_id, logical_time)

    return CommandMutation(events, reference, revision, apply, observation_id)
