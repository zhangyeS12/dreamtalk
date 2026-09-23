"""Authenticated bounded binary upload, review and world-owned content read boundary."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from livingworld.application.content import ContentConflictError
from livingworld.application.errors import EntityNotFoundError
from livingworld.application.imports import ContentImportError
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


def _view(item: AcceptedWorldContent) -> dict:
    characters = [root for root in item.contents if isinstance(root, CharacterDefinition)]
    collections = [root for root in item.contents if isinstance(root, LoreCollection)]
    return {
        "import_id": str(item.import_id),
        "replaces_import_id": str(item.replaces_import_id) if item.replaces_import_id else None,
        "kind": item.kind,
        "reviewed_hash": item.reviewed_hash,
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
                "content": root.content,
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
            return [_view(item) for item in await service.store.list_imports(WorldId(world_id))]
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

    return router
