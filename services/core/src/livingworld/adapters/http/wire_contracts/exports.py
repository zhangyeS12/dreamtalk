"""exports wire DTOs; TypeScript declarations and guards are generated from this source."""

from __future__ import annotations

from typing import Literal, TypedDict

from pydantic import ConfigDict, with_config

from livingworld.adapters.http.wire_contracts.numbers import WireNumber

type ContentExportFormat = Literal[
    "character_card_v2", "character_card_v3", "sillytavern_world_info"
]


@with_config(ConfigDict(extra="allow"))
class FileExportRequestVariant1(TypedDict):
    kind: Literal["content"]
    world_id: str
    item_id: str
    format: ContentExportFormat
    content_id: str
    reviewed_hash: str
    expected_digest: str
    use_regex: bool


@with_config(ConfigDict(extra="allow"))
class FileExportRequestVariant2(TypedDict):
    kind: Literal["chat"]
    world_id: str
    item_id: str
    format: Literal["txt", "json"]
    player_id: str
    expected_digest: str
    through_position: WireNumber


type FileExportRequest = FileExportRequestVariant1 | FileExportRequestVariant2


@with_config(ConfigDict(extra="allow"))
class ContentExportInfoWarningsItem(TypedDict):
    code: str
    path: str


@with_config(ConfigDict(extra="allow"))
class ContentExportInfo(TypedDict):
    filename: str
    digest: str
    size: WireNumber
    warnings: list[ContentExportInfoWarningsItem]


@with_config(ConfigDict(extra="allow"))
class ChatExportInfoPlayer(TypedDict):
    id: str
    name: str


@with_config(ConfigDict(extra="allow"))
class ChatExportInfoCharactersItem(TypedDict):
    id: str
    name: str


@with_config(ConfigDict(extra="allow"))
class ChatExportInfoFilenames(TypedDict):
    txt: str
    json: str


@with_config(ConfigDict(extra="allow"))
class ChatExportInfo(TypedDict):
    world_id: str
    world_name: str
    conversation_id: str
    kind: Literal["direct", "group"]
    player: ChatExportInfoPlayer
    characters: list[ChatExportInfoCharactersItem]
    through_position: WireNumber
    message_count: WireNumber
    title: str
    digest: str
    filenames: ChatExportInfoFilenames
