"""Deterministic validation and canonical mutation; no ORM or business HTTP API."""

from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import datetime

from livingworld.application.action_resolution import ActionResolutionService
from livingworld.application.command_knowledge import (
    acquire_knowledge,
    assert_world_truth,
    form_character_belief,
)
from livingworld.application.command_locations import configure_location, create_location
from livingworld.application.command_mutation import MutationContext
from livingworld.application.command_participants import (
    create_character,
    create_player,
    place_character,
    set_player_availability,
)
from livingworld.application.command_relationships import change_relationship
from livingworld.application.command_support import EVENT_PAYLOAD_VERSION, event_identity
from livingworld.application.commands import (
    AcquireKnowledge,
    AssertWorldTruth,
    ChangeRelationship,
    ConfigureLocation,
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
from livingworld.application.fingerprints import command_fingerprint
from livingworld.application.idempotency import run_with_receipt_recovery
from livingworld.application.ports import (
    TemporalMutationBarrier,
    UnitOfWork,
    WallClock,
    WorldRuntimeRegistrar,
    WorldTimeSource,
)
from livingworld.application.results import CommandResult, EntityReference
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
    CorrelationId,
    ObservationId,
)
from livingworld.domain.values import Revision, WorldTime, utc_timestamp
from livingworld.domain.world import World, WorldClock


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
        result = await run_with_receipt_recovery(
            lambda: self._transaction(command, fingerprint),
            self._uow_factory,
            lambda uow: uow.receipts.existing(command.request_id, fingerprint),
            (ConcurrencyConflictError, EntityAlreadyExistsError, IdempotencyConflictError),
        )
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

    async def _mutate(
        self,
        uow: UnitOfWork,
        command: WorldCommand,
        fingerprint: str,
        now: datetime,
        world: World,
        logical_time: WorldTime,
    ) -> CommandResult:
        context = MutationContext(uow, world, now, logical_time)
        match command:
            case CreateLocation():
                mutation = await create_location(context, command)
            case ConfigureLocation():
                mutation = await configure_location(context, command)
            case CreatePlayer():
                mutation = await create_player(context, command)
            case SetPlayerAvailability():
                mutation = await set_player_availability(context, command)
            case CreateCharacter():
                mutation = await create_character(context, command)
            case PlaceCharacter():
                mutation = await place_character(context, command)
            case ChangeRelationship():
                mutation = await change_relationship(context, command)
            case FormCharacterBelief():
                mutation = await form_character_belief(context, command)
            case AssertWorldTruth():
                mutation = await assert_world_truth(context, command)
            case AcquireKnowledge():
                mutation = await acquire_knowledge(context, command)
            case _:
                raise TypeError("Unsupported command type")
        return await self._finish(
            uow,
            command,
            fingerprint,
            now,
            logical_time,
            mutation.events,
            mutation.reference,
            mutation.revision,
            mutation.apply,
            mutation.observation_id,
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
