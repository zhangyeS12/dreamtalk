"""developer wire DTOs; TypeScript declarations and guards are generated from this source."""

from __future__ import annotations

from typing import Literal, TypedDict

from pydantic import ConfigDict, with_config

from livingworld.adapters.http.wire_contracts.core import WorldSummary
from livingworld.adapters.http.wire_contracts.numbers import WireNumber


@with_config(ConfigDict(extra="allow"))
class InspectorSnapshotClock(TypedDict):
    world_time: str
    state: Literal["running", "paused"]
    scale: str
    revision: WireNumber


@with_config(ConfigDict(extra="allow"))
class InspectorSnapshotLocationsItem(TypedDict):
    location_id: str
    name: str


@with_config(ConfigDict(extra="allow"))
class InspectorSnapshotPlayersItem(TypedDict):
    player_id: str
    name: str
    location_id: str
    activity: str
    availability: str
    revision: WireNumber


@with_config(ConfigDict(extra="allow"))
class InspectorSnapshotCharactersItem(TypedDict):
    character_id: str
    name: str
    location_id: str | None


@with_config(ConfigDict(extra="allow"))
class InspectorSnapshotScenesItemParticipantsItem(TypedDict):
    kind: str
    principal_id: str
    name: str
    joined_at: str


@with_config(ConfigDict(extra="allow"))
class InspectorSnapshotScenesItem(TypedDict):
    scene_id: str
    location_id: str
    status: str
    started_at: str
    participants: list[InspectorSnapshotScenesItemParticipantsItem]


@with_config(ConfigDict(extra="allow"))
class InspectorSnapshotTriggersItem(TypedDict):
    trigger_id: str
    kind: str
    status: str
    priority: WireNumber
    due_at: str


@with_config(ConfigDict(extra="allow"))
class InspectorSnapshotActivationsItem(TypedDict):
    activation_id: str
    target: str
    kind: str
    priority: WireNumber
    due_at: str
    fidelity: str | None
    cause_count: WireNumber


@with_config(ConfigDict(extra="allow"))
class InspectorSnapshotEventsItem(TypedDict):
    event_id: str
    type: str
    occurred_at: str
    ledger_position: WireNumber


@with_config(ConfigDict(extra="allow"))
class InspectorSnapshotObservationsItem(TypedDict):
    observation_id: str
    principal_kind: str
    principal_id: str
    principal_name: str
    event_id: str
    channel: str
    observed_at: str


@with_config(ConfigDict(extra="allow"))
class InspectorSnapshotMemoriesItemEvidenceItem(TypedDict):
    observation_id: str
    observed_at: str


@with_config(ConfigDict(extra="allow"))
class InspectorSnapshotMemoriesItem(TypedDict):
    memory_id: str
    owner_character_id: str
    content: str
    experienced_from: str
    experienced_to: str
    formed_at: str
    salience: WireNumber | None
    evidence: list[InspectorSnapshotMemoriesItemEvidenceItem]


@with_config(ConfigDict(extra="allow"))
class InspectorSnapshot(TypedDict):
    world: WorldSummary
    clock: InspectorSnapshotClock
    runtime_state: str
    locations: list[InspectorSnapshotLocationsItem]
    players: list[InspectorSnapshotPlayersItem]
    characters: list[InspectorSnapshotCharactersItem]
    scenes: list[InspectorSnapshotScenesItem]
    triggers: list[InspectorSnapshotTriggersItem]
    activations: list[InspectorSnapshotActivationsItem]
    events: list[InspectorSnapshotEventsItem]
    observations: list[InspectorSnapshotObservationsItem]
    memories: list[InspectorSnapshotMemoriesItem]
