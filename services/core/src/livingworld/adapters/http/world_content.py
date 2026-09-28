"""Authenticated bounded binary upload, review and world-owned content read boundary."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from livingworld.application.content import ContentConflictError
from livingworld.application.content_builder import research_view
from livingworld.application.errors import EntityNotFoundError
from livingworld.application.imports import ContentImportError
from livingworld.application.lore_activation import lore_activation_summary
from livingworld.application.world_content import (
    AcceptedWorldContent,
    ImportKind,
    WorldContentService,
)
from livingworld.domain.content.models import CharacterDefinition, LoreCollection, LoreEntry
from livingworld.domain.content.serialization import json_value
from livingworld.domain.contracts import API_PROTOCOL
from livingworld.domain.identifiers import WorldId


class Confirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reviewed_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class LoreExposure(BaseModel):
    model_config = ConfigDict(extra="forbid")
    common: bool


def _view(item: AcceptedWorldContent, common_ids: set[tuple[UUID, UUID]] | None = None) -> dict:
    characters = [root for root in item.contents if isinstance(root, CharacterDefinition)]
    collections = [root for root in item.contents if isinstance(root, LoreCollection)]
    collection_by_id = {root.content_id: root for root in collections}
    return {
        "import_id": str(item.import_id),
        "replaces_import_id": str(item.replaces_import_id) if item.replaces_import_id else None,
        "kind": item.kind,
        "reviewed_hash": item.reviewed_hash,
        "research": next(
            (
                research_view(json_value(root.extensions["dreamtalk.research"]))
                for root in item.contents
                if "dreamtalk.research" in root.extensions
            ),
            None,
        ),
        "characters": [
            {
                "id": str(root.content_id.value),
                "name": root.display_name,
                "description": root.description,
                "personality": root.personality,
                "background": root.background,
                "scenario": root.scenario,
                "speech_guidance": root.speech_guidance,
                "creator_notes": root.creator_notes,
                "tags": list(root.tags),
                "example_dialogue": list(root.example_dialogue),
                "authored_instructions": json_value(root.authored_instructions),
            }
            for root in characters
        ],
        "lorebooks": [
            {"id": str(root.content_id.value), "name": root.name, "description": root.description}
            for root in collections
        ],
        "entries": [
            {
                "id": str(root.content_id.value),
                "title": root.title,
                "keywords": list(root.keywords),
                "secondary_keywords": list(root.secondary_keywords),
                "activation_summary": lore_activation_summary(
                    root, collection_by_id.get(root.collection_id)
                ),
                "content": root.content,
                "enabled": root.enabled,
                "common": (item.import_id, root.content_id.value) in (common_ids or set()),
            }
            for root in item.contents
            if isinstance(root, LoreEntry)
        ],
    }


def world_content_router(service: WorldContentService, authorize) -> APIRouter:
    router = APIRouter(
        prefix=f"/api/v{API_PROTOCOL}/worlds/{{world_id}}/content",
        dependencies=[Depends(authorize)],
    )

    @router.get("")
    async def list_imports(world_id: UUID) -> list[dict]:
        try:
            identity = WorldId(world_id)
            common = {
                (item.import_id, item.entry.content_id.value)
                for item in await service.list_common_lore(identity)
            }
            return [_view(item, common) for item in await service.store.list_imports(identity)]
        except EntityNotFoundError:
            raise HTTPException(404, "world_not_found") from None

    @router.post("/preview")
    async def preview(
        world_id: UUID,
        kind: ImportKind,
        request: Request,
        replaces_import_id: UUID | None = None,
    ) -> dict:
        payload = bytearray()
        async for chunk in request.stream():
            if len(payload) + len(chunk) > 32 * 1024 * 1024:
                raise HTTPException(413, "import_too_large")
            payload.extend(chunk)
        try:
            pending = await service.prepare(
                WorldId(world_id), kind, bytes(payload), replaces_import_id
            )
            return {
                **_view(pending.item),
                "warnings": [
                    {"code": warning.code, "path": warning.path}
                    for warning in pending.preview.warnings
                ],
            }
        except EntityNotFoundError:
            raise HTTPException(404, "world_not_found") from None
        except ContentImportError as error:
            raise HTTPException(422, error.code) from None
        except ContentConflictError:
            raise HTTPException(409, "replacement_target_conflict") from None

    @router.post("/{import_id}/commit")
    async def commit(world_id: UUID, import_id: UUID, body: Confirmation) -> dict:
        try:
            return _view(await service.commit(WorldId(world_id), import_id, body.reviewed_hash))
        except ContentImportError as error:
            raise HTTPException(422, error.code) from None
        except EntityNotFoundError:
            raise HTTPException(404, "world_not_found") from None
        except ContentConflictError:
            raise HTTPException(409, "import_confirmation_conflict") from None

    @router.post("/{import_id}/discard")
    async def discard(world_id: UUID, import_id: UUID) -> dict:
        service.discard(WorldId(world_id), import_id)
        return {"discarded": True}

    @router.put("/{import_id}/entries/{entry_id}/common")
    async def set_common_lore(
        world_id: UUID, import_id: UUID, entry_id: UUID, body: LoreExposure
    ) -> dict:
        try:
            await service.set_common_lore(WorldId(world_id), import_id, entry_id, body.common)
            return {"common": body.common}
        except EntityNotFoundError:
            raise HTTPException(404, "current_lore_entry_not_found") from None

    return router
