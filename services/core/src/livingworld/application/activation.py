"""Sparse activation requests, bounded wake planning, and current fidelity selection."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256

from livingworld.application.errors import (
    ActivationAccessDeniedError,
    ActivationFanoutTooLargeError,
    EntityNotFoundError,
    UnsupportedActivationError,
)
from livingworld.application.fingerprints import canonical_json, id_input
from livingworld.application.ports import UnitOfWork, WallClock
from livingworld.application.scheduler import SchedulerWakeSignal
from livingworld.domain.contracts import RequestId
from livingworld.domain.identifiers import (
    ActivationId,
    CharacterId,
    EventId,
    PrincipalId,
    SceneId,
    WorldId,
)
from livingworld.domain.scenes import SceneStatus
from livingworld.domain.simulation import (
    ActivationAttention,
    ActivationCandidate,
    ActivationCause,
    ActivationCauseKind,
    ActivationCausePage,
    ActivationKind,
    ActivationRequest,
    ActivationRequestResult,
    ActivationTarget,
    ActivationTargetKind,
    EventWakeKind,
    EventWakeSpec,
    SceneActivityKind,
    TriggerPriority,
)
from livingworld.domain.values import WorldTime

DEFAULT_MAX_CHARACTER_FANOUT = 128


@dataclass(frozen=True, slots=True)
class ActivationKindContract:
    target_kind: ActivationTargetKind


class ActivationKindRegistry:
    """Allowlisted activation contracts; it never resolves persisted names to code."""

    def __init__(
        self,
        contracts: Mapping[tuple[ActivationKind, int], ActivationKindContract] | None = None,
    ) -> None:
        self._contracts = dict(
            contracts
            or {
                (ActivationKind.WORLD_ORCHESTRATION, 1): ActivationKindContract(
                    ActivationTargetKind.WORLD
                ),
                (ActivationKind.CHARACTER_REACTION, 1): ActivationKindContract(
                    ActivationTargetKind.CHARACTER
                ),
                (ActivationKind.CHARACTER_SCHEDULE_DUE, 1): ActivationKindContract(
                    ActivationTargetKind.CHARACTER
                ),
                (ActivationKind.SCENE_ACTIVITY, 1): ActivationKindContract(
                    ActivationTargetKind.CHARACTER
                ),
            }
        )

    @property
    def supported(self) -> frozenset[tuple[ActivationKind, int]]:
        return frozenset(self._contracts)

    def validate(self, request: ActivationRequest) -> None:
        contract = self._contracts.get((request.activation_kind, request.activation_version))
        if contract is None or contract.target_kind is not request.target.kind:
            raise UnsupportedActivationError(
                f"unsupported_activation:{request.activation_kind}:v{request.activation_version}:"
                f"{request.target.kind}"
            )


def activation_request_fingerprint(request: ActivationRequest) -> str:
    cause = request.cause
    semantic = {
        "fingerprint_version": 1,
        "world_id": id_input(request.world_id),
        "target": {
            "kind": request.target.kind.value,
            "character_id": (
                id_input(request.target.character_id)
                if request.target.character_id is not None
                else None
            ),
        },
        "activation_kind": request.activation_kind.value,
        "activation_version": request.activation_version,
        "cause": {
            "kind": cause.kind.value,
            "trigger_id": (
                id_input(cause.source_trigger_id) if cause.source_trigger_id is not None else None
            ),
            "event_id": (
                id_input(cause.source_event_id) if cause.source_event_id is not None else None
            ),
            "scene_id": (
                id_input(cause.source_scene_id) if cause.source_scene_id is not None else None
            ),
            "scene_activity": cause.scene_activity.value if cause.scene_activity else None,
            "request_id": (str(cause.source_request_id.value) if cause.source_request_id else None),
        },
        "due_at": request.due_at.microseconds,
        "priority": int(request.priority),
        "coalescing_key": request.coalescing_key,
        "attention": request.attention.value,
        "source_contract_kind": request.source_contract_kind,
        "source_contract_version": request.source_contract_version,
        "payload": request.payload.data,
    }
    return sha256(canonical_json(semantic).encode("utf-8")).hexdigest()


async def validate_activation_request(
    uow: UnitOfWork,
    request: ActivationRequest,
    registry: ActivationKindRegistry,
) -> None:
    registry.validate(request)
    if await uow.worlds.get(request.world_id) is None:
        raise EntityNotFoundError("Activation World does not exist")
    if request.target.kind is ActivationTargetKind.CHARACTER:
        character_id = request.target.character_id
        if await uow.characters.get(character_id) is None:
            raise EntityNotFoundError("Activation Character does not exist")
    cause = request.cause
    if cause.kind is ActivationCauseKind.WORLD_EVENT:
        if not await uow.event_references.exists(cause.source_event_id):
            raise EntityNotFoundError("Activation source WorldEvent does not exist")
        if (
            request.target.kind is ActivationTargetKind.CHARACTER
            and not await uow.observations.has_event_access(
                request.target.character_id, cause.source_event_id
            )
        ):
            raise ActivationAccessDeniedError(
                "Character cannot be activated from an unobserved event"
            )
    elif cause.kind is ActivationCauseKind.SCENE_ACTIVITY:
        scene = await uow.scenes.get(cause.source_scene_id)
        if scene is None:
            raise EntityNotFoundError("Activation source Scene does not exist")


class EventWakeResolver:
    """Resolve bounded wake targets independently from the perception audience."""

    def __init__(self, max_character_fanout: int = DEFAULT_MAX_CHARACTER_FANOUT) -> None:
        if type(max_character_fanout) is not int or max_character_fanout <= 0:
            raise ValueError("max_character_fanout must be positive")
        self._max = max_character_fanout

    async def resolve(
        self,
        uow: UnitOfWork,
        spec: EventWakeSpec,
        *,
        world_id: WorldId,
        actor_id: PrincipalId | None,
    ) -> tuple[ActivationTarget, ...]:
        if spec.kind is EventWakeKind.NONE:
            return ()
        if spec.kind is EventWakeKind.WORLD:
            return (ActivationTarget.world(world_id),)
        if spec.kind is EventWakeKind.ACTOR:
            return (
                (ActivationTarget.character(actor_id),) if isinstance(actor_id, CharacterId) else ()
            )
        if spec.kind is EventWakeKind.SCENE_CHARACTER_PARTICIPANTS:
            if spec.scene_id.world_id != world_id:
                raise EntityNotFoundError("Wake Scene belongs to another World")
            scene = await uow.scenes.get(spec.scene_id)
            if scene is None or scene.status is not SceneStatus.OPEN:
                raise EntityNotFoundError("Wake Scene is not open")
            characters, more = await uow.scenes.active_characters_bounded(spec.scene_id, self._max)
            if more:
                raise ActivationFanoutTooLargeError("scene_character_wake_fanout_too_large")
            return tuple(ActivationTarget.character(character) for character in characters)
        if len(spec.characters) > self._max:
            raise ActivationFanoutTooLargeError("explicit_character_wake_fanout_too_large")
        targets: list[ActivationTarget] = []
        for character_id in spec.characters:
            if character_id.world_id != world_id:
                raise EntityNotFoundError("Wake Character belongs to another World")
            if await uow.characters.get(character_id) is None:
                raise EntityNotFoundError("Wake Character does not exist")
            targets.append(ActivationTarget.character(character_id))
        return tuple(sorted(targets, key=lambda target: target.character_id.value.hex))


class ActivationPlanner:
    """Materialize typed sparse work inside an existing transaction."""

    def __init__(
        self,
        registry: ActivationKindRegistry | None = None,
        *,
        max_character_fanout: int = DEFAULT_MAX_CHARACTER_FANOUT,
    ) -> None:
        self.registry = registry or ActivationKindRegistry()
        self.wakes = EventWakeResolver(max_character_fanout)

    async def request(
        self,
        uow: UnitOfWork,
        request: ActivationRequest,
        materialized_at_utc: datetime,
    ) -> ActivationRequestResult:
        await validate_activation_request(uow, request, self.registry)
        return await uow.activations.request(
            request, activation_request_fingerprint(request), materialized_at_utc
        )

    async def materialize_event_wake(
        self,
        uow: UnitOfWork,
        spec: EventWakeSpec,
        *,
        world_id: WorldId,
        event_id: EventId,
        actor_id: PrincipalId | None,
        due_at: WorldTime,
        priority: TriggerPriority,
        materialized_at_utc: datetime,
    ) -> tuple[ActivationRequestResult, ...]:
        targets = await self.wakes.resolve(uow, spec, world_id=world_id, actor_id=actor_id)
        return await self.materialize_event_targets(
            uow,
            targets,
            world_id=world_id,
            event_id=event_id,
            due_at=due_at,
            priority=priority,
            materialized_at_utc=materialized_at_utc,
        )

    async def materialize_event_targets(
        self,
        uow: UnitOfWork,
        targets: tuple[ActivationTarget, ...],
        *,
        world_id: WorldId,
        event_id: EventId,
        due_at: WorldTime,
        priority: TriggerPriority,
        materialized_at_utc: datetime,
    ) -> tuple[ActivationRequestResult, ...]:
        results: list[ActivationRequestResult] = []
        for target in targets:
            is_world = target.kind is ActivationTargetKind.WORLD
            request = ActivationRequest(
                world_id=world_id,
                target=target,
                activation_kind=(
                    ActivationKind.WORLD_ORCHESTRATION
                    if is_world
                    else ActivationKind.CHARACTER_REACTION
                ),
                activation_version=1,
                cause=ActivationCause(
                    world_id, ActivationCauseKind.WORLD_EVENT, source_event_id=event_id
                ),
                due_at=due_at,
                priority=priority,
                coalescing_key=("world_orchestration" if is_world else "character_reaction"),
                attention=(ActivationAttention.NONE if is_world else ActivationAttention.ACTIVE),
            )
            results.append(await self.request(uow, request, materialized_at_utc))
        return tuple(results)


class SparseActivationService:
    """Trusted application seam; creates work and selects candidates, never cognition."""

    def __init__(
        self,
        uow_factory,
        clock: WallClock,
        wake_signal: SchedulerWakeSignal,
        planner: ActivationPlanner | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._wake_signal = wake_signal
        self._planner = planner or ActivationPlanner()

    async def request(self, request: ActivationRequest) -> ActivationRequestResult:
        async with self._uow_factory() as uow:
            result = await self._planner.request(uow, request, self._clock.now_utc())
            await uow.commit()
        if result.schedule_changed:
            self._wake_signal.wake(request.world_id)
        return result

    async def promote_character_active(
        self,
        character_id: CharacterId,
        source_request_id: RequestId,
        due_at: WorldTime,
        priority: TriggerPriority = TriggerPriority.NORMAL,
    ) -> ActivationRequestResult:
        return await self.request(
            ActivationRequest(
                world_id=character_id.world_id,
                target=ActivationTarget.character(character_id),
                activation_kind=ActivationKind.CHARACTER_REACTION,
                activation_version=1,
                cause=ActivationCause(
                    character_id.world_id,
                    ActivationCauseKind.EXPLICIT_SYSTEM,
                    source_request_id=source_request_id,
                ),
                due_at=due_at,
                priority=priority,
                coalescing_key="explicit_active",
                attention=ActivationAttention.ACTIVE,
            )
        )

    async def request_scene_activity(
        self,
        scene_id: SceneId,
        activity: SceneActivityKind,
        source_request_id: RequestId,
        due_at: WorldTime,
        priority: TriggerPriority = TriggerPriority.NORMAL,
    ) -> tuple[ActivationRequestResult, ...]:
        spec = EventWakeSpec(EventWakeKind.SCENE_CHARACTER_PARTICIPANTS, scene_id=scene_id)
        async with self._uow_factory() as uow:
            targets = await self._planner.wakes.resolve(
                uow, spec, world_id=scene_id.world_id, actor_id=None
            )
            results: list[ActivationRequestResult] = []
            for target in targets:
                request = ActivationRequest(
                    world_id=scene_id.world_id,
                    target=target,
                    activation_kind=ActivationKind.SCENE_ACTIVITY,
                    activation_version=1,
                    cause=ActivationCause(
                        scene_id.world_id,
                        ActivationCauseKind.SCENE_ACTIVITY,
                        source_scene_id=scene_id,
                        scene_activity=activity,
                        source_request_id=source_request_id,
                    ),
                    due_at=due_at,
                    priority=priority,
                    coalescing_key="scene_activity",
                    attention=ActivationAttention.ACTIVE,
                )
                results.append(await self._planner.request(uow, request, self._clock.now_utc()))
            await uow.commit()
        if any(result.schedule_changed for result in results):
            self._wake_signal.wake(scene_id.world_id)
        return tuple(results)

    async def select_due(
        self, world_id: WorldId, through: WorldTime, max_items: int
    ) -> tuple[ActivationCandidate, ...]:
        if type(max_items) is not int or max_items <= 0:
            raise ValueError("max_items must be positive")
        async with self._uow_factory() as uow:
            return await uow.activations.list_due_candidates(world_id, through, max_items)

    async def causes(
        self, activation_id: ActivationId, limit: int, offset: int = 0
    ) -> ActivationCausePage:
        if type(limit) is not int or limit <= 0 or type(offset) is not int or offset < 0:
            raise ValueError("bounded cause query requires positive limit and non-negative offset")
        async with self._uow_factory() as uow:
            return await uow.activations.causes(activation_id, limit, offset)
