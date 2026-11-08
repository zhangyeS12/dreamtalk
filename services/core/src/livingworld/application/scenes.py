"""Transactional Scene lifecycle operations with Presence as physical authority."""

from dataclasses import dataclass, replace
from hashlib import sha256
from uuid import uuid4

from livingworld.application.errors import (
    EntityAlreadyExistsError,
    EntityNotFoundError,
    IdempotencyConflictError,
)
from livingworld.application.fingerprints import canonical_json, id_input
from livingworld.application.idempotency import run_with_receipt_recovery
from livingworld.application.ports import UnitOfWork, WallClock
from livingworld.application.results import SceneResult
from livingworld.domain.commands import CommandReceipt
from livingworld.domain.contracts import RequestId
from livingworld.domain.errors import DomainInvariantError
from livingworld.domain.identifiers import (
    CharacterId,
    LocationId,
    PlayerId,
    PrincipalId,
    SceneId,
    SceneParticipantId,
    WorldId,
)
from livingworld.domain.scenes import Scene, SceneParticipant, SceneStatus
from livingworld.domain.values import Revision, WorldTime, require_type, same_world, utc_timestamp


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateScene:
    request_id: RequestId
    world_id: WorldId
    scene_id: SceneId
    location_id: LocationId
    initial_participants: tuple[PrincipalId, ...]
    started_at: WorldTime

    def __post_init__(self) -> None:
        require_type(self.request_id, RequestId, "request_id")
        require_type(self.scene_id, SceneId, "scene_id")
        require_type(self.location_id, LocationId, "location_id")
        require_type(self.started_at, WorldTime, "started_at")
        same_world(self.world_id, self.scene_id, self.location_id, *self.initial_participants)
        if not self.initial_participants:
            raise DomainInvariantError("Scene requires at least one initial participant")
        if len(set(self.initial_participants)) != len(self.initial_participants):
            raise DomainInvariantError("Scene initial participants must be unique")


@dataclass(frozen=True, slots=True, kw_only=True)
class JoinScene:
    request_id: RequestId
    world_id: WorldId
    scene_id: SceneId
    principal_id: PrincipalId
    joined_at: WorldTime
    expected_scene_revision: Revision


@dataclass(frozen=True, slots=True, kw_only=True)
class LeaveScene:
    request_id: RequestId
    world_id: WorldId
    scene_id: SceneId
    principal_id: PrincipalId
    left_at: WorldTime
    expected_scene_revision: Revision


@dataclass(frozen=True, slots=True, kw_only=True)
class EndScene:
    request_id: RequestId
    world_id: WorldId
    scene_id: SceneId
    ended_at: WorldTime
    expected_scene_revision: Revision


type SceneCommand = CreateScene | JoinScene | LeaveScene | EndScene


def _scene_fingerprint(command: SceneCommand) -> str:
    value = {
        "fingerprint_version": 1,
        "command_type": type(command).__name__,
        "world_id": id_input(command.world_id),
        "scene_id": id_input(command.scene_id),
    }
    match command:
        case CreateScene():
            value |= {
                "location_id": id_input(command.location_id),
                "initial_participants": sorted(
                    (id_input(principal) for principal in command.initial_participants),
                    key=lambda item: (item["kind"], item["id"]),
                ),
                "started_at": command.started_at.microseconds,
            }
        case JoinScene():
            value |= {
                "principal_id": id_input(command.principal_id),
                "joined_at": command.joined_at.microseconds,
                "expected_scene_revision": command.expected_scene_revision.value,
            }
        case LeaveScene():
            value |= {
                "principal_id": id_input(command.principal_id),
                "left_at": command.left_at.microseconds,
                "expected_scene_revision": command.expected_scene_revision.value,
            }
        case EndScene():
            value |= {
                "ended_at": command.ended_at.microseconds,
                "expected_scene_revision": command.expected_scene_revision.value,
            }
    return sha256(canonical_json(value).encode()).hexdigest()


