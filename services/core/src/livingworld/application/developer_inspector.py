"""Developer-only runtime inspection composed from canonical application paths."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import UUID, uuid4, uuid5

from livingworld.application.command_handler import CommandHandler
from livingworld.application.commands import (
    CreateCharacter,
    CreateLocation,
    CreatePlayer,
    CreateWorld,
    MovePlayer,
    PlaceCharacter,
)
from livingworld.application.memory import EpisodicMemoryService, RecordEpisodicMemory
from livingworld.application.scenes import CreateScene, SceneService
from livingworld.application.scheduler import ScheduleTrigger, SimulationScheduler
from livingworld.application.simulation_runtime import WorldClockService, WorldSimulationRuntime
from livingworld.domain.contracts import RequestId
from livingworld.domain.identifiers import (
    CharacterId,
    LocationId,
    MemoryId,
    ObservationId,
    PlayerId,
    SceneId,
    TriggerId,
    WorldId,
)
from livingworld.domain.memory import MemorySalience
from livingworld.domain.simulation import (
    ActivationKind,
    ActivationTarget,
    SimulationPayload,
    TriggerPriority,
)
from livingworld.domain.values import Revision, WorldTime

DEMO_NAMESPACE = UUID("d67d7e04-16dd-4d31-9e3c-2fdd92ee5480")
INSPECTOR_TRIGGER_KIND = "developer.inspector"


class DeveloperInspectorStore(Protocol):
    async def list_worlds(self) -> list[dict[str, object]]: ...
    async def snapshot(self, world_id: WorldId) -> dict[str, object]: ...
    async def player_presence_revision(self, player_id: PlayerId) -> Revision | None: ...


@dataclass(frozen=True, slots=True)
class DemoIdentity:
    world: WorldId
    location_a: LocationId
    location_b: LocationId
    player_a: PlayerId
    character_a: CharacterId
    character_b: CharacterId
    scene_a: SceneId


def _stable(label: str) -> UUID:
    return uuid5(DEMO_NAMESPACE, label)


def demo_identity() -> DemoIdentity:
    world = WorldId(_stable("world_demo"))
    return DemoIdentity(
        world,
        LocationId(world, _stable("location_a")),
        LocationId(world, _stable("location_b")),
        PlayerId(world, _stable("player_a")),
        CharacterId(world, _stable("character_a")),
        CharacterId(world, _stable("character_b")),
        SceneId(world, _stable("scene_a")),
    )


class DeveloperInspectorService:
    def __init__(
        self,
        store: DeveloperInspectorStore,
        command_handler: CommandHandler,
        scene_service: SceneService,
        memory_service: EpisodicMemoryService,
        scheduler: SimulationScheduler,
        clock_service: WorldClockService,
        runtime: WorldSimulationRuntime,
        memory_reader_factory,
        uow_factory,
    ) -> None:
        self._store = store
        self._execute_command = command_handler.execute
        self._execute_scene = scene_service.execute
        self._record_memory = memory_service.execute
        self._scheduler = scheduler
        self._clock_service = clock_service
        self._runtime = runtime
        self._memory_reader_factory = memory_reader_factory
        self._uow_factory = uow_factory

    async def list_worlds(self) -> list[dict[str, object]]:
        return await self._store.list_worlds()

    async def snapshot(
        self, world_id: WorldId, owner_character_id: CharacterId | None = None
    ) -> dict[str, object]:
        data = await self._store.snapshot(world_id)
        clocks = {clock.world_id: clock for clock in await self._clock_service.list_clocks()}
        clock = clocks.get(world_id)
        if clock is None:
            raise ValueError("world_not_found")
        data["clock"] = {
            "world_time": str(self._clock_service.current_time(clock).microseconds),
            "state": clock.state.value,
            "scale": str(clock.time_scale),
            "revision": clock.revision.value,
        }
        state = self._runtime.state(world_id)
        data["runtime_state"] = state.value if state is not None else "unmanaged"
        async with self._uow_factory() as uow:
            candidates = await uow.activations.list_due_candidates(
                world_id, self._clock_service.current_time(clock), 1000
            )
        fidelity_by_id = {
            str(item.activation.activation_id.value): (
                item.fidelity.name.lower() if item.fidelity is not None else None
            )
            for item in candidates
        }
        for activation in data["activations"]:
            activation["fidelity"] = fidelity_by_id.get(activation["activation_id"])
        data["memories"] = []
        if owner_character_id is not None:
            if owner_character_id.world_id != world_id:
                raise ValueError("owner_world_mismatch")
            reader = self._memory_reader_factory(owner_character_id)
            page = await reader.list(limit=50)
            memories = []
            for memory in page.items:
                evidence = await reader.evidence(memory.memory_id)
                memories.append(
                    {
                        "memory_id": str(memory.memory_id.value),
                        "owner_character_id": str(memory.owner_character_id.value),
                        "content": memory.content,
                        "experienced_from": str(memory.experienced_from.microseconds),
                        "experienced_to": str(memory.experienced_to.microseconds),
                        "formed_at": str(memory.formed_at.microseconds),
                        "salience": memory.salience.value if memory.salience else None,
                        "evidence": [
                            {
                                "observation_id": str(item.observation_id.value),
                                "observed_at": str(item.observed_at.microseconds),
                            }
                            for item in evidence
                        ],
                    }
                )
            data["memories"] = memories
        return data

    async def create_demo_world(self) -> WorldId:
        ids = demo_identity()
        commands = (
            CreateWorld(
                request_id=RequestId(_stable("create_world_demo")),
                world_id=ids.world,
                name="world_demo",
            ),
            CreateLocation(
                request_id=RequestId(_stable("create_location_a")),
                world_id=ids.world,
                location_id=ids.location_a,
                name="location_a",
            ),
            CreateLocation(
                request_id=RequestId(_stable("create_location_b")),
                world_id=ids.world,
                location_id=ids.location_b,
                name="location_b",
            ),
            CreatePlayer(
                request_id=RequestId(_stable("create_player_a")),
                world_id=ids.world,
                player_id=ids.player_a,
                name="player_a",
                initial_location_id=ids.location_a,
            ),
            CreateCharacter(
                request_id=RequestId(_stable("create_character_a")),
                world_id=ids.world,
                character_id=ids.character_a,
                name="character_a",
            ),
            CreateCharacter(
                request_id=RequestId(_stable("create_character_b")),
                world_id=ids.world,
                character_id=ids.character_b,
                name="character_b",
            ),
            PlaceCharacter(
                request_id=RequestId(_stable("place_character_a")),
                world_id=ids.world,
                character_id=ids.character_a,
                location_id=ids.location_a,
                expected_state_revision=None,
            ),
            PlaceCharacter(
                request_id=RequestId(_stable("place_character_b")),
                world_id=ids.world,
                character_id=ids.character_b,
                location_id=ids.location_b,
                expected_state_revision=None,
            ),
        )
        for command in commands:
            await self._execute_command(command)
        await self._execute_scene(
            CreateScene(
                request_id=RequestId(_stable("create_scene_a")),
                world_id=ids.world,
                scene_id=ids.scene_a,
                location_id=ids.location_a,
                initial_participants=(ids.character_a,),
                started_at=WorldTime(0),
            )
        )
        return ids.world

    async def pause(self, world_id: WorldId) -> None:
        await self._runtime.pause(world_id)

    async def resume(self, world_id: WorldId) -> None:
        await self._runtime.resume(world_id)

    async def change_scale(self, world_id: WorldId, scale: Decimal) -> None:
        await self._runtime.change_scale(world_id, scale)

    async def schedule_trigger(
        self,
        world_id: WorldId,
        delay_microseconds: int,
        target_character_id: CharacterId,
    ) -> TriggerId:
        if delay_microseconds < 0:
            raise ValueError("delay_must_be_nonnegative")
        clock = next(
            (item for item in await self._clock_service.list_clocks() if item.world_id == world_id),
            None,
        )
        if clock is None:
            raise ValueError("world_not_found")
        trigger_id = TriggerId(world_id, uuid4())
        await self._scheduler.schedule_trigger(
            ScheduleTrigger(
                request_id=RequestId(uuid4()),
                trigger_id=trigger_id,
                world_id=world_id,
                due_at=WorldTime(
                    self._clock_service.current_time(clock).microseconds + delay_microseconds
                ),
                priority=TriggerPriority.NORMAL,
                kind=INSPECTOR_TRIGGER_KIND,
                payload_version=1,
                payload=SimulationPayload({}),
                activation_target=ActivationTarget.character(target_character_id),
                activation_kind=ActivationKind.CHARACTER_SCHEDULE_DUE,
            )
        )
        return trigger_id

    async def move_player(
        self, world_id: WorldId, player_id: PlayerId, destination_id: LocationId
    ) -> None:
        revision = await self._store.player_presence_revision(player_id)
        if revision is None:
            raise ValueError("player_presence_not_found")
        await self._execute_command(
            MovePlayer(
                request_id=RequestId(uuid4()),
                world_id=world_id,
                player_id=player_id,
                destination_id=destination_id,
                expected_presence_revision=revision,
            )
        )

    async def record_memory(
        self,
        world_id: WorldId,
        owner_character_id: CharacterId,
        observation_id: ObservationId,
        content: str,
        salience: int | None,
    ) -> MemoryId:
        result = await self._record_memory(
            RecordEpisodicMemory(
                request_id=RequestId(uuid4()),
                world_id=world_id,
                owner_character_id=owner_character_id,
                source_observation_ids=(observation_id,),
                content=content,
                salience=MemorySalience(salience) if salience is not None else None,
            )
        )
        return result.memory_id
