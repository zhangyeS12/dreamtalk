"""background wire DTOs; TypeScript declarations and guards are generated from this source."""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict

from pydantic import ConfigDict, with_config

from livingworld.adapters.http.wire_contracts.numbers import WireNumber


@with_config(ConfigDict(extra="allow"))
class ProactiveContactStatus(TypedDict):
    player_id: str
    enabled: bool
    consented: bool
    revision: WireNumber
    interval_minutes: WireNumber
    state: Literal["off", "idle", "writing", "attention", "waiting_reply"]
    error: str | None
    model_available: bool
    waiting_conversation_id: str | None


@with_config(ConfigDict(extra="allow"))
class ChatUnreadStatusItemsItem(TypedDict):
    conversation_id: str
    latest_position: WireNumber
    unread: WireNumber


@with_config(ConfigDict(extra="allow"))
class ChatUnreadStatus(TypedDict):
    player_id: str
    items: list[ChatUnreadStatusItemsItem]
    waiting_conversation_id: str | None
    has_unread: NotRequired[bool]
    next_after: NotRequired[str | None]


@with_config(ConfigDict(extra="allow"))
class OfflineContactStatusUnreadItem(TypedDict):
    message_id: str
    conversation_id: str


@with_config(ConfigDict(extra="allow"))
class OfflineInputPreparation(TypedDict):
    selected: int
    excluded: int
    clipped: int
    batched: bool
    background_omitted: bool
    context_limited: bool


@with_config(ConfigDict(extra="allow"))
class OfflineContactStatus(TypedDict):
    enabled: bool
    consented: bool
    revision: WireNumber
    hours: WireNumber
    state: Literal[
        "off", "idle", "waiting", "planning", "writing", "delivered", "skipped", "attention"
    ]
    error: str | None
    last_online_at: str | None
    model_available: bool
    unread: list[OfflineContactStatusUnreadItem]
    input_preparation: NotRequired[OfflineInputPreparation | None]


@with_config(ConfigDict(extra="allow"))
class DirectorStatus(TypedDict):
    batch_size: NotRequired[WireNumber]
    batch_size_revision: NotRequired[WireNumber]
    enabled: bool
    revision: WireNumber
    state: Literal["off", "idle", "planning", "ready", "attention"]
    error: str | None
    consented: bool
    model_available: bool
    model: str | None
    encounters_enabled: bool
    encounter_revision: WireNumber
    encounters_consented: bool
    shared_activities_enabled: bool
    shared_activity_revision: WireNumber
    shared_activities_consented: bool


@with_config(ConfigDict(extra="allow"))
class ChatStoryEntry(TypedDict):
    entry_id: str
    character_id: str
    character_name: str
    conversation_id: str
    message_id: str
    kind: Literal["activity", "plan", "rumor", "invitation", "change"]
    title: str
    quote: str
    time_text: str | None
    source_event_id: str | None
    updates_entry_id: str | None
    learned_at: str
    learned_world_time: str | None
    revision: WireNumber
    correction: str | None


type NewsMark = Literal["pending", "experienced", "skipped"]


@with_config(ConfigDict(extra="allow"))
class PublicNewsEntry(TypedDict):
    entry_id: str
    event_id: str
    batch_id: str
    title: str
    body: str
    time_text: str | None
    published_at: str
    occurred_at: str
    state: NewsMark
    revision: WireNumber


@with_config(ConfigDict(extra="allow"))
class WorldStoryEntries(TypedDict):
    chat: list[ChatStoryEntry]
    news: list[PublicNewsEntry]
    next_before: str | None


@with_config(ConfigDict(extra="allow"))
class LongChatMemory(TypedDict):
    entry_id: str
    character_id: str
    kind: Literal["identity", "preference", "promise", "experience"]
    topic: str
    content: str
    quote: str
    source_kind: Literal["player", "character"]
    source_sender_id: str
    conversation_id: str
    message_id: str
    created_at: str
    world_time: str | None
    state: Literal["active", "forgotten", "superseded"]
    pinned: bool
    revision: WireNumber
    replaces: str | None


@with_config(ConfigDict(extra="allow"))
class LongChatMemorySnapshot(TypedDict):
    enabled: bool
    settings_revision: WireNumber
    items: list[LongChatMemory]
    next_cursor: str | None


@with_config(ConfigDict(extra="allow"))
class WorldNewsStatus(TypedDict):
    enabled: bool
    consented: bool
    revision: WireNumber
    state: Literal["off", "idle", "generating", "ready", "attention"]
    error: str | None
    pending: WireNumber
    batch_total: WireNumber
    batch_processed: WireNumber
    model_available: bool
    model: str | None
