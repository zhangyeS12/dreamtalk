"""Deterministic validation and canonical mutation; no ORM or business HTTP API."""

from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import datetime
from uuid import uuid5

from livingworld.application.commands import (
    ChangeRelationship,
    CreateCharacter,
    CreateLocation,
    CreatePlayer,
    CreateWorld,
    MovePlayer,
    PlaceCharacter,
    WorldCommand,
)
from livingworld.application.errors import EntityAlreadyExistsError, EntityNotFoundError
from livingworld.application.fingerprints import command_fingerprint, id_input
from livingworld.application.ports import UnitOfWork, WallClock
from livingworld.application.results import CommandResult, EntityReference, RelationshipReference
from livingworld.domain.commands import CommandReceipt
from livingworld.domain.events import WorldEvent
from livingworld.domain.identifiers import CharacterId, CorrelationId, EventId, LocationId
from livingworld.domain.participants import Character, CharacterState, Player, PlayerPresence
from livingworld.domain.relationships import Relationship, RelationshipMetrics
from livingworld.domain.values import Revision, WorldTime, same_world, utc_timestamp
from livingworld.domain.world import Location, World, WorldClock

EVENT_PAYLOAD_VERSION = 1


def metrics_payload(metrics: RelationshipMetrics) -> dict[str, int]:
    return {
        "affinity": metrics.affinity,
        "trust": metrics.trust,
        "familiarity": metrics.familiarity,
    }


