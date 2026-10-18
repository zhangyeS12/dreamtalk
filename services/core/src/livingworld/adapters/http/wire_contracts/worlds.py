"""worlds wire DTOs; TypeScript declarations and guards are generated from this source."""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict

from pydantic import ConfigDict, with_config

from livingworld.adapters.http.wire_contracts.numbers import WireNumber


@with_config(ConfigDict(extra="allow"))
class ExampleWorldTemplateEntriesItem(TypedDict):
    key: str
    title: str
    content: str


@with_config(ConfigDict(extra="allow"))
class ExampleWorldTemplateCharactersItem(TypedDict):
    key: str
    name: str
    role: str
    description: str
    personality: str
    scenario: str
    first_mes: str


@with_config(ConfigDict(extra="allow"))
class ExampleWorldTemplatePendingItem(TypedDict):
    request_id: str
    reviewed_hash: str
    public_entries: list[str]


@with_config(ConfigDict(extra="allow"))
class ExampleWorldTemplate(TypedDict):
    id: str
    name: str
    description: str
    reviewed_hash: str
    locations: list[str]
    entries: list[ExampleWorldTemplateEntriesItem]
    characters: list[ExampleWorldTemplateCharactersItem]
    pending: list[ExampleWorldTemplatePendingItem]


type CoverFace = Literal["front", "spine", "back"]


@with_config(ConfigDict(extra="allow"))
class CoverCrop(TypedDict):
    x: WireNumber
    y: WireNumber
    width: WireNumber
    height: WireNumber
    rotation: Literal[0, 90, 180, 270]


@with_config(ConfigDict(extra="allow"))
class CoverImage(TypedDict):
    digest: str
    size: WireNumber
    media_type: str
    width: WireNumber
    height: WireNumber


@with_config(ConfigDict(extra="allow"))
class WorldCoverFacesFront(TypedDict):
    source: CoverImage
    display: CoverImage
    crop: CoverCrop


@with_config(ConfigDict(extra="allow"))
class WorldCoverFacesSpine(TypedDict):
    source: CoverImage
    display: CoverImage
    crop: CoverCrop


@with_config(ConfigDict(extra="allow"))
class WorldCoverFacesBack(TypedDict):
    source: CoverImage
    display: CoverImage
    crop: CoverCrop


@with_config(ConfigDict(extra="allow"))
class WorldCoverFaces(TypedDict):
    front: NotRequired[WorldCoverFacesFront]
    spine: NotRequired[WorldCoverFacesSpine]
    back: NotRequired[WorldCoverFacesBack]


@with_config(ConfigDict(extra="allow"))
class WorldCover(TypedDict):
    world_id: str
    mode: Literal["text", "image"]
    title: str
    show_title: bool
    faces: WorldCoverFaces
    revision: WireNumber


@with_config(ConfigDict(extra="allow"))
class WorldCoverWriteFacesFront(TypedDict):
    source_digest: str
    crop: CoverCrop


@with_config(ConfigDict(extra="allow"))
class WorldCoverWriteFacesSpine(TypedDict):
    source_digest: str
    crop: CoverCrop


@with_config(ConfigDict(extra="allow"))
class WorldCoverWriteFacesBack(TypedDict):
    source_digest: str
    crop: CoverCrop


@with_config(ConfigDict(extra="allow"))
class WorldCoverWriteFaces(TypedDict):
    front: NotRequired[WorldCoverWriteFacesFront]
    spine: NotRequired[WorldCoverWriteFacesSpine]
    back: NotRequired[WorldCoverWriteFacesBack]


@with_config(ConfigDict(extra="allow"))
class WorldCoverWrite(TypedDict):
    mode: Literal["text", "image"]
    title: str
    show_title: bool
    faces: WorldCoverWriteFaces
    expected_revision: WireNumber


type Residency = Literal["normal", "strong", "very_strong"]


@with_config(ConfigDict(extra="allow"))
class ActivityLocation(TypedDict):
    location_id: str
    name: str
    is_home: bool
    parent_id: str | None
    hidden: bool
    is_region: bool
    allowed_character_ids: list[str]
    revision: WireNumber


@with_config(ConfigDict(extra="allow"))
class ActivityCharacter(TypedDict):
    character_id: str
    name: str
    initialized: bool
    root_import_id: str
    initial_location_id: str | None
    current_location_id: str | None
    locked: bool
    residency: Residency
    revision: WireNumber | None
    policy_revision: WireNumber


@with_config(ConfigDict(extra="allow"))
class LocationDraft(TypedDict):
    name: str
    parent_id: str | None
    hidden: bool
    is_region: bool
    allowed_character_ids: list[str]


@with_config(ConfigDict(extra="allow"))
class ActivityCharacterDirectory(TypedDict):
    player_id: str | None
    items: list[ActivityCharacter]
