"""Deterministic validation and canonical mutation; no ORM or business HTTP API."""

from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import datetime
from uuid import uuid4, uuid5

from livingworld.application.action_resolution import ActionResolutionService
from livingworld.application.commands import (
    AcquireKnowledge,
    AssertWorldTruth,
    ChangeRelationship,
    CreateCharacter,
    CreateLocation,
    CreatePlayer,
    CreateWorld,
    FormCharacterBelief,
    MovePlayer,
    PlaceCharacter,
    SetPlayerAvailability,
    WorldCommand,
)
from livingworld.application.errors import (
    EntityAlreadyExistsError,
    EntityNotFoundError,
    IdempotencyConflictError,
)
from livingworld.application.fingerprints import command_fingerprint, decimal_input, id_input
from livingworld.application.ports import (
    TemporalMutationBarrier,
    UnitOfWork,
    WallClock,
    WorldRuntimeRegistrar,
    WorldTimeSource,
)
from livingworld.application.results import CommandResult, EntityReference, RelationshipReference
from livingworld.application.routine_lifecycle import settle_routines
from livingworld.domain.actions import (
    ActionKind,
    ActionProposal,
    ActionProposer,
    ActionRejectionReason,
    ActionResolutionStatus,
    MovePlayerPayload,
    ProposerKind,
)
from livingworld.domain.commands import CommandReceipt
from livingworld.domain.errors import ConcurrencyConflictError, DomainInvariantError
from livingworld.domain.events import WorldEvent
from livingworld.domain.identifiers import (
    CharacterId,
    CorrelationId,
    EventId,
    LocationId,
    ObservationId,
)
from livingworld.domain.knowledge import (
    KnowledgeAssertion,
    KnowledgeScope,
    Observation,
    ObservationChannel,
)
from livingworld.domain.participants import Character, CharacterState, Player, PlayerPresence
from livingworld.domain.relationships import Relationship, RelationshipMetrics
from livingworld.domain.values import Revision, WorldTime, same_world, utc_timestamp
from livingworld.domain.world import Location, World, WorldClock

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


