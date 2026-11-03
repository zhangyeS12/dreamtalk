"""Persistent user-authored pack presentation; opening never writes runtime state."""

import asyncio
from hashlib import sha256
from time import monotonic
from uuid import uuid5

from livingworld.application.card_design import PackDesignWrite
from livingworld.application.content_packages import AssetBlobBinding, PackagedBlob
from livingworld.application.errors import EntityNotFoundError
from livingworld.application.world_covers import MAX_IMAGE_BYTES, CoverError
from livingworld.domain.content.identifiers import ContentAssetId


class CardPackService:
    def __init__(self, store, assets, processor):
        self.store, self.assets, self.processor = store, assets, processor
        self._images = {}
        self._lock = asyncio.Lock()

    def _binding(self, pack_id, digest, size):
        return AssetBlobBinding(
            ContentAssetId(uuid5(pack_id, "card-pack-image:" + digest)), digest, size
        )

    def _expire(self):
        self._images = {key: value for key, value in self._images.items() if value[1] > monotonic()}

    async def _materialize(self, pack_id, data, info):
        self._expire()
        image = {**info, "digest": sha256(data).hexdigest(), "size": len(data)}
        persisted = await self.store.find(pack_id) is not None
        if not persisted:
            owners = {key[0] for key in self._images}
            count = sum(key[0] == pack_id for key in self._images)
            if pack_id not in owners and len(owners) >= 8 or count >= 64:
                raise CoverError("card_pack_image_capacity")
        await self.assets.materialize(
            PackagedBlob(self._binding(pack_id, image["digest"], image["size"]), data)
        )
        if persisted:
            await self.store.add_image(pack_id, image)
        else:
            self._images[pack_id, image["digest"]] = image, monotonic() + 3600
        return image

    async def upload(self, pack_id, data):
        if not data or len(data) > MAX_IMAGE_BYTES:
            raise CoverError("cover_image_size_limit")
        async with self._lock:
            info = await asyncio.to_thread(self.processor.inspect, data)
            return await self._materialize(pack_id, data, info)

    async def image(self, pack_id, digest):
        self._expire()
        info = await self.store.image(pack_id, digest)
        if info is None:
            staged = self._images.get((pack_id, digest))
            if staged is None:
                raise EntityNotFoundError("card_pack_image_not_found")
            info = staged[0]
        return await self.assets.read(self._binding(pack_id, digest, info["size"])), info

    async def crop(self, pack_id, digest, crop):
        async with self._lock:
            data, _ = await self.image(pack_id, digest)
            rendered = await asyncio.to_thread(self.processor.render, data, crop, (900, 1286))
            return await self._materialize(
                pack_id, rendered, {"media_type": "image/webp", "width": 900, "height": 1286}
            )

    async def save(self, pack_id, revision, name, subtitle, card_ids, design):
        async with self._lock:
            return await self._save(pack_id, revision, name, subtitle, card_ids, design)

    async def _save(self, pack_id, revision, name, subtitle, card_ids, design):
        design = PackDesignWrite.model_validate(design, strict=True).model_dump()
        infos = {}
        for face in (design["front"], design["back"]):
            for digest in {face["image"], face["source"]} - {None}:
                _, info = await self.image(pack_id, digest)
                infos[digest] = info
        saved = await self.store.save(
            pack_id, revision, name, subtitle, card_ids, design, tuple(infos.values())
        )
        self._images = {key: value for key, value in self._images.items() if key[0] != pack_id}
        return saved

    def discard(self, pack_id):
        self._images = {key: value for key, value in self._images.items() if key[0] != pack_id}
