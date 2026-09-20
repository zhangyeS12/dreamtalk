"""Deterministic, game-neutral temporal scheduling values."""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum, StrEnum

from livingworld.domain.contracts import RequestId
from livingworld.domain.errors import DomainInvariantError
from livingworld.domain.identifiers import ActivationId, CorrelationId, TriggerId, WorldId
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
    source_trigger_id: TriggerId
    kind: str
    payload_version: int
    due_at: WorldTime
    payload: SimulationPayload
    status: ActivationStatus
    materialized_at_utc: datetime

    def __post_init__(self) -> None:
        require_type(self.activation_id, ActivationId, "activation_id")
        require_type(self.source_trigger_id, TriggerId, "source_trigger_id")
        same_world(self.world_id, self.activation_id, self.source_trigger_id)
        validate_trigger_contract(self.kind, self.payload_version)
        require_type(self.due_at, WorldTime, "due_at")
        require_type(self.payload, SimulationPayload, "payload")
        require_type(self.status, ActivationStatus, "activation status")
        object.__setattr__(
            self,
            "materialized_at_utc",
            utc_timestamp(self.materialized_at_utc, "materialized_at_utc"),
        )
