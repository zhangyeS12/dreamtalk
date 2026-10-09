"""Authenticated, read-only export preview and file downloads."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.responses import Response, StreamingResponse

from livingworld.application.content import ContentConflictError
from livingworld.application.errors import EntityNotFoundError
from livingworld.application.exports import ContentExportError, ExportTarget
from livingworld.application.file_exports import attachment_headers
from livingworld.domain.contracts import API_PROTOCOL
from livingworld.domain.errors import DomainInvariantError
from livingworld.domain.identifiers import ConversationId, WorldId

Digest = Annotated[str, Query(pattern=r"^[a-f0-9]{64}$")]
ExportFormat = Literal["character_card_v2", "character_card_v3", "sillytavern_world_info"]


def file_export_router(content_exports, chat_exports, authorize):
    router = APIRouter(
        prefix=f"/api/v{API_PROTOCOL}/worlds/{{world_id}}", dependencies=[Depends(authorize)]
    )

    async def content_file(world_id, import_id, reviewed_hash, format, content_id, use_regex):
        try:
            return await content_exports.prepare(
                WorldId(world_id),
                import_id,
                reviewed_hash,
                ExportTarget(format),
                content_id,
                use_regex,
            )
        except EntityNotFoundError:
            raise HTTPException(404, "export_content_unavailable") from None
        except ContentConflictError:
            raise HTTPException(409, "export_content_changed") from None
        except ContentExportError as error:
            raise HTTPException(422, error.code) from None
        except (DomainInvariantError, KeyError, ValueError):
            raise HTTPException(422, "export_content_invalid") from None

    @router.get("/content/{import_id}/export/info")
    async def content_info(
        world_id: UUID,
        import_id: UUID,
        reviewed_hash: Digest,
        format: ExportFormat,
        content_id: UUID,
        use_regex: bool = False,
    ):
        file = await content_file(world_id, import_id, reviewed_hash, format, content_id, use_regex)
        return {
            "filename": file.filename,
            "digest": file.digest,
            "size": len(file.payload),
            "warnings": [{"code": warning.code, "path": warning.path} for warning in file.warnings],
        }

    @router.get("/content/{import_id}/export")
    async def content_download(
        world_id: UUID,
        import_id: UUID,
        reviewed_hash: Digest,
        expected_digest: Digest,
        format: ExportFormat,
        content_id: UUID,
        use_regex: bool = False,
    ):
        file = await content_file(world_id, import_id, reviewed_hash, format, content_id, use_regex)
        if file.digest != expected_digest:
            raise HTTPException(409, "export_content_changed")
        return Response(
            file.payload, media_type=file.media_type, headers=attachment_headers(file.filename)
        )

    async def chat_snapshot(world_id, conversation_id, through=None, player=None):
        try:
            return await chat_exports.snapshot(
                ConversationId(WorldId(world_id), conversation_id), through, player
            )
        except EntityNotFoundError:
            raise HTTPException(404, "export_conversation_unavailable") from None

    @router.get("/conversations/{conversation_id}/export/info")
    async def chat_info(world_id: UUID, conversation_id: UUID):
        snapshot = await chat_snapshot(world_id, conversation_id)
        return {
            **snapshot.metadata(),
            "digest": snapshot.digest,
            "title": snapshot.title,
            "filenames": {format: snapshot.filename(format) for format in ("txt", "json")},
        }

    @router.get("/conversations/{conversation_id}/export")
    async def chat_download(
        world_id: UUID,
        conversation_id: UUID,
        format: Literal["txt", "json"],
        player_id: UUID,
        expected_digest: Digest,
        through_position: Annotated[int, Query(ge=0, le=9223372036854775807)],
    ):
        snapshot = await chat_snapshot(world_id, conversation_id, through_position, player_id)
        if snapshot.digest != expected_digest:
            raise HTTPException(409, "export_transcript_changed")
        return StreamingResponse(
            chat_exports.stream(snapshot, format),
            media_type="application/json" if format == "json" else "text/plain",
            headers=attachment_headers(snapshot.filename(format)),
        )

    return router
