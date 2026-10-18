"""Locations command validation and projection writes; the caller owns commit."""

from dataclasses import replace

from livingworld.application.command_mutation import CommandMutation, MutationContext
from livingworld.application.command_support import expect_revision
from livingworld.application.commands import (
    ConfigureLocation,
    CreateLocation,
)
from livingworld.application.errors import (
    EntityAlreadyExistsError,
)
from livingworld.domain.world import Location


async def create_location(context: MutationContext, command: CreateLocation) -> CommandMutation:
    uow = context.uow
    world = context.world
    observation_id = None
    location = Location(world.world_id, command.location_id, command.name)
    if await uow.locations.get(location.location_id) is not None:
        raise EntityAlreadyExistsError("Location already exists")
    if command.list_locally:
        await uow.local_locations.check_new(command.world_id, command.name, command.parent_id)
        await uow.local_locations.check_options(
            command.location_id, command.parent_id, command.hidden, command.allowed_characters
        )
    events = [
        (
            "LocationCreated",
            {"location_id": str(location.location_id.value), "name": location.name, "revision": 0},
        )
    ]
    reference, revision = (location.location_id, location.revision)

    async def apply() -> None:
        await uow.locations.add(location)
        if command.list_locally:
            await uow.local_locations.add(location.location_id, command.name, command.parent_id)
            await uow.local_locations.configure(
                location.location_id,
                command.name,
                command.parent_id,
                command.hidden,
                command.allowed_characters,
                command.is_region,
            )

    return CommandMutation(events, reference, revision, apply, observation_id)


async def configure_location(
    context: MutationContext, command: ConfigureLocation
) -> CommandMutation:
    uow = context.uow
    observation_id = None
    before = await context.location(command.location_id)
    expect_revision("Location", command.location_id, before.revision, command.expected_revision)
    await uow.local_locations.check_edit(command.location_id, command.name, command.parent_id)
    await uow.local_locations.check_options(
        command.location_id, command.parent_id, command.hidden, command.allowed_characters
    )
    after = replace(
        before, name=command.name, revision=before.revision.advance(command.expected_revision)
    )
    events = [
        (
            "LocationUpdated",
            {
                "location_id": str(after.location_id.value),
                "before_name": before.name,
                "name": after.name,
                "revision": after.revision.value,
            },
        )
    ]
    reference, revision = (after.location_id, after.revision)

    async def apply() -> None:
        await uow.locations.replace(after, command.expected_revision)
        await uow.local_locations.configure(
            after.location_id,
            command.name,
            command.parent_id,
            command.hidden,
            command.allowed_characters,
            command.is_region,
        )

    return CommandMutation(events, reference, revision, apply, observation_id)
