"""Evidence-backed EpisodicMemory formation without LLM or belief side effects."""

from dataclasses import dataclass, replace
from hashlib import sha256
from uuid import UUID, uuid4

from livingworld.application.errors import (
    EntityAlreadyExistsError,
    EntityNotFoundError,
    IdempotencyConflictError,
    MemoryEvidenceAccessDeniedError,
)
from livingworld.application.fingerprints import canonical_json, id_input
from livingworld.application.idempotency import run_with_receipt_recovery
from livingworld.application.ports import (
    TemporalMutationBarrier,
    WallClock,
    WorldTimeSource,
)
from livingworld.application.results import MemoryResult
from livingworld.domain.commands import CommandReceipt
from livingworld.domain.contracts import RequestId
from livingworld.domain.errors import DomainInvariantError
from livingworld.domain.identifiers import CharacterId, MemoryId, ObservationId, WorldId
from livingworld.domain.memory import (
    MAX_EPISODIC_MEMORY_CONTENT_BYTES,
    MAX_EPISODIC_MEMORY_SOURCES,
    EpisodicMemory,
    MemorySalience,
)
from livingworld.domain.values import require_text, require_type, same_world, utc_timestamp


@dataclass(frozen=True, slots=True, kw_only=True)
class RecordEpisodicMemory:
    request_id: RequestId
    world_id: WorldId
    owner_character_id: CharacterId
    source_observation_ids: tuple[ObservationId, ...]
    content: str
    salience: MemorySalience | None = None

    def __post_init__(self) -> None:
        require_type(self.request_id, RequestId, "request_id")
        require_type(self.request_id.value, UUID, "request_id value")
        require_type(self.owner_character_id, CharacterId, "owner_character_id")
        same_world(self.world_id, self.owner_character_id)
        sources = tuple(self.source_observation_ids)
        if not sources:
            raise MemoryEvidenceAccessDeniedError("EpisodicMemory requires Observation evidence")
        if len(sources) > MAX_EPISODIC_MEMORY_SOURCES:
            raise MemoryEvidenceAccessDeniedError("Too many Observation evidence sources")
        if len(set(sources)) != len(sources):
            raise MemoryEvidenceAccessDeniedError("Observation evidence must be unique")
        for source in sources:
            require_type(source, ObservationId, "source_observation_id")
            same_world(self.world_id, source)
        object.__setattr__(self, "source_observation_ids", sources)
        require_text(self.content, "memory content")
        if len(self.content.encode("utf-8")) > MAX_EPISODIC_MEMORY_CONTENT_BYTES:
            raise DomainInvariantError("Memory content exceeds the UTF-8 size limit")
        if self.salience is not None:
            require_type(self.salience, MemorySalience, "salience")


def memory_fingerprint(command: RecordEpisodicMemory) -> str:
    semantic = {
        "fingerprint_version": 1,
        "command_type": type(command).__name__,
        "world_id": id_input(command.world_id),
        "owner_character_id": id_input(command.owner_character_id),
        "source_observation_ids": [
            id_input(observation_id) for observation_id in command.source_observation_ids
        ],
        "content": command.content,
        "salience": command.salience.value if command.salience is not None else None,
        "kind": "episodic",
        "kind_version": 1,
        "content_format": "plain_text",
        "content_version": 1,
        "provenance_kind": "observation_evidence",
        "provenance_version": 1,
    }
    return sha256(canonical_json(semantic).encode("utf-8")).hexdigest()


class EpisodicMemoryService:
    def __init__(
        self,
        uow_factory,
        clock: WallClock,
        *,
        world_time_source: WorldTimeSource,
        mutation_barrier: TemporalMutationBarrier | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._world_time_source = world_time_source
        self._mutation_barrier = mutation_barrier

    async def execute(self, command: RecordEpisodicMemory) -> MemoryResult:
        if self._mutation_barrier is not None:
            await self._mutation_barrier.assert_mutation_allowed(command.world_id)
        fingerprint = memory_fingerprint(command)
        return await run_with_receipt_recovery(
            lambda: self._transaction(command, fingerprint),
            self._uow_factory,
            lambda uow: uow.receipts.existing_memory(command.request_id, fingerprint),
            (EntityAlreadyExistsError, IdempotencyConflictError),
        )

    async def _transaction(self, command: RecordEpisodicMemory, fingerprint: str) -> MemoryResult:
        async with self._uow_factory() as uow:
            existing = await uow.receipts.existing_memory(command.request_id, fingerprint)
            if existing is not None:
                return replace(existing, replayed=True)
            world = await uow.worlds.get(command.world_id)
            if world is None:
                raise EntityNotFoundError("World does not exist")
            owner = await uow.characters.get(command.owner_character_id)
            if owner is None:
                raise EntityNotFoundError("Memory owner Character does not exist")
            observations = await uow.memories.authorized_observations(
                command.owner_character_id, command.source_observation_ids
            )
            by_id = {item.observation_id: item for item in observations}
            if len(by_id) != len(command.source_observation_ids) or any(
                identity not in by_id for identity in command.source_observation_ids
            ):
                raise MemoryEvidenceAccessDeniedError(
                    "Observation evidence is unavailable to the memory owner"
                )
            ordered = tuple(by_id[identity] for identity in command.source_observation_ids)
            experienced_from = min(item.observed_at for item in ordered)
            experienced_to = max(item.observed_at for item in ordered)
            formed_at = self._world_time_source.read(world.clock)
            now = utc_timestamp(self._clock.now_utc(), "memory creation wall clock")
            memory = EpisodicMemory(
                MemoryId(command.world_id, uuid4()),
                command.world_id,
                command.owner_character_id,
                command.content,
                experienced_from,
                experienced_to,
                formed_at,
                now,
                command.source_observation_ids,
                command.salience,
            )
            await uow.memories.add(memory)
            result = MemoryResult(command.request_id, memory.memory_id)
            receipt = CommandReceipt(
                command.request_id,
                command.world_id,
                type(command).__name__,
                "committed",
                now,
                now,
            )
            await uow.receipts.add_memory(receipt, fingerprint, result)
            await uow.commit()
            return result
