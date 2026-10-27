"""Wire DTOs shared with generated TypeScript; keep business types out of the host protocol.

The generator reads this module's AST only. It never constructs the app or opens storage.
"""

from decimal import Decimal
from typing import Literal, NotRequired, TypedDict
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from livingworld.application.runtime import LLMRuntimeStatus
from livingworld.domain.participants import PlayerAvailability
from livingworld.domain.world import ClockState


class CoreHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ready: bool
    core_version: str
    api_protocol: int
    generation: str
    llm_status: LLMRuntimeStatus


class WorldSummary(TypedDict):
    world_id: str
    name: str


class WorldSettings(WorldSummary):
    world_time: str
    clock_state: ClockState
    time_scale: str
    runtime_state: str


class SelectablePlayer(TypedDict):
    player_id: str
    name: str


class SelectedPlayerState(TypedDict):
    player_id: str | None
    availability: PlayerAvailability | None
    presence_revision: int | None


class LocalProfile(TypedDict):
    name: str
    description: str
    revision: int


class KnownWorldEvent(TypedDict):
    event_id: str
    title: str
    occurred_at: str
    observed_at: str
    ledger_position: int
    description: NotRequired[str | None]
    observation_channel: NotRequired[str | None]


class ChatConversation(TypedDict):
    conversation_id: str
    player_id: str
    character_id: str
    root_import_id: str
    character_name: str
    kind: Literal["direct"]
    pinned: NotRequired[bool]
    read_only: NotRequired[bool]


class GroupParticipant(TypedDict):
    character_id: str
    root_import_id: str
    character_name: str


class GroupChatConversation(TypedDict):
    conversation_id: str
    player_id: str
    kind: Literal["group"]
    pinned: NotRequired[bool]
    read_only: NotRequired[bool]
    participants: list[GroupParticipant]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateWorldRequest(StrictModel):
    name: str = Field(min_length=1, max_length=120)


class ClockScaleRequest(StrictModel):
    scale: Decimal = Field(gt=0, le=1000)


class DeleteWorldRequest(StrictModel):
    confirmed: bool
    expected_name: str = Field(min_length=1, max_length=120)


class ProfileWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(max_length=120)
    description: str = Field(max_length=8000)
    expected_revision: int = Field(ge=0, strict=True)


class BindPlayerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    player_id: UUID


class AvailabilityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    availability: PlayerAvailability
    expected_presence_revision: int = Field(ge=0, strict=True)


class CreateGroupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    import_ids: list[UUID] = Field(min_length=2)
