"""Small operation results shared by server annotations and client response guards."""

from __future__ import annotations

from typing import TypedDict

from pydantic import ConfigDict, with_config

from livingworld.adapters.http.wire_contracts.chat import ChatMessage
from livingworld.adapters.http.wire_contracts.content import ContentEditorDraft, ContentResearch
from livingworld.adapters.http.wire_contracts.media import SpeechPreviewJob, StickerEntry
from livingworld.adapters.http.wire_contracts.numbers import WireNumber
from livingworld.domain.participants import PlayerAvailability


@with_config(ConfigDict(extra="allow"))
class MediaUsageResult(TypedDict):
    utc_day: str
    caption_calls: WireNumber


@with_config(ConfigDict(extra="allow"))
class StickersResult(TypedDict):
    items: list[StickerEntry]
    has_more: bool


@with_config(ConfigDict(extra="allow"))
class EditStickerResult(TypedDict):
    saved: bool


@with_config(ConfigDict(extra="allow"))
class RemoveStickerResult(TypedDict):
    removed: bool


@with_config(ConfigDict(extra="allow"))
class CaptionMediaResult(TypedDict):
    description: str


@with_config(ConfigDict(extra="allow"))
class VoiceBindingResult(TypedDict):
    card_id: str | None


@with_config(ConfigDict(extra="allow"))
class RemoveVoiceCardResult(TypedDict):
    deleted: bool


@with_config(ConfigDict(extra="allow"))
class SpeechPreviewsResult(TypedDict):
    items: list[SpeechPreviewJob]


@with_config(ConfigDict(extra="allow"))
class SetCommonLoreResult(TypedDict):
    common: bool


@with_config(ConfigDict(extra="allow"))
class ConversationMemoryDraftSourcesResult(TypedDict):
    items: list[ChatMessage]


@with_config(ConfigDict(extra="allow"))
class CreateReplyRecoveryResult(TypedDict):
    turn_id: str
    token_ceiling: WireNumber


@with_config(ConfigDict(extra="allow"))
class ContentEditorResult(TypedDict):
    draft: ContentEditorDraft
    research: ContentResearch | None


@with_config(ConfigDict(extra="allow"))
class ContentEditorPage(TypedDict):
    draft: ContentEditorDraft
    research: ContentResearch | None
    total_entries: int
    offset: int
    next_offset: int | None


@with_config(ConfigDict(extra="allow"))
class DiscardWorldContentResult(TypedDict):
    discarded: bool


@with_config(ConfigDict(extra="allow"))
class InitializeCharacterActivityResult(TypedDict):
    character_id: str
    initialized: bool


@with_config(ConfigDict(extra="allow"))
class CreateFactionResult(TypedDict):
    faction_id: str


@with_config(ConfigDict(extra="allow"))
class DeleteWorldResult(TypedDict):
    deleted: bool
    asset_cleanup_pending: bool


@with_config(ConfigDict(extra="allow"))
class DissolveGroupResult(TypedDict):
    dissolved: bool


@with_config(ConfigDict(extra="allow"))
class CreateWorldResult(TypedDict):
    world_id: str


@with_config(ConfigDict(extra="allow"))
class PauseProductWorldResult(TypedDict):
    ok: bool


@with_config(ConfigDict(extra="allow"))
class SetPlayerAvailabilityResult(TypedDict):
    availability: PlayerAvailability
    presence_revision: WireNumber


@with_config(ConfigDict(extra="allow"))
class BindPlayerResult(TypedDict):
    player_id: str


@with_config(ConfigDict(extra="allow"))
class MarkConversationReadResult(TypedDict):
    read: bool


@with_config(ConfigDict(extra="allow"))
class ScheduleTriggerResult(TypedDict):
    trigger_id: str


@with_config(ConfigDict(extra="allow"))
class RecordMemoryResult(TypedDict):
    memory_id: str
