"""Explicit, resumable example installation through the normal product services."""

import asyncio
import json
from hashlib import sha256
from uuid import uuid5

from livingworld.application.errors import IdempotencyConflictError
from livingworld.domain.content.models import LoreEntry
from livingworld.domain.contracts import RequestId
from livingworld.domain.identifiers import WorldId


class ExampleWorldService:
    def __init__(self, template, store, worlds, content, onboarding, locations, activities):
        self.template, self.store = template, store
        self.worlds, self.content = worlds, content
        self.onboarding, self.locations, self.activities = onboarding, locations, activities
        self._lock = asyncio.Lock()
        self.reviewed_hash = sha256(
            json.dumps(template, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()

    async def catalog(self):
        return {
            **self.template,
            "reviewed_hash": self.reviewed_hash,
            "pending": await self.store.pending(self.template["id"]),
        }

    async def create(self, template_id, request_id, reviewed_hash, public_entries):
        template = self.template
        if template_id != template["id"] or reviewed_hash != self.reviewed_hash:
            raise ValueError("example_preview_changed")
        entry_keys = {entry["key"] for entry in template["entries"]}
        if len(set(public_entries)) != len(public_entries) or not set(public_entries) <= entry_keys:
            raise ValueError("example_public_entries_invalid")
        # Example and ordinary world-creation requests cannot share command receipts.
        creation = RequestId(uuid5(request_id.value, f"dreamtalk:example:{template_id}"))
        world = WorldId(uuid5(creation.value, "livingworld:create-world:v1"))
        async with self._lock:
            if await self.worlds.deleted(world):
                raise IdempotencyConflictError("world_deleted")
            complete = await self.store.begin(
                request_id, world, template_id, reviewed_hash, public_entries
            )
            if complete:
                return world
            await self.worlds.create_world(creation, template["name"])
            await self.onboarding.start_at_home(world)
            locations = []
            for index, name in enumerate(template["locations"]):
                locations.append(
                    await self.locations.create(
                        world, name, RequestId(uuid5(world.value, f"example-location:{index}"))
                    )
                )
            book = {
                "name": template["name"],
                "description": template["description"],
                "entries": {
                    str(index): {
                        "uid": index,
                        "key": [],
                        "keysecondary": [],
                        "comment": entry["title"],
                        "content": entry["content"],
                        "constant": True,
                        "order": 100 - index,
                        "disable": False,
                    }
                    for index, entry in enumerate(template["entries"])
                },
            }
            saved = await self._accept(world, "lorebook", "book", book)
            public_titles = {
                entry["title"] for entry in template["entries"] if entry["key"] in public_entries
            }
            for entry in saved.contents:
                if isinstance(entry, LoreEntry):
                    await self.content.set_common_lore(
                        world, saved.import_id, entry.content_id.value, entry.title in public_titles
                    )
            for character in template["characters"]:
                data = {
                    field: character.get(field, "")
                    for field in (
                        "name",
                        "description",
                        "personality",
                        "scenario",
                        "first_mes",
                        "mes_example",
                        "system_prompt",
                        "post_history_instructions",
                    )
                }
                data.update(
                    creator="dreamtalk",
                    character_version="1.0",
                    creator_notes="dreamtalk 原创校园示例，可自由编辑。",
                    alternate_greetings=[],
                    tags=["校园", character["role"]],
                    extensions={},
                )
                saved = await self._accept(
                    world,
                    "character",
                    character["key"],
                    {
                        "spec": "chara_card_v2",
                        "spec_version": "2.0",
                        "data": data,
                    },
                )
                await self.activities.initialize_card(
                    world, saved.import_id, locations[0].location_id
                )
            await self.store.complete(request_id)
            return world

    async def _accept(self, world, kind, key, payload):
        identity = uuid5(world.value, f"example-content:{key}")
        existing = await self.content.store.find(identity)
        if existing is not None:
            return existing
        pending = await self.content.prepare(
            world, kind, json.dumps(payload, ensure_ascii=False).encode(), import_id=identity
        )
        return await self.content.commit(world, identity, pending.item.reviewed_hash)
