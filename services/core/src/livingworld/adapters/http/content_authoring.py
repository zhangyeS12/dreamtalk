"""Authenticated native editing and explicit, recoverable research generation."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from livingworld.adapters.http.world_content import _view
from livingworld.application.content import ContentConflictError
from livingworld.application.content_authoring import EditorDraft, authored_graph, editable
from livingworld.application.content_builder import BuilderError, research_view
from livingworld.application.errors import EntityNotFoundError
from livingworld.application.imports import ContentImportError
from livingworld.domain.content.serialization import json_value
from livingworld.domain.contracts import API_PROTOCOL
from livingworld.domain.errors import DomainInvariantError
from livingworld.domain.identifiers import WorldId


class DraftReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    draft: EditorDraft
    replaces_import_id: UUID | None = None
    generation_id: UUID | None = None


class ResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: str = Field(pattern="^(character|lorebook)$")
    query: str = Field(min_length=1, max_length=600)
    token_ceiling: int = Field(ge=1, le=1000000)


def content_authoring_router(service, repository, builder, authorize):
    router = APIRouter(
        prefix=f"/api/v{API_PROTOCOL}/worlds/{{world_id}}/content/editor",
        dependencies=[Depends(authorize)],
    )

    @router.get("/{import_id}")
    async def read_editor(world_id: UUID, import_id: UUID):
        try:
            item = await service.current(WorldId(world_id), import_id)
            research = next(
                (
                    research_view(json_value(x.extensions["dreamtalk.research"]))
                    for x in item.contents
                    if "dreamtalk.research" in x.extensions
                ),
                None,
            )
            return {"draft": editable(item).model_dump(mode="json"), "research": research}
        except EntityNotFoundError:
            raise HTTPException(404, "content_not_found") from None
        except ContentConflictError:
            raise HTTPException(409, "replacement_target_conflict") from None
        except ContentImportError as error:
            raise HTTPException(422, error.code) from None
        except ValueError:
            raise HTTPException(422, "editor_content_limits_exceeded") from None

    @router.post("/preview")
    async def preview_editor(world_id: UUID, body: DraftReview):
        try:
            identity = WorldId(world_id)
            await service.store.require_world(identity)
            previous = (
                await service.current(identity, body.replaces_import_id)
                if body.replaces_import_id
                else None
            )
            if previous and previous.kind != body.draft.kind:
                raise ContentConflictError("editor_kind_mismatch")
            research = None
            if body.generation_id is not None:
                job = await builder.status(identity, body.generation_id)
                if job["state"] != "ready" or job["result"]["draft"]["kind"] != body.draft.kind:
                    raise BuilderError("builder_result_unavailable")
                research = {
                    **job["result"],
                    "generation_id": str(body.generation_id),
                    "user_edited": job["result"]["draft"] != body.draft.model_dump(mode="json"),
                }
            draft = await authored_graph(body.draft, previous, repository, research)
            pending = await service.prepare_draft(
                identity, body.draft.kind, draft, body.replaces_import_id
            )
            return _view(pending.item)
        except EntityNotFoundError:
            raise HTTPException(404, "content_not_found") from None
        except ContentConflictError:
            raise HTTPException(409, "replacement_target_conflict") from None
        except ContentImportError as error:
            raise HTTPException(422, error.code) from None
        except (DomainInvariantError, ValueError):
            raise HTTPException(422, "editor_draft_invalid") from None

    @router.post("/research")
    async def research(world_id: UUID, body: ResearchRequest, request: Request):
        try:
            request_id = UUID(request.headers.get("X-Request-Id", ""))
        except ValueError:
            raise HTTPException(422, "builder_request_id_required") from None
        try:
            return await builder.generate(
                WorldId(world_id), request_id, body.kind, body.query, body.token_ceiling
            )
        except EntityNotFoundError:
            raise HTTPException(404, "world_not_found") from None
        except BuilderError as error:
            raise HTTPException(409, str(error)) from None

    @router.get("/research/{request_id}")
    async def research_status(world_id: UUID, request_id: UUID):
        try:
            return await builder.status(WorldId(world_id), request_id)
        except (EntityNotFoundError, BuilderError):
            raise HTTPException(404, "builder_job_not_found") from None

    return router
