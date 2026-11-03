"""Shared bounded card presentation schema for edits and portable shares."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ImageCropWrite(Strict):
    x: float = Field(ge=0, le=100)
    y: float = Field(ge=0, le=100)
    width: float = Field(gt=0, le=100)
    height: float = Field(gt=0, le=100)
    rotation: Literal[0, 90, 180, 270] = 0


class LayerWrite(Strict):
    anchor: Literal["center", "start"] = "start"
    id: str = Field(min_length=1, max_length=64)
    kind: Literal["name", "role", "text", "sticker"]
    text: str = Field(max_length=300)
    x: float = Field(ge=0, le=100)
    y: float = Field(ge=0, le=100)
    size: float = Field(ge=8, le=128)
    rotation: float = Field(ge=-720, le=720)
    opacity: float = Field(ge=0, le=100)
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")


class FaceWrite(Strict):
    layout: str = Field(pattern="^(portrait|notes)$")
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    accent: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    material: Literal["matte", "metal", "gloss", "holo"]
    frame: bool = Field(strict=True)
    image_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    source_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    crop: ImageCropWrite | None = None
    image_opacity: float = Field(ge=0, le=100)
    layers: list[LayerWrite] = Field(max_length=24)


class DesignWrite(Strict):
    version: int = Field(ge=1, le=1, strict=True)
    display_name: str = Field(max_length=60)
    subtitle: str = Field(max_length=120)
    glyph: str = Field(max_length=8)
    front: FaceWrite
    back: FaceWrite


class PackFaceWrite(Strict):
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    accent: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    material: Literal["matte", "metal", "gloss", "holo"]
    frame: bool = Field(strict=True)
    glyph: str = Field(max_length=8)
    image: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    source: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    crop: ImageCropWrite | None = None
    imageOpacity: float = Field(ge=0, le=100)
    layers: list[LayerWrite] = Field(max_length=24)


class PackDesignWrite(Strict):
    version: Literal[1]
    front: PackFaceWrite
    back: PackFaceWrite


def referenced_images(design):
    return (
        sorted(
            {
                face[key]
                for face in (design["front"], design["back"])
                for key in ("image_digest", "source_digest")
                if face.get(key)
            }
        )
        if design
        else []
    )