class CommandHandler:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        clock: WallClock,
        *,
        world_time_source: WorldTimeSource,
        mutation_barrier: TemporalMutationBarrier | None = None,
        wake_signal=None,
        activation_planner=None,
        world_runtime_registrar: WorldRuntimeRegistrar | None = None,
    ):
        self._uow_factory = uow_factory
        self._clock = clock
        self._world_time_source = world_time_source
        self._mutation_barrier = mutation_barrier
        self._world_runtime_registrar = world_runtime_registrar
        self._actions = ActionResolutionService(
            uow_factory,
            clock,
            wake_signal,
            activation_planner,
            world_time_source=world_time_source,
            mutation_barrier=mutation_barrier,
        )

    async def execute(self, command: WorldCommand) -> CommandResult:
        if isinstance(command, MovePlayer):
            return await self._execute_legacy_move(command)
        if self._mutation_barrier is not None and not isinstance(command, CreateWorld):
            await self._mutation_barrier.assert_mutation_allowed(command.world_id)
        fingerprint = command_fingerprint(command)
        try:
            result = await self._transaction(command, fingerprint)
        except (ConcurrencyConflictError, EntityAlreadyExistsError, IdempotencyConflictError):
            # The failed UoW has exited/rolled back. Resolve a possible committed duplicate
            # exactly once from a fresh transaction; NEVER execute the mutation again.
            async with self._uow_factory() as uow:
                existing = await uow.receipts.existing(command.request_id, fingerprint)
            if existing is None:
                raise
            result = replace(existing, replayed=True)
        if isinstance(command, CreateWorld) and self._world_runtime_registrar is not None:
            await self._world_runtime_registrar.register_world(command.world_id)
        return result

    async def _execute_legacy_move(self, command: MovePlayer) -> CommandResult:
        """Adapt the compatibility command to the sole fictional-action commit path."""

        proposal = ActionProposal(
            command.world_id,
            ActionKind.MOVE_PLAYER,
            1,
            ActionProposer(ProposerKind.PLAYER_INPUT, command.player_id),
            command.player_id,
            MovePlayerPayload(command.destination_id, command.expected_presence_revision),
        )
        try:
            result = await self._actions.execute(command.request_id, proposal)
        except IdempotencyConflictError as action_conflict:
            # Databases created before Q-001A may contain the old result-v1 MovePlayer
            # receipt. Preserve exact historical retries without executing either path.
            try:
                async with self._uow_factory() as uow:
                    existing = await uow.receipts.existing(
                        command.request_id, command_fingerprint(command)
                    )
            except IdempotencyConflictError:
                raise action_conflict from None
            if existing is not None:
                return replace(existing, replayed=True)
            raise action_conflict from None
        if result.status is ActionResolutionStatus.REJECTED:
            await self._raise_legacy_move_rejection(command, result.reason)
        if result.resulting_revision is None:
            raise DomainInvariantError("Accepted player movement requires a resulting revision")
        return CommandResult(
            command.request_id,
            type(command).__name__,
            command.player_id,
            result.resulting_revision,
            replayed=result.replayed,
        )

    async def _raise_legacy_move_rejection(
        self, command: MovePlayer, reason: ActionRejectionReason | None
    ) -> None:
        if reason is ActionRejectionReason.PRECONDITION_FAILED:
            async with self._uow_factory() as uow:
                presence = await uow.players.presence(command.player_id)
            raise ConcurrencyConflictError(
                "PlayerPresence does not match expected revision",
                resource_kind="PlayerPresence",
                resource_identity=command.player_id,
                expected_revision=command.expected_presence_revision,
                actual_revision=presence.revision if presence is not None else None,
            )
        if reason in {
            ActionRejectionReason.NOT_PRESENT,
            ActionRejectionReason.INVALID_DESTINATION,
        }:
            raise EntityNotFoundError("Player movement references unavailable state")
        label = reason.value if reason is not None else "unknown"
        raise DomainInvariantError(f"Player movement rejected: {label}")

    async def _transaction(self, command: WorldCommand, fingerprint: str) -> CommandResult:
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
            logical_time = self._world_time_source.read(world.clock)
            return await self._mutate(uow, command, fingerprint, now, world, logical_time)

    async def _location(self, uow: UnitOfWork, world: World, identity: LocationId) -> Location:
        same_world(world.world_id, identity)
        location = await uow.locations.get(identity)
        if location is None:
            raise EntityNotFoundError("Location does not exist")
        return location

    async def _mutate(
        self,
        uow: UnitOfWork,
        command: WorldCommand,
        fingerprint: str,
        now: datetime,
        world: World,
        logical_time: WorldTime,
    ) -> CommandResult:
        observation_id = None
        match command:
            case CreateLocation():
                location = Location(world.world_id, command.location_id, command.name)
                if await uow.locations.get(location.location_id) is not None:
                    raise EntityAlreadyExistsError("Location already exists")
                if command.list_locally:
                    await uow.local_locations.check_new(command.world_id, command.name)
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
                    if command.list_locally:
                        await uow.local_locations.add(location.location_id, command.name)

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

            case SetPlayerAvailability():
                player = await uow.players.get(command.player_id)
                before = await uow.players.presence(command.player_id)
                if player is None or before is None:
                    raise EntityNotFoundError("Player does not exist")
                expect_revision(
                    "PlayerPresence",
                    command.player_id,
                    before.revision,
                    command.expected_presence_revision,
                )
                if before.availability is command.availability_state:
                    raise DomainInvariantError("Player availability is already set")
                after = before.with_availability(
                    command.availability_state,
                    expected_revision=command.expected_presence_revision,
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
                reference, revision = after.player_id, after.revision

                async def apply() -> None:
                    await uow.players.replace_presence(after, command.expected_presence_revision)

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
                if command.activity_player_id is not None:
                    await uow.local_locations.check_initial_activity(
                        command.character_id, command.location_id, command.activity_player_id
                    )
                if await uow.characters.get(command.character_id) is None:
                    raise EntityNotFoundError("Character does not exist")
                await self._location(uow, world, command.location_id)
                before = await uow.characters.state(command.character_id)
                expect_revision(
                    "CharacterState",
                    command.character_id,
                    before.revision if before else None,
                    command.expected_state_revision,
                )
                if before is not None:
                    await settle_routines(
                        uow,
                        world.world_id,
                        logical_time,
                        now,
                        character=command.character_id,
                        interrupt=True,
                    )
                revision = (
                    before.revision.advance(command.expected_state_revision)
                    if before
                    else Revision()
                )
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
                    await uow.characters.put_state(state, command.expected_state_revision)
                    if before is not None and before.location_id != state.location_id:
                        await uow.scenes.leave_active_for_principal(
                            state.character_id, logical_time
                        )

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
                expect_revision(
                    "Relationship",
                    RelationshipReference(command.source_id, command.target_id),
                    before.revision if before else None,
                    command.expected_relationship_revision,
                )
                initial = before or Relationship(
                    world.world_id, command.source_id, command.target_id
                )
                after = initial.change(
                    command.affinity_delta,
                    command.trust_delta,
                    command.familiarity_delta,
                    expected_revision=(
                        command.expected_relationship_revision if before else initial.revision
                    ),
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
                    await uow.relationships.put(after, command.expected_relationship_revision)

            case FormCharacterBelief():
                if await uow.characters.get(command.character_id) is None:
                    raise EntityNotFoundError("Belief owner does not exist")
                if await uow.knowledge.get(command.assertion_id) is not None:
                    raise EntityAlreadyExistsError("KnowledgeAssertion already exists")
                if (
                    command.source_assertion_id is not None
                    and await uow.knowledge.get(command.source_assertion_id) is None
                ):
                    raise EntityNotFoundError("Source KnowledgeAssertion does not exist")
                if (
                    command.provenance_event_id is not None
                    and not await uow.event_references.exists(command.provenance_event_id)
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
                reference, revision = assertion.assertion_id, assertion.revision

                async def apply() -> None:
                    await uow.knowledge.add(assertion)

            case AssertWorldTruth():
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
                reference, revision = assertion.assertion_id, assertion.revision

                async def apply() -> None:
                    await uow.knowledge.add(assertion)

            case AcquireKnowledge():
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
                # Occurrence identity is independent of RequestId and all semantic coordinates.
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
                reference, revision = assertion.assertion_id, assertion.revision

                async def apply() -> None:
                    await uow.observations.add(observation)
                    await uow.knowledge.add(assertion)

            case _:
                raise TypeError("Unsupported command type")
        return await self._finish(
            uow,
            command,
            fingerprint,
            now,
            logical_time,
            events,
            reference,
            revision,
            apply,
            observation_id,
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
        observation_id: ObservationId | None = None,
    ) -> CommandResult:
        event_ids = []
        for ordinal, (event_type, payload) in enumerate(events):
            event_id = event_identity(command, ordinal)
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
        result = CommandResult(
            command.request_id,
            type(command).__name__,
            reference,
            revision,
            observation_id=observation_id,
        )
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