class SceneService:
    def __init__(self, uow_factory, clock: WallClock):
        self._uow_factory = uow_factory
        self._clock = clock

    async def execute(self, command: SceneCommand) -> SceneResult:
        self._validate(command)
        fingerprint = _scene_fingerprint(command)
        return await run_with_receipt_recovery(
            lambda: self._execute(command, fingerprint),
            self._uow_factory,
            lambda uow: uow.receipts.existing_scene(command.request_id, fingerprint),
            (EntityAlreadyExistsError, IdempotencyConflictError),
        )

    def _validate(self, command: SceneCommand) -> None:
        require_type(command.request_id, RequestId, "request_id")
        require_type(command.scene_id, SceneId, "scene_id")
        same_world(command.world_id, command.scene_id)
        if not isinstance(command, CreateScene):
            require_type(command.expected_scene_revision, Revision, "expected_scene_revision")
        if isinstance(command, (JoinScene, LeaveScene)):
            require_type(command.principal_id, (PlayerId, CharacterId), "principal_id")
            same_world(command.world_id, command.principal_id)
        time = (
            command.started_at
            if isinstance(command, CreateScene)
            else command.joined_at
            if isinstance(command, JoinScene)
            else command.left_at
            if isinstance(command, LeaveScene)
            else command.ended_at
        )
        require_type(time, WorldTime, "scene operation time")

    async def _physical_location(
        self, uow: UnitOfWork, principal: PrincipalId
    ) -> LocationId | None:
        if isinstance(principal, PlayerId):
            if await uow.players.get(principal) is None:
                return None
            presence = await uow.players.presence(principal)
            return presence.location_id if presence is not None else None
        if await uow.characters.get(principal) is None:
            return None
        state = await uow.characters.state(principal)
        return state.location_id if state is not None else None

    async def _execute(self, command: SceneCommand, fingerprint: str) -> SceneResult:
        async with self._uow_factory() as uow:
            existing = await uow.receipts.existing_scene(command.request_id, fingerprint)
            if existing is not None:
                return replace(existing, replayed=True)
            world = await uow.worlds.get(command.world_id)
            if world is None:
                raise EntityNotFoundError("World does not exist")
            now = utc_timestamp(self._clock.now_utc(), "application wall clock")
            if isinstance(command, CreateScene):
                if await uow.locations.get(command.location_id) is None:
                    raise EntityNotFoundError("Scene Location does not exist")
                if await uow.scenes.get(command.scene_id) is not None:
                    raise EntityAlreadyExistsError("Scene already exists")
                participants = []
                for principal in command.initial_participants:
                    if await self._physical_location(uow, principal) != command.location_id:
                        raise DomainInvariantError(
                            "Initial Scene participant is not physically present at Scene Location"
                        )
                    if await uow.scenes.active_for_principal(principal) is not None:
                        raise DomainInvariantError(
                            "Principal already participates in an active Scene"
                        )
                    participants.append(
                        SceneParticipant(
                            SceneParticipantId(command.world_id, uuid4()),
                            command.world_id,
                            command.scene_id,
                            principal,
                            command.started_at,
                        )
                    )
                scene = Scene(
                    command.scene_id,
                    command.world_id,
                    command.location_id,
                    SceneStatus.OPEN,
                    command.started_at,
                    None,
                    Revision(),
                    now,
                )
                await uow.scenes.add(scene, tuple(participants))
            else:
                scene = await uow.scenes.get(command.scene_id)
                if scene is None:
                    raise EntityNotFoundError("Scene does not exist")
                if scene.status is SceneStatus.CLOSED:
                    raise DomainInvariantError("Closed Scene cannot change")
                if scene.revision != command.expected_scene_revision:
                    from livingworld.domain.errors import ConcurrencyConflictError

                    raise ConcurrencyConflictError(
                        "Scene does not match expected revision",
                        resource_kind="Scene",
                        resource_identity=scene.scene_id,
                        expected_revision=command.expected_scene_revision,
                        actual_revision=scene.revision,
                    )
                if isinstance(command, JoinScene):
                    if command.joined_at < scene.started_at:
                        raise DomainInvariantError(
                            "Scene participant cannot join before Scene started_at"
                        )
                    if (
                        await self._physical_location(uow, command.principal_id)
                        != scene.location_id
                    ):
                        raise DomainInvariantError(
                            "Scene participant is not physically present at Scene Location"
                        )
                    if await uow.scenes.active_for_principal(command.principal_id) is not None:
                        raise DomainInvariantError(
                            "Principal already participates in an active Scene"
                        )
                    next_scene = scene.advance(command.expected_scene_revision)
                    await uow.scenes.replace(next_scene, command.expected_scene_revision)
                    await uow.scenes.add_participant(
                        SceneParticipant(
                            SceneParticipantId(command.world_id, uuid4()),
                            command.world_id,
                            command.scene_id,
                            command.principal_id,
                            command.joined_at,
                        )
                    )
                    scene = next_scene
                elif isinstance(command, LeaveScene):
                    participant = await uow.scenes.active_for_principal(command.principal_id)
                    if participant is None or participant.scene_id != command.scene_id:
                        raise EntityNotFoundError("Principal is not an active Scene participant")
                    next_scene = scene.advance(command.expected_scene_revision)
                    await uow.scenes.replace(next_scene, command.expected_scene_revision)
                    await uow.scenes.leave_participant(participant.leave(command.left_at))
                    scene = next_scene
                else:
                    next_scene = scene.close(command.ended_at, command.expected_scene_revision)
                    await uow.scenes.replace(next_scene, command.expected_scene_revision)
                    await uow.scenes.leave_all(command.scene_id, command.ended_at)
                    scene = next_scene
            result = SceneResult(command.request_id, scene.scene_id, scene.revision)
            receipt = CommandReceipt(
                command.request_id,
                command.world_id,
                type(command).__name__,
                "committed",
                now,
                now,
            )
            await uow.receipts.add_scene(receipt, fingerprint, result)
            await uow.commit()
            return result
