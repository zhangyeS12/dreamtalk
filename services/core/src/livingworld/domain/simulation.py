"""Deterministic, game-neutral temporal scheduling values."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum, StrEnum

from livingworld.domain.contracts import RequestId
from livingworld.domain.errors import DomainInvariantError
from livingworld.domain.identifiers import (
    ActivationId,
    CharacterId,
    CorrelationId,
    EventId,
    SceneId,
    TriggerId,
    WorldId,
)
from livingworld.domain.values import (
    JsonValue,
    Revision,
    WorldTime,
    freeze_json,
    require_type,
    same_world,
    utc_timestamp,
)

MAX_TRIGGER_PAYLOAD_BYTES = 16_384
MAX_TRIGGER_KIND_LENGTH = 128
MAX_COALESCING_KEY_LENGTH = 128


class TriggerPriority(IntEnum):
    """Lower values run first when due times are equal."""

    HIGH = -1
    NORMAL = 0
    LOW = 1


class TriggerStatus(StrEnum):
    PENDING = "pending"
    FIRED = "fired"
    CANCELLED = "cancelled"


class ActivationStatus(StrEnum):
    PENDING = "pending"


class ActivationTargetKind(StrEnum):
    WORLD = "world"
    CHARACTER = "character"


class ActivationKind(StrEnum):
    WORLD_ORCHESTRATION = "world_orchestration"
    CHARACTER_REACTION = "character_reaction"
    CHARACTER_SCHEDULE_DUE = "character_schedule_due"
    SCENE_ACTIVITY = "scene_activity"


class ActivationAttention(StrEnum):
    NONE = "none"
    ACTIVE = "active"


class ActivationCauseKind(StrEnum):
    SCHEDULED_TRIGGER = "scheduled_trigger"
    WORLD_EVENT = "world_event"
    SCENE_ACTIVITY = "scene_activity"
    EXPLICIT_SYSTEM = "explicit_system"


class SceneActivityKind(StrEnum):
    CREATED = "created"
    PARTICIPANT_JOINED = "participant_joined"
    PARTICIPANT_LEFT = "participant_left"
    ENDED = "ended"
    ACTION = "action"


class EventWakeKind(StrEnum):
    NONE = "none"
    ACTOR = "actor"
    SCENE_CHARACTER_PARTICIPANTS = "scene_character_participants"
    EXPLICIT_CHARACTERS = "explicit_characters"
    WORLD = "world"


class SimulationFidelity(IntEnum):
    DORMANT = 0
    BACKGROUND = 1
    ACTIVE = 2
    SCENE_ACTIVE = 3
    PLAYER_FACING = 4


@dataclass(frozen=True, slots=True)
class ActivationTarget:
    world_id: WorldId
    kind: ActivationTargetKind
    character_id: CharacterId | None = None

    def __post_init__(self) -> None:
        require_type(self.world_id, WorldId, "world_id")
        require_type(self.kind, ActivationTargetKind, "activation target kind")
        if self.kind is ActivationTargetKind.WORLD:
            if self.character_id is not None:
                raise DomainInvariantError("WORLD activation target cannot contain a Character")
            return
        require_type(self.character_id, CharacterId, "character_id")
        same_world(self.world_id, self.character_id)

    @classmethod
    def world(cls, world_id: WorldId) -> ActivationTarget:
        return cls(world_id, ActivationTargetKind.WORLD)

    @classmethod
    def character(cls, character_id: CharacterId) -> ActivationTarget:
        return cls(character_id.world_id, ActivationTargetKind.CHARACTER, character_id)


@dataclass(frozen=True, slots=True)
class EventWakeSpec:
    kind: EventWakeKind = EventWakeKind.NONE
    scene_id: SceneId | None = None
    characters: tuple[CharacterId, ...] = ()

    def __post_init__(self) -> None:
        require_type(self.kind, EventWakeKind, "event wake kind")
        if self.kind is EventWakeKind.SCENE_CHARACTER_PARTICIPANTS:
            require_type(self.scene_id, SceneId, "scene_id")
            if self.characters:
                raise DomainInvariantError("Scene wake cannot contain explicit Characters")
            return
        if self.kind is EventWakeKind.EXPLICIT_CHARACTERS:
            if self.scene_id is not None or not self.characters:
                raise DomainInvariantError("Explicit wake requires Characters and no Scene")
            world = self.characters[0].world_id
            same_world(world, *self.characters)
            if len(set(self.characters)) != len(self.characters):
                raise DomainInvariantError("Explicit wake Characters must be unique")
            return
        if self.scene_id is not None or self.characters:
            raise DomainInvariantError("Wake kind does not accept Scene or Character data")


@dataclass(frozen=True, slots=True)
class ActivationCause:
    world_id: WorldId
    kind: ActivationCauseKind
    source_trigger_id: TriggerId | None = None
    source_event_id: EventId | None = None
    source_scene_id: SceneId | None = None
    scene_activity: SceneActivityKind | None = None
    source_request_id: RequestId | None = None

    def __post_init__(self) -> None:
        require_type(self.world_id, WorldId, "world_id")
        require_type(self.kind, ActivationCauseKind, "activation cause kind")
        present = {
            "trigger": self.source_trigger_id is not None,
            "event": self.source_event_id is not None,
            "scene": self.source_scene_id is not None,
            "activity": self.scene_activity is not None,
            "request": self.source_request_id is not None,
        }
        expected = {
            ActivationCauseKind.SCHEDULED_TRIGGER: {
                "trigger": True,
                "event": False,
                "scene": False,
                "activity": False,
                "request": False,
            },
            ActivationCauseKind.WORLD_EVENT: {
                "trigger": False,
                "event": True,
                "scene": False,
                "activity": False,
                "request": False,
            },
            ActivationCauseKind.SCENE_ACTIVITY: {
                "trigger": False,
                "event": False,
                "scene": True,
                "activity": True,
                "request": True,
            },
            ActivationCauseKind.EXPLICIT_SYSTEM: {
                "trigger": False,
                "event": False,
                "scene": False,
                "activity": False,
                "request": True,
            },
        }
        if present != expected[self.kind]:
            raise DomainInvariantError("activation cause references do not match its typed kind")
        references = (
            self.source_trigger_id,
            self.source_event_id,
            self.source_scene_id,
        )
        same_world(self.world_id, *(item for item in references if item is not None))
        if self.scene_activity is not None:
            require_type(self.scene_activity, SceneActivityKind, "scene_activity")
        if self.source_request_id is not None:
            require_type(self.source_request_id, RequestId, "source_request_id")

    @property
    def identity(self) -> str:
        if self.kind is ActivationCauseKind.SCHEDULED_TRIGGER:
            return f"scheduled_trigger:{self.source_trigger_id.value.hex}"
        if self.kind is ActivationCauseKind.WORLD_EVENT:
            return f"world_event:{self.source_event_id.value.hex}"
        if self.kind is ActivationCauseKind.SCENE_ACTIVITY:
            return (
                f"scene_activity:{self.source_scene_id.value.hex}:"
                f"{self.scene_activity.value}:{self.source_request_id.value.hex}"
            )
        return f"explicit_system:{self.source_request_id.value.hex}"


@dataclass(frozen=True, slots=True)
class SimulationActivationCause:
    activation_id: ActivationId
    cause: ActivationCause
    position: int
    request_fingerprint: str
    attached_at_utc: datetime

    def __post_init__(self) -> None:
        require_type(self.activation_id, ActivationId, "activation_id")
        if self.activation_id.world_id != self.cause.world_id:
            raise DomainInvariantError("activation cause belongs to a different world")
        if type(self.position) is not int or self.position <= 0:
            raise DomainInvariantError("activation cause position must be positive")
        if not re.fullmatch(r"[0-9a-f]{64}", self.request_fingerprint):
            raise DomainInvariantError("activation cause fingerprint must be SHA-256 hex")
        object.__setattr__(
            self,
            "attached_at_utc",
            utc_timestamp(self.attached_at_utc, "attached_at_utc"),
        )


@dataclass(frozen=True, slots=True)
class ActivationCausePage:
    causes: tuple[SimulationActivationCause, ...]
    more_causes: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class ActivationRequest:
    world_id: WorldId
    target: ActivationTarget
    activation_kind: ActivationKind
    activation_version: int
    cause: ActivationCause
    due_at: WorldTime
    priority: TriggerPriority = TriggerPriority.NORMAL
    coalescing_key: str | None = None
    attention: ActivationAttention = ActivationAttention.NONE
    payload: SimulationPayload = field(default_factory=lambda: SimulationPayload({}))
    source_contract_kind: str | None = None
    source_contract_version: int | None = None

    def __post_init__(self) -> None:
        require_type(self.world_id, WorldId, "world_id")
        require_type(self.target, ActivationTarget, "target")
        require_type(self.cause, ActivationCause, "cause")
        if self.target.world_id != self.world_id or self.cause.world_id != self.world_id:
            raise DomainInvariantError("activation request references another world")
        validate_activation_contract(self.activation_kind, self.activation_version)
        require_type(self.due_at, WorldTime, "due_at")
        require_type(self.priority, TriggerPriority, "priority")
        validate_coalescing_key(self.coalescing_key)
        require_type(self.attention, ActivationAttention, "attention")
        require_type(self.payload, SimulationPayload, "payload")
        if self.cause.kind is not ActivationCauseKind.SCHEDULED_TRIGGER and self.payload.data:
            raise DomainInvariantError(
                "non-scheduled activation payload must be empty; use typed cause references"
            )
        if (
            self.attention is ActivationAttention.ACTIVE
            and self.target.kind is not ActivationTargetKind.CHARACTER
        ):
            raise DomainInvariantError("ACTIVE attention is valid only for Character targets")
        kind = self.source_contract_kind or self.activation_kind.value
        version = self.source_contract_version or self.activation_version
        validate_trigger_contract(kind, version)
        object.__setattr__(self, "source_contract_kind", kind)
        object.__setattr__(self, "source_contract_version", version)


@dataclass(frozen=True, slots=True)
class ActivationRequestResult:
    activation: SimulationActivation
    coalesced: bool
    replayed: bool
    schedule_changed: bool


@dataclass(frozen=True, slots=True)
class ActivationCandidate:
    activation: SimulationActivation
    fidelity: SimulationFidelity | None


def _mutable_json(value: JsonValue) -> object:
    if isinstance(value, Mapping):
        return {key: _mutable_json(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [_mutable_json(child) for child in value]
    return value


@dataclass(frozen=True, slots=True)
class SimulationPayload:
    """A bounded immutable JSON object; never executable or dynamically imported."""

    data: Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        frozen = freeze_json(self.data)
        if not isinstance(frozen, Mapping):
            raise DomainInvariantError("simulation payload must be a JSON object")
        encoded = json.dumps(
            _mutable_json(frozen),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > MAX_TRIGGER_PAYLOAD_BYTES:
            raise DomainInvariantError("simulation payload exceeds the bounded size")
        object.__setattr__(self, "data", frozen)


def validate_trigger_contract(kind: str, payload_version: int) -> None:
    if not isinstance(kind, str) or not re.fullmatch(
        rf"[a-z][a-z0-9_.-]{{0,{MAX_TRIGGER_KIND_LENGTH - 1}}}", kind
    ):
        raise DomainInvariantError("trigger kind must be a bounded namespaced identifier")
    if type(payload_version) is not int or not 1 <= payload_version <= 65_535:
        raise DomainInvariantError("payload_version must be an integer in [1, 65535]")


def validate_activation_contract(kind: ActivationKind, version: int) -> None:
    require_type(kind, ActivationKind, "activation kind")
    if type(version) is not int or not 1 <= version <= 65_535:
        raise DomainInvariantError("activation version must be an integer in [1, 65535]")


def validate_coalescing_key(value: str | None) -> None:
    if value is None:
        return
    if not isinstance(value, str) or not re.fullmatch(
        rf"[a-z][a-z0-9_.-]{{0,{MAX_COALESCING_KEY_LENGTH - 1}}}", value
    ):
        raise DomainInvariantError("coalescing key must be a bounded namespaced identifier")


@dataclass(frozen=True, slots=True)
class ScheduledSimulationTrigger:
    trigger_id: TriggerId
    world_id: WorldId
    due_at: WorldTime
    priority: TriggerPriority
    enqueue_position: int
    kind: str
    payload_version: int
    payload: SimulationPayload
    activation_target: ActivationTarget
    activation_kind: ActivationKind
    activation_version: int
    activation_coalescing_key: str | None
    activation_attention: ActivationAttention
    status: TriggerStatus
    created_at_utc: datetime
    fired_at_utc: datetime | None = None
    cancelled_at_utc: datetime | None = None
    revision: Revision = Revision()
    causation_request_id: RequestId | None = None
    correlation_id: CorrelationId | None = None

    def __post_init__(self) -> None:
        require_type(self.trigger_id, TriggerId, "trigger_id")
        same_world(self.world_id, self.trigger_id)
        require_type(self.due_at, WorldTime, "due_at")
        require_type(self.priority, TriggerPriority, "priority")
        if type(self.enqueue_position) is not int or self.enqueue_position <= 0:
            raise DomainInvariantError("enqueue_position must be a positive integer")
        validate_trigger_contract(self.kind, self.payload_version)
        require_type(self.payload, SimulationPayload, "payload")
        require_type(self.activation_target, ActivationTarget, "activation_target")
        if self.activation_target.world_id != self.world_id:
            raise DomainInvariantError("activation target belongs to a different world")
        validate_activation_contract(self.activation_kind, self.activation_version)
        validate_coalescing_key(self.activation_coalescing_key)
        require_type(self.activation_attention, ActivationAttention, "activation_attention")
        if (
            self.activation_attention is ActivationAttention.ACTIVE
            and self.activation_target.kind is not ActivationTargetKind.CHARACTER
        ):
            raise DomainInvariantError("ACTIVE attention is valid only for Character targets")
        require_type(self.status, TriggerStatus, "trigger status")
        object.__setattr__(
            self, "created_at_utc", utc_timestamp(self.created_at_utc, "created_at_utc")
        )
        if self.fired_at_utc is not None:
            object.__setattr__(
                self, "fired_at_utc", utc_timestamp(self.fired_at_utc, "fired_at_utc")
            )
        if self.cancelled_at_utc is not None:
            object.__setattr__(
                self,
                "cancelled_at_utc",
                utc_timestamp(self.cancelled_at_utc, "cancelled_at_utc"),
            )
        require_type(self.revision, Revision, "revision")
        if self.causation_request_id is not None:
            require_type(self.causation_request_id, RequestId, "causation_request_id")
        if self.correlation_id is not None:
            require_type(self.correlation_id, CorrelationId, "correlation_id")
        terminal_times = (self.fired_at_utc is not None, self.cancelled_at_utc is not None)
        valid = {
            TriggerStatus.PENDING: (False, False),
            TriggerStatus.FIRED: (True, False),
            TriggerStatus.CANCELLED: (False, True),
        }
        if terminal_times != valid[self.status]:
            raise DomainInvariantError("trigger status and terminal timestamps disagree")


@dataclass(frozen=True, slots=True)
class SimulationActivation:
    activation_id: ActivationId
    world_id: WorldId
    target: ActivationTarget
    activation_kind: ActivationKind
    activation_version: int
    source_trigger_id: TriggerId | None
    kind: str
    payload_version: int
    due_at: WorldTime
    priority: TriggerPriority
    enqueue_position: int
    coalescing_key: str | None
    attention: ActivationAttention
    payload: SimulationPayload
    status: ActivationStatus
    materialized_at_utc: datetime

    def __post_init__(self) -> None:
        require_type(self.activation_id, ActivationId, "activation_id")
        require_type(self.target, ActivationTarget, "activation target")
        same_world(self.world_id, self.activation_id)
        if self.target.world_id != self.world_id:
            raise DomainInvariantError("activation target belongs to a different world")
        validate_activation_contract(self.activation_kind, self.activation_version)
        if self.source_trigger_id is not None:
            require_type(self.source_trigger_id, TriggerId, "source_trigger_id")
            same_world(self.world_id, self.source_trigger_id)
        validate_trigger_contract(self.kind, self.payload_version)
        require_type(self.due_at, WorldTime, "due_at")
        require_type(self.priority, TriggerPriority, "priority")
        if type(self.enqueue_position) is not int or self.enqueue_position <= 0:
            raise DomainInvariantError("activation enqueue_position must be positive")
        validate_coalescing_key(self.coalescing_key)
        require_type(self.attention, ActivationAttention, "activation attention")
        if (
            self.attention is ActivationAttention.ACTIVE
            and self.target.kind is not ActivationTargetKind.CHARACTER
        ):
            raise DomainInvariantError("ACTIVE attention is valid only for Character targets")
        require_type(self.payload, SimulationPayload, "payload")
        require_type(self.status, ActivationStatus, "activation status")
        object.__setattr__(
            self,
            "materialized_at_utc",
            utc_timestamp(self.materialized_at_utc, "materialized_at_utc"),
        )
