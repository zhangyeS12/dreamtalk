"""Card-library DTO authority. Presentation never enters character prompts."""

from typing import Literal, NotRequired, TypedDict

from livingworld.adapters.http.wire_contracts.content import ContentEditorDraft, WorldContentItem
from livingworld.adapters.http.wire_contracts.numbers import WireNumber
from livingworld.adapters.http.wire_contracts.worlds import CoverCrop

type CardMaterial = Literal["matte", "metal", "gloss", "holo"]
type CardLayerKind = Literal["name", "role", "text", "sticker"]


class CardLayer(TypedDict):
    anchor: NotRequired[Literal["center", "start"]]
    id: str
    kind: CardLayerKind
    text: str
    x: float
    y: float
    size: float
    rotation: float
    opacity: float
    color: str


class CardFaceDesign(TypedDict):
    layout: Literal["portrait", "notes"]
    color: str
    accent: str
    material: CardMaterial
    frame: bool
    image_digest: str | None
    source_digest: str | None
    crop: CoverCrop | None
    image_opacity: float
    layers: list[CardLayer]


class CardDesign(TypedDict):
    version: Literal[1]
    display_name: str
    subtitle: str
    glyph: str
    front: CardFaceDesign
    back: CardFaceDesign


class LibraryCardItem(TypedDict):
    card_id: str
    name: str
    revision: WireNumber
    design: CardDesign | None
    world_ids: list[str]


class LibraryCardRead(TypedDict):
    card: LibraryCardItem
    draft: ContentEditorDraft


class LibraryCardPreview(TypedDict):
    preview_id: str
    card_id: str
    expected_revision: WireNumber
    reviewed_hash: str
    content: WorldContentItem
    shared: NotRequired[bool]
    design: NotRequired[CardDesign | None]
    image_count: NotRequired[int]


class LibraryCardJoinPreview(TypedDict):
    card_id: str
    source_revision: WireNumber
    content: WorldContentItem
