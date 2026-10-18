"""chat wire DTOs; TypeScript declarations and guards are generated from this source."""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict

from pydantic import ConfigDict, with_config

from livingworld.adapters.http.wire_contracts.media import ChatMediaAttachment
from livingworld.adapters.http.wire_contracts.numbers import WireNumber


@with_config(ConfigDict(extra="allow"))
class ConversationMemoryContent(TypedDict):
    base_revision: WireNumber
    through_position: WireNumber
    source_ids: list[str]
    content: str | None
    user_edited: bool
    created_at_utc: str


@with_config(ConfigDict(extra="allow"))
class ConversationMemoryRevision(TypedDict):
    base_revision: WireNumber
    through_position: WireNumber
    source_ids: list[str]
    content: str
    user_edited: bool
    created_at_utc: str
    revision: WireNumber


@with_config(ConfigDict(extra="allow"))
class ConversationMemoryDraft(TypedDict):
    base_revision: WireNumber
    through_position: WireNumber
    source_ids: list[str]
    content: str | None
    user_edited: bool
    created_at_utc: str
    draft_id: str
    mode: Literal["summarize", "correct"]
    state: Literal["generating", "ready", "previewed", "committed", "failed", "interrupted"]
    reviewed_hash: str | None
    committed_revision: WireNumber | None
    error: str | None


@with_config(ConfigDict(extra="allow"))
class ConversationMemorySnapshot(TypedDict):
    current: ConversationMemoryRevision | None
    draft: ConversationMemoryDraft | None
    latest_position: WireNumber
    model_available: bool


@with_config(ConfigDict(extra="allow"))
class ConversationMemorySources(TypedDict):
    memory: ConversationMemoryRevision
    sources: list[ChatMessage]


@with_config(ConfigDict(extra="allow"))
class ChatMessage(TypedDict):
    message_id: str
    turn_id: str
    conversation_id: str
    position: WireNumber
    sender_kind: Literal["player", "character"]
    sender_id: str
    text: str
    created_at_utc: str
    story_sent_at_utc: NotRequired[str | None]
    media: NotRequired[ChatMediaAttachment | None]


@with_config(ConfigDict(extra="allow"))
class ChatReplyProgressVariant1(TypedDict):
    kind: Literal["preparing", "selecting"]


@with_config(ConfigDict(extra="allow"))
class ChatReplyProgressVariant2(TypedDict):
    kind: Literal["replying"]
    speaker_id: str


@with_config(ConfigDict(extra="allow"))
class ChatReplyProgressVariant3(TypedDict):
    kind: Literal["delta"]
    speaker_id: str
    text: str


@with_config(ConfigDict(extra="allow"))
class ChatReplyProgressVariant4(TypedDict):
    kind: Literal["message"]
    message: ChatMessage


type ChatReplyProgress = (
    ChatReplyProgressVariant1
    | ChatReplyProgressVariant2
    | ChatReplyProgressVariant3
    | ChatReplyProgressVariant4
)


@with_config(ConfigDict(extra="allow"))
class ChatMessagePage(TypedDict):
    items: list[ChatMessage]
    next_before_position: WireNumber | None


@with_config(ConfigDict(extra="allow"))
class ChatHistoryMatches(TypedDict):
    items: list[ChatMessage]
    scanned_count: WireNumber
    skipped_count: WireNumber
    next_before_position: WireNumber | None


@with_config(ConfigDict(extra="allow"))
class PendingPlayerSend(TypedDict):
    turn_id: str
    token_ceiling: WireNumber
    status: Literal["pending"]
    message: ChatMessage


@with_config(ConfigDict(extra="allow"))
class DirectTurnView(TypedDict):
    turn_id: str
    state: Literal["pending", "claimed", "completed"]
    token_ceiling: WireNumber
    player_message: ChatMessage
    reply: ChatMessage | None


@with_config(ConfigDict(extra="allow"))
class GroupTurnView(TypedDict):
    turn_id: str
    state: Literal["pending", "claimed", "completed"]
    token_ceiling: WireNumber
    player_message: ChatMessage
    replies: list[ChatMessage]


@with_config(ConfigDict(extra="allow"))
class ReplyRecoveryView(TypedDict):
    source_turn_id: str
    attempt_turn_id: str
    state: Literal[
        "pending", "running", "completed", "failed", "unknown", "interrupted", "has_replies"
    ]
    token_ceiling: WireNumber
    can_generate: bool
    can_create: bool
    reason: str | None


@with_config(ConfigDict(extra="allow"))
class ChatReplyAvailability(TypedDict):
    available: bool
    input_token_reservation: NotRequired[WireNumber | None]
    max_output_tokens: NotRequired[WireNumber | None]


@with_config(ConfigDict(extra="allow"))
class ChatContextReportsReportsItemCategoriesItem(TypedDict):
    label: str
    included: WireNumber
    omitted: WireNumber


@with_config(ConfigDict(extra="allow"))
class ChatContextReportsReportsItemReferencesItem(TypedDict):
    kind: str
    id: str | None
    text: str
    source: str
    time: str
    source_kind: str
    source_sender_id: str


@with_config(ConfigDict(extra="allow"))
class ChatContextReportsReportsItem(TypedDict):
    speaker_id: str
    version: WireNumber
    input_upper_bound: WireNumber
    output_upper_bound: WireNumber
    remaining_before_call: WireNumber
    retrieval: str
    context_reduced: bool
    references_omitted: WireNumber
    categories: list[ChatContextReportsReportsItemCategoriesItem]
    references: list[ChatContextReportsReportsItemReferencesItem]


@with_config(ConfigDict(extra="allow"))
class ChatContextReports(TypedDict):
    turn_id: str
    reports: list[ChatContextReportsReportsItem]
