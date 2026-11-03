"""Pack presentation DTO authority; a pack holds references, never role copies."""

from typing import Literal, TypedDict

from livingworld.adapters.http.wire_contracts.card_library import CardLayer, CardMaterial
from livingworld.adapters.http.wire_contracts.numbers import WireNumber
from livingworld.adapters.http.wire_contracts.worlds import CoverCrop


class PackFaceDesign(TypedDict):
    color: str
    accent: str
    material: CardMaterial
    frame: bool
    glyph: str
    image: str | None
    source: str | None
    crop: CoverCrop | None
    imageOpacity: float
    layers: list[CardLayer]


class PackDesign(TypedDict):
    version: Literal[1]
    front: PackFaceDesign
    back: PackFaceDesign


class CharacterPack(TypedDict):
    id: str
    name: str
    subtitle: str
    cardIds: list[str]
    design: PackDesign
    revision: WireNumber
