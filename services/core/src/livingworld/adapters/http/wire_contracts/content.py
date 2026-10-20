"""content wire DTOs; TypeScript declarations and guards are generated from this source."""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict

from pydantic import ConfigDict, with_config

from livingworld.adapters.http.wire_contracts.numbers import WireNumber
from livingworld.application.lore_controls import LoreControls


@with_config(ConfigDict(extra="allow"))
class WorldContentItemCharactersItem(TypedDict):
    id: str
    name: str
    description: str
    personality: str
    background: str
    scenario: str
    speech_guidance: str
    creator_notes: str
    tags: list[str]
    example_dialogue: list[str]
    authored_instructions: dict[str, object]


@with_config(ConfigDict(extra="allow"))
class WorldContentItemLorebooksItem(TypedDict):
    id: str
    name: str
    description: str


@with_config(ConfigDict(extra="allow"))
class WorldContentItemEntriesItem(TypedDict):
    id: str
    title: str
    keywords: list[str]
    secondary_keywords: NotRequired[list[str]]
    activation_summary: NotRequired[str]
    planning_activation_summary: NotRequired[str]
    content: str
    enabled: bool
    common: bool


@with_config(ConfigDict(extra="allow"))
class WorldContentItemWarningsItem(TypedDict):
    code: str
    path: str


@with_config(ConfigDict(extra="allow"))
class WorldContentItem(TypedDict):
    import_id: str
    replaces_import_id: str | None
    kind: Literal["character", "lorebook"]
    reviewed_hash: str
    characters: list[WorldContentItemCharactersItem]
    lorebooks: list[WorldContentItemLorebooksItem]
    entries: list[WorldContentItemEntriesItem]
    warnings: NotRequired[list[WorldContentItemWarningsItem]]
    research: NotRequired[ContentResearch | None]


@with_config(ConfigDict(extra="allow"))
class ContentEditorEntry(TypedDict):
    source_entry_id: str | None
    title: str
    content: str
    keywords: list[str]
    secondary_keywords: list[str]
    enabled: bool
    constant: bool
    advanced: NotRequired[LoreControls | None]
    selective_logic: Literal["AND_ANY", "AND_ALL", "NOT_ANY", "NOT_ALL"]
    priority: WireNumber
    order: WireNumber


@with_config(ConfigDict(extra="allow"))
class ContentEditorDraft(TypedDict):
    kind: Literal["character", "lorebook"]
    name: str
    description: str
    personality: str
    background: str
    scenario: str
    speech_guidance: str
    first_message: str
    creator_notes: str
    tags: list[str]
    example_dialogue: list[str]
    entries: list[ContentEditorEntry]


@with_config(ConfigDict(extra="allow"))
class ContentResearchSourcesItem(TypedDict):
    id: str
    title: str
    url: str
    excerpt: str
    retrieved_at: str


@with_config(ConfigDict(extra="allow"))
class ContentResearchClaimsItem(TypedDict):
    field: str
    text: str
    sources: list[str]
    status: Literal["sourced", "uncertain", "creative"]


@with_config(ConfigDict(extra="allow"))
class ContentResearch(TypedDict):
    draft: ContentEditorDraft
    query: str
    user_edited: bool
    sources: list[ContentResearchSourcesItem]
    claims: list[ContentResearchClaimsItem]
    conflicts: list[str]
    uncertainties: list[str]


@with_config(ConfigDict(extra="allow"))
class ContentBuilderJob(TypedDict):
    request_id: str
    state: Literal["searching", "generating", "ready", "failed", "interrupted"]
    result: ContentResearch | None
    error: str | None
