"""Local book presentation. No canonical world, knowledge or model capabilities."""

import asyncio
from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Protocol
from uuid import uuid5

from livingworld.application.content_packages import (
    AssetBlobBinding,
    ContentAssetStore,
    PackagedBlob,
)
from livingworld.domain.content.identifiers import ContentAssetId
from livingworld.domain.errors import ConcurrencyConflictError
from livingworld.domain.identifiers import WorldId

MAX_IMAGE_BYTES = 10 * 1024 * 1024
FACE_SIZES = {"front": (980, 1430), "back": (980, 1430), "spine": (210, 1430)}


class CoverError(ValueError):
    pass


@dataclass(frozen=True)
class CoverCrop:
    x: float
    y: float
    width: float
    height: float
    rotation: int = 0


class CoverRepository(Protocol):
    async def world_name(self, world: WorldId) -> str: ...
    async def list_covers(self) -> list[dict]: ...
    async def load(self, world: WorldId) -> dict | None: ...
    async def image(self, world: WorldId, digest: str) -> dict: ...
    async def add_image(self, world: WorldId, image: dict) -> None: ...
    async def save(self, world: WorldId, value: dict, revision: int) -> dict: ...


class CoverImageProcessor(Protocol):
    def inspect(self, data: bytes) -> dict: ...
    def render(self, data: bytes, crop: CoverCrop, size: tuple[int, int]) -> bytes: ...


class WorldCoverService:
    def __init__(
        self, repository: CoverRepository, assets: ContentAssetStore, processor: CoverImageProcessor
    ) -> None:
        self._repository = repository
        self._assets = assets
        self._processor = processor
        # Only one bounded decode runs at a time; no full-image data enters the event loop.
        self._image_lock = asyncio.Lock()

    def _binding(self, world, digest, size):
        return AssetBlobBinding(ContentAssetId(uuid5(world.value, "cover:" + digest)), digest, size)

    async def list_covers(self):
        return await self._repository.list_covers()

    async def load(self, world):
        name = await self._repository.world_name(world)
        return await self._repository.load(world) or {
            "world_id": str(world.value),
            "mode": "text",
            "title": name,
            "show_title": True,
            "faces": {},
            "revision": 0,
        }

    async def _store(self, world, data, info):
        image = {**info, "digest": sha256(data).hexdigest(), "size": len(data)}
        await self._assets.materialize(
            PackagedBlob(self._binding(world, image["digest"], image["size"]), data)
        )
        await self._repository.add_image(world, image)
        return image

    async def upload(self, world, data):
        await self._repository.world_name(world)
        if not data or len(data) > MAX_IMAGE_BYTES:
            raise CoverError("cover_image_size_limit")
        async with self._image_lock:
            info = await asyncio.to_thread(self._processor.inspect, data)
            return await self._store(world, data, info)

    async def image(self, world, digest):
        image = await self._repository.image(world, digest)
        return await self._assets.read(self._binding(world, digest, image["size"])), image

    async def save(self, world, mode, title, show_title, faces, revision):
        await self._repository.world_name(world)
        if mode == "image" and "front" not in faces:
            raise CoverError("cover_front_required")
        previous = await self.load(world)
        if previous["revision"] != revision:
            raise ConcurrencyConflictError("cover_edit_conflict")
        result = {}
        async with self._image_lock:
            for face, (digest, crop) in faces.items():
                source = await self._repository.image(world, digest)
                old = previous["faces"].get(face)
                if old and old["source"]["digest"] == digest and old["crop"] == asdict(crop):
                    result[face] = old
                    continue
                data = await self._assets.read(self._binding(world, digest, source["size"]))
                rendered = await asyncio.to_thread(
                    self._processor.render, data, crop, FACE_SIZES[face]
                )
                width, height = FACE_SIZES[face]
                display = await self._store(
                    world,
                    rendered,
                    {
                        "media_type": "image/webp",
                        "width": width,
                        "height": height,
                    },
                )
                result[face] = {"source": source, "display": display, "crop": asdict(crop)}
        return await self._repository.save(
            world,
            {
                "mode": mode,
                "title": title.strip(),
                "show_title": show_title,
                "faces": result,
            },
            revision,
        )
