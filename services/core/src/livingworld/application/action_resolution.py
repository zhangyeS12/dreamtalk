"""Deterministic action registry, authority checks and atomic kernel commit."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from hashlib import sha256
from uuid import uuid4, uuid5

from livingworld.application.activation import ActivationPlanner
from livingworld.application.errors import (
    ActivationFanoutTooLargeError,
    EntityNotFoundError,
    IdempotencyConflictError,
)
from livingworld.application.fingerprints import canonical_json, id_input
from livingworld.application.player_movement import (
    apply_player_movement,
    player_moved_payload,
    resolve_player_movement,
)
from livingworld.application.ports import (
    TemporalMutationBarrier,
    UnitOfWork,
    WallClock,
    WorldTimeSource,
)
from livingworld.application.results import ActionResult
from livingworld.domain.actions import (
    ActionKind,
    ActionProposal,
    ActionRejectionReason,
    ActionResolutionStatus,
    AudienceSelector,
    AudienceSelectorKind,
    MovePlayerPayload,
    PerceptionAudience,
    ProposerKind,
)
from livingworld.domain.commands import CommandReceipt
from livingworld.domain.contracts import RequestId
from livingworld.domain.events import WorldEvent
from livingworld.domain.identifiers import (
    CorrelationId,
    EventId,
    ObservationId,
    PlayerId,
    PrincipalId,
)
from livingworld.domain.knowledge import Observation, ObservationBasis, ObservationChannel
from livingworld.domain.participants import PlayerPresence
from livingworld.domain.scenes import SceneStatus
from livingworld.domain.simulation import EventWakeKind, EventWakeSpec, TriggerPriority
from livingworld.domain.values import utc_timestamp

EVENT_PAYLOAD_VERSION = 1


def _identity(value):
    return id_input(value) if value is not None else None


def action_fingerprint(proposal: ActionProposal) -> str:
    payload = proposal.payload
    semantic = {
        "fingerprint_version": 1,
        "command_type": "ResolveAction",
        "world_id": _identity(proposal.world_id),
        "kind": proposal.kind.value,
        "schema_version": proposal.schema_version,
        "proposer": {
            "kind": proposal.proposer.kind.value,
            "principal_id": _identity(proposal.proposer.principal_id),
        },
        "actor_id": _identity(proposal.actor_id),
        "scene_id": _identity(proposal.scene_id),
        "source_activation_id": _identity(proposal.source_activation_id),
        "causation_id": _identity(proposal.causation_id),
        "correlation_id": str(proposal.correlation_id.value)
        if proposal.correlation_id is not None
        else None,
        "payload": {
            "destination_id": _identity(payload.destination_id),
            "expected_presence_revision": payload.expected_presence_revision.value,
        },
    }
    return sha256(canonical_json(semantic).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class _AcceptedMove:
    before: PlayerPresence
    after: PlayerPresence
    audience: PerceptionAudience
    wake: EventWakeSpec


class AudienceResolver:
    """Resolve only indexed, typed selectors against transaction-local canonical state."""

    async def resolve(
        self,
        uow: UnitOfWork,
        audience: PerceptionAudience,
        *,
        actor_id: PrincipalId | None,
        world_id,
    ) -> tuple[PrincipalId, ...]:
        resolved: set[PrincipalId] = set()
        for selector in audience.selectors:
            if selector.kind is AudienceSelectorKind.NONE:
                continue
            if selector.kind is AudienceSelectorKind.ACTOR_ONLY:
                if actor_id is not None:
                    resolved.add(actor_id)
                continue
            if selector.kind is AudienceSelectorKind.SCENE_PARTICIPANTS:
                scene = await uow.scenes.get(selector.scene_id)
                if (
                    scene is None
                    or scene.world_id != world_id
                    or scene.status is not SceneStatus.OPEN
                ):
                    raise EntityNotFoundError("Audience Scene is not open in this World")
                resolved.update(
                    participant.principal_id
                    for participant in await uow.scenes.active_participants(selector.scene_id)
                )
                continue
            if selector.kind is AudienceSelectorKind.LOCATION_PRESENT:
                if selector.location_id.world_id != world_id:
                    raise EntityNotFoundError("Audience Location belongs to another World")
                resolved.update(await uow.players.at_location(selector.location_id))
                resolved.update(await uow.characters.at_location(selector.location_id))
                continue
            for principal in selector.principals:
                if principal.world_id != world_id:
                    raise EntityNotFoundError(
                        "Explicit audience principal belongs to another World"
                    )
                exists = (
                    await uow.players.get(principal)
                    if isinstance(principal, PlayerId)
                    else await uow.characters.get(principal)
                )
                if exists is None:
                    raise EntityNotFoundError("Explicit audience principal does not exist")
                resolved.add(principal)
        return tuple(sorted(resolved, key=lambda value: (type(value).__name__, value.value.hex)))


type ResolverResult = tuple[ActionRejectionReason | None, _AcceptedMove | None]
type Resolver = Callable[[UnitOfWork, ActionProposal], Awaitable[ResolverResult]]


class ActionKindRegistry:
    """Closed, typed allowlist; payloads cannot select code or module paths."""

    def __init__(self, resolvers: dict[tuple[ActionKind, int], Resolver]):
        self._resolvers = dict(resolvers)

    def get(self, kind: ActionKind, version: int) -> Resolver | None:
        return self._resolvers.get((kind, version))


class ActionResolutionService:
    def __init__(
        self,
        uow_factory,
        clock: WallClock,
        wake_signal=None,
        activation_planner=None,
        *,
        world_time_source: WorldTimeSource,
        mutation_barrier: TemporalMutationBarrier | None = None,
    ):
        self._uow_factory = uow_factory
        self._clock = clock
        self._world_time_source = world_time_source
        self._mutation_barrier = mutation_barrier
        self._wake_signal = wake_signal
        self._audiences = AudienceResolver()
        self._activations = activation_planner or ActivationPlanner()
        self._registry = ActionKindRegistry({(ActionKind.MOVE_PLAYER, 1): self._resolve_move})

    async def execute(self, request_id: RequestId, proposal: ActionProposal) -> ActionResult:
        if self._mutation_barrier is not None:
            await self._mutation_barrier.assert_mutation_allowed(proposal.world_id)
        fingerprint = action_fingerprint(proposal)
        try:
            return await self._execute(request_id, proposal, fingerprint)
        except IdempotencyConflictError:
            async with self._uow_factory() as uow:
                existing = await uow.receipts.existing_action(request_id, fingerprint)
                if existing is not None:
                    return replace(existing, replayed=True)
            raise

    async def _execute(
        self, request_id: RequestId, proposal: ActionProposal, fingerprint: str
    ) -> ActionResult:
        async with self._uow_factory() as uow:
            existing = await uow.receipts.existing_action(request_id, fingerprint)
            if existing is not None:
                return replace(existing, replayed=True)
            now = utc_timestamp(self._clock.now_utc(), "application wall clock")
            world = await uow.worlds.get(proposal.world_id)
            if world is None:
                raise EntityNotFoundError("World does not exist")
            occurred_at = self._world_time_source.read(world.clock)
            resolver = self._registry.get(proposal.kind, proposal.schema_version)
            rejected, accepted = (
                (ActionRejectionReason.UNSUPPORTED_ACTION, None)
                if resolver is None
                else await resolver(uow, proposal)
            )
            if rejected is not None:
                return await self._commit_rejection(
                    uow, request_id, proposal, fingerprint, rejected, now
                )

            assert accepted is not None
            event_id = EventId(
                proposal.world_id,
                uuid5(request_id.value, f"livingworld:action:{proposal.world_id.value}:0"),
            )
            payload = player_moved_payload(accepted.before, accepted.after)
            payload["source_activation_id"] = (
                str(proposal.source_activation_id.value)
                if proposal.source_activation_id is not None
                else None
            )
            event = WorldEvent(
                event_id,
                proposal.world_id,
                "PlayerMoved",
                occurred_at,
                payload,
                EVENT_PAYLOAD_VERSION,
                now,
                proposal.causation_id or request_id,
                proposal.correlation_id or CorrelationId(request_id.value),
                f"{request_id}:action:0",
            )
            observers = await self._audiences.resolve(
                uow,
                accepted.audience,
                actor_id=proposal.actor_id,
                world_id=proposal.world_id,
            )
            try:
                wake_targets = await self._activations.wakes.resolve(
                    uow,
                    accepted.wake,
                    actor_id=proposal.actor_id,
                    world_id=proposal.world_id,
                )
            except ActivationFanoutTooLargeError:
                return await self._commit_rejection(
                    uow,
                    request_id,
                    proposal,
                    fingerprint,
                    ActionRejectionReason.WAKE_FANOUT_TOO_LARGE,
                    now,
                )
            await uow.events.append(event)
            await apply_player_movement(
                uow,
                accepted.before,
                accepted.after,
                accepted.before.revision,
                occurred_at,
            )
            for observer in observers:
                await uow.observations.add(
                    Observation(
                        proposal.world_id,
                        observer,
                        event_id,
                        ObservationChannel.WITNESSED,
                        occurred_at,
                        now,
                        observation_id=ObservationId(proposal.world_id, uuid4()),
                        basis=ObservationBasis.EVENT_OCCURRENCE,
                    )
                )
            activation_results = await self._activations.materialize_event_targets(
                uow,
                wake_targets,
                world_id=proposal.world_id,
                event_id=event_id,
                due_at=occurred_at,
                priority=TriggerPriority.NORMAL,
                materialized_at_utc=now,
            )
            result = ActionResult(
                request_id,
                ActionResolutionStatus.ACCEPTED,
                None,
                (event_id,),
                accepted.after.revision,
            )
            receipt = CommandReceipt(
                request_id,
                proposal.world_id,
                "ResolveAction",
                "committed",
                now,
                now,
                event_id,
            )
            await uow.receipts.add_action(receipt, fingerprint, result)
            await uow.commit()
            if self._wake_signal is not None and any(
                item.schedule_changed for item in activation_results
            ):
                self._wake_signal.wake(proposal.world_id)
            return result

    @staticmethod
    async def _commit_rejection(
        uow,
        request_id: RequestId,
        proposal: ActionProposal,
        fingerprint: str,
        reason: ActionRejectionReason,
        now,
    ) -> ActionResult:
        result = ActionResult(
            request_id,
            ActionResolutionStatus.REJECTED,
            reason,
            (),
            None,
        )
        receipt = CommandReceipt(
            request_id,
            proposal.world_id,
            "ResolveAction",
            "rejected",
            now,
            now,
        )
        await uow.receipts.add_action(receipt, fingerprint, result)
        await uow.commit()
        return result

    async def _resolve_move(
        self, uow: UnitOfWork, proposal: ActionProposal
    ) -> tuple[ActionRejectionReason | None, _AcceptedMove | None]:
        if not isinstance(proposal.payload, MovePlayerPayload):
            return ActionRejectionReason.UNSUPPORTED_ACTION, None
        if not isinstance(proposal.actor_id, PlayerId):
            return ActionRejectionReason.UNAUTHORIZED_ACTOR, None
        if (
            proposal.proposer.kind is not ProposerKind.PLAYER_INPUT
            or proposal.proposer.principal_id != proposal.actor_id
        ):
            return ActionRejectionReason.UNAUTHORIZED_ACTOR, None
        actor = await uow.players.get(proposal.actor_id)
        before = await uow.players.presence(proposal.actor_id)
        if actor is None or before is None:
            return ActionRejectionReason.NOT_PRESENT, None
        if before.revision != proposal.payload.expected_presence_revision:
            return ActionRejectionReason.PRECONDITION_FAILED, None
        destination = await uow.locations.get(proposal.payload.destination_id)
        if destination is None or destination.world_id != proposal.world_id:
            return ActionRejectionReason.INVALID_DESTINATION, None
        if before.location_id == destination.location_id:
            return ActionRejectionReason.INVALID_DESTINATION, None
        if proposal.scene_id is not None:
            scene = await uow.scenes.get(proposal.scene_id)
            membership = await uow.scenes.active_for_principal(proposal.actor_id)
            if (
                scene is None
                or scene.status is not SceneStatus.OPEN
                or membership is None
                or membership.scene_id != scene.scene_id
                or scene.location_id != before.location_id
            ):
                return ActionRejectionReason.INVALID_SCENE, None
        after = resolve_player_movement(
            before,
            destination.location_id,
            proposal.payload.expected_presence_revision,
        )
        audience = PerceptionAudience(
            (
                AudienceSelector(AudienceSelectorKind.ACTOR_ONLY),
                AudienceSelector(
                    AudienceSelectorKind.LOCATION_PRESENT, location_id=before.location_id
                ),
                AudienceSelector(
                    AudienceSelectorKind.LOCATION_PRESENT, location_id=destination.location_id
                ),
            )
        )
        wake = (
            EventWakeSpec(
                EventWakeKind.SCENE_CHARACTER_PARTICIPANTS,
                scene_id=proposal.scene_id,
            )
            if proposal.scene_id is not None
            else EventWakeSpec()
        )
        return None, _AcceptedMove(before, after, audience, wake)