class CommandHandler:
    def __init__(self, uow_factory: Callable[[], UnitOfWork], clock: WallClock):
        self._uow_factory = uow_factory
        self._clock = clock

    async def execute(self, command: WorldCommand) -> CommandResult:
        fingerprint = command_fingerprint(command)
        async with self._uow_factory() as uow:
            existing = await uow.receipts.existing(command.request_id, fingerprint)
            if existing is not None:
                return replace(existing, replayed=True)
            now = utc_timestamp(self._clock.now_utc(), "application wall clock")
            if isinstance(command, CreateWorld):
                if await uow.worlds.get(command.world_id) is not None:
                    raise EntityAlreadyExistsError("World already exists")
                clock = WorldClock(
                    command.world_id,
                    command.initial_time,
                    now,
                    command.time_scale,
                    command.clock_state,
                )
                world = World(command.world_id, command.name, clock)
                # Events reference worlds by FK: stage the world in this SAME transaction first.
                await uow.worlds.add(world)

                return await self._finish(
                    uow,
                    command,
                    fingerprint,
                    now,
                    clock.logical_time,
                    [
                        (
                            "WorldCreated",
                            {
                                "world_id": str(world.world_id.value),
                                "name": world.name,
                                "logical_time": clock.logical_time.microseconds,
                                "observed_wall_time_utc": now.isoformat(),
                                "time_scale": str(clock.time_scale),
                                "clock_state": clock.state.value,
                                "world_revision": world.revision.value,
                                "clock_revision": clock.revision.value,
                            },
                        )
                    ],
                    world.world_id,
                    world.revision,
                    None,
                )
            world = await uow.worlds.get(command.world_id)
            if world is None:
                raise EntityNotFoundError("World does not exist")
            return await self._mutate(uow, command, fingerprint, now, world)

    async def _location(self, uow: UnitOfWork, world: World, identity: LocationId) -> Location:
        same_world(world.world_id, identity)
        location = await uow.locations.get(identity)
        if location is None:
            raise EntityNotFoundError("Location does not exist")
        return location

    async def _mutate(
        self, uow: UnitOfWork, command: WorldCommand, fingerprint: str, now: datetime, world: World
    ) -> CommandResult:
        match command:
            case CreateLocation():
                location = Location(world.world_id, command.location_id, command.name)
                if await uow.locations.get(location.location_id) is not None:
                    raise EntityAlreadyExistsError("Location already exists")
                events = [
                    (
                        "LocationCreated",
                        {
                            "location_id": str(location.location_id.value),
                            "name": location.name,
                            "revision": 0,
                        },
                    )
                ]
                reference, revision = location.location_id, location.revision

                async def apply() -> None:
                    await uow.locations.add(location)

            case CreatePlayer():
                player = Player(world.world_id, command.player_id, command.name)
                await self._location(uow, world, command.initial_location_id)
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
                        {
                            "player_id": str(player.player_id.value),
                            "name": player.name,
                            "revision": 0,
                        },
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
                reference, revision = player.player_id, presence.revision

                async def apply() -> None:
                    await uow.players.add(player, presence)

            case MovePlayer():
                same_world(world.world_id, command.player_id, command.destination_id)
                if await uow.players.get(command.player_id) is None:
                    raise EntityNotFoundError("Player does not exist")
                await self._location(uow, world, command.destination_id)
                before = await uow.players.presence(command.player_id)
                if before is None:
                    raise EntityNotFoundError("PlayerPresence does not exist")
                after = before.at_location(
                    command.destination_id, expected_revision=before.revision
                )
                events = [
                    (
                        "PlayerMoved",
                        {
                            "player_id": str(after.player_id.value),
                            "from_location_id": str(before.location_id.value),
                            "to_location_id": str(after.location_id.value),
                            "activity": after.activity.value,
                            "availability": after.availability.value,
                            "revision": after.revision.value,
                        },
                    )
                ]
                reference, revision = after.player_id, after.revision

                async def apply() -> None:
                    await uow.players.replace_presence(after)

            case CreateCharacter():
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
                reference, revision = character.character_id, character.revision

                async def apply() -> None:
                    await uow.characters.add(character)

            case PlaceCharacter():
                same_world(world.world_id, command.character_id, command.location_id)
                if await uow.characters.get(command.character_id) is None:
                    raise EntityNotFoundError("Character does not exist")
                await self._location(uow, world, command.location_id)
                before = await uow.characters.state(command.character_id)
                revision = before.revision.advance(before.revision) if before else Revision()
                state = CharacterState(
                    world.world_id, command.character_id, command.location_id, revision
                )
                events = [
                    (
                        "CharacterPlaced",
                        {
                            "character_id": str(state.character_id.value),
                            "before_location_id": (
                                str(before.location_id.value) if before else None
                            ),
                            "location_id": str(state.location_id.value),
                            "revision": revision.value,
                        },
                    )
                ]
                reference = state.character_id

                async def apply() -> None:
                    await uow.characters.put_state(state)

            case ChangeRelationship():
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
                initial = before or Relationship(
                    world.world_id, command.source_id, command.target_id
                )
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
                            "source_character_id": (
                                str(after.source_id.value)
                                if isinstance(after.source_id, CharacterId)
                                else None
                            ),
                            "target_character_id": (
                                str(after.target_id.value)
                                if isinstance(after.target_id, CharacterId)
                                else None
                            ),
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
                    await uow.relationships.put(after)

            case _:
                raise TypeError("Unsupported command type")
        return await self._finish(
            uow,
            command,
            fingerprint,
            now,
            world.clock.logical_time,
            events,
            reference,
            revision,
            apply,
        )

    async def _finish(
        self,
        uow: UnitOfWork,
        command: WorldCommand,
        fingerprint: str,
        now: datetime,
        logical_time: WorldTime,
        events: list[tuple[str, dict]],
        reference: EntityReference,
        revision: Revision,
        apply: Callable[[], Awaitable[None]] | None,
    ) -> CommandResult:
        event_ids = []
        for ordinal, (event_type, payload) in enumerate(events):
            event_id = EventId(
                command.world_id,
                uuid5(command.request_id.value, f"livingworld:{command.world_id.value}:{ordinal}"),
            )
            event_ids.append(event_id)
            await uow.events.append(
                WorldEvent(
                    event_id,
                    command.world_id,
                    event_type,
                    logical_time,
                    payload,
                    EVENT_PAYLOAD_VERSION,
                    now,
                    command.request_id,
                    CorrelationId(command.request_id.value),
                    f"{command.request_id}:{ordinal}",
                )
            )
        if apply is not None:
            await apply()
        result = CommandResult(command.request_id, type(command).__name__, reference, revision)
        receipt = CommandReceipt(
            command.request_id,
            command.world_id,
            type(command).__name__,
            "committed",
            now,
            now,
            event_ids[-1],
        )
        await uow.receipts.add(receipt, fingerprint, result)
        await uow.commit()
        return result
