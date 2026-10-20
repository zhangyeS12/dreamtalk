"""Additive editor endpoints: accepted-source pages and bounded sparse changes."""

from uuid import UUID

from fastapi import HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator

from livingworld.adapters.http import contracts as wire
from livingworld.adapters.http.world_content import _view
from livingworld.application.content import ContentConflictError
from livingworld.application.content_authoring import EditorEntry, authored_graph
from livingworld.application.content_builder import research_view
from livingworld.application.content_editor_pages import editor_page, merge_editor_patch
from livingworld.application.errors import EntityNotFoundError
from livingworld.application.imports import ContentImportError
from livingworld.application.lore_controls import LoreControls
from livingworld.domain.content.serialization import json_value
from livingworld.domain.identifiers import WorldId


class HeaderPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=16000)
    personality: str | None = Field(default=None, max_length=16000)
    background: str | None = Field(default=None, max_length=16000)
    scenario: str | None = Field(default=None, max_length=16000)
    speech_guidance: str | None = Field(default=None, max_length=16000)
    first_message: str | None = Field(default=None, max_length=16000)
    creator_notes: str | None = Field(default=None, max_length=16000)
    tags: list[str] | None = Field(default=None, max_length=64)
    example_dialogue: list[str] | None = Field(default=None, max_length=32)

    @model_validator(mode="after")
    def no_null_patch(self):
        if any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("editor_patch_null")
        return self


class EntryFields(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    title: str | None = Field(default=None, max_length=300)
    content: str | None = Field(default=None, min_length=1, max_length=16000)
    keywords: list[str] | None = Field(default=None, max_length=64)
    secondary_keywords: list[str] | None = Field(default=None, max_length=64)
    enabled: bool | None = None
    constant: bool | None = None
    advanced: LoreControls | None = None
    selective_logic: str | None = Field(default=None, pattern="^(AND_ANY|AND_ALL|NOT_ANY|NOT_ALL)$")
    priority: int | None = Field(default=None, ge=-1000000, le=1000000)
    order: int | None = Field(default=None, ge=-1000000, le=1000000)

    @model_validator(mode="after")
    def no_null_patch(self):
        if any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("editor_patch_null")
        return self


class EntryPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_entry_id: UUID
    fields: EntryFields


class EditorPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fields: HeaderPatch
    updates: list[EntryPatch] = Field(default_factory=list, max_length=10000)
    removed: list[UUID] = Field(default_factory=list, max_length=10000)
    added: list[EditorEntry] = Field(default_factory=list, max_length=10000)

    @model_validator(mode="after")
    def bounded_patch(self):
        if len(self.model_dump_json().encode("utf-8")) > 4 * 1024 * 1024:
            raise ValueError("editor_patch_too_large")
        return self


def install_editor_pages(router, service, repository):
    async def current(world_id, import_id):
        try:
            return await service.current(WorldId(world_id), import_id)
        except EntityNotFoundError:
            raise HTTPException(404, "content_not_found") from None
        except ContentConflictError:
            raise HTTPException(409, "replacement_target_conflict") from None

    @router.get("/{import_id}/page", response_model=wire.ContentEditorPage)
    async def read_page(world_id: UUID, import_id: UUID, offset: int = Query(default=0, ge=0)):
        item = await current(world_id, import_id)
        try:
            research = next(
                (
                    research_view(json_value(x.extensions["dreamtalk.research"]))
                    for x in item.contents
                    if "dreamtalk.research" in x.extensions
                ),
                None,
            )
            return {**editor_page(item, offset), "research": research}
        except ContentImportError as error:
            raise HTTPException(422, error.code) from None
        except ValueError:
            raise HTTPException(422, "editor_content_limits_exceeded") from None

    @router.post("/{import_id}/preview-changes", response_model=wire.WorldContentItem)
    async def preview_changes(world_id: UUID, import_id: UUID, body: EditorPatchRequest):
        item = await current(world_id, import_id)
        try:
            fields = merge_editor_patch(
                item,
                body.fields.model_dump(exclude_unset=True),
                [
                    (entry.source_entry_id, entry.fields.model_dump(exclude_unset=True))
                    for entry in body.updates
                ],
                body.removed,
                body.added,
            )
            draft = await authored_graph(fields, item, repository)
            pending = await service.prepare_draft(WorldId(world_id), item.kind, draft, import_id)
            return _view(pending.item)
        except ContentConflictError:
            raise HTTPException(409, "replacement_target_conflict") from None
        except (ContentImportError, ValueError):
            raise HTTPException(422, "editor_draft_invalid") from None
