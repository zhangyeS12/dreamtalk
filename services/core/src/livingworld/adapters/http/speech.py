"""Authenticated speech settings, declarative card import and committed-message playback."""

import asyncio
from typing import Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from livingworld.adapters.http import contracts as wire
from livingworld.application.errors import EntityNotFoundError
from livingworld.application.llm_config import CredentialUnavailableError
from livingworld.application.speech_contracts import (
    MAX_REFERENCE_BYTES,
    SpeechError,
    SpeechSettings,
    VoiceManifest,
)
from livingworld.domain.contracts import API_PROTOCOL
from livingworld.infrastructure.speech_cards import inspect_audio, read_card, write_card


class SettingsWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    settings: SpeechSettings
    expected_revision: int = Field(strict=True, ge=0)


class BindingWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    card_id: UUID | None


class GenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID


class PreviewQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message_ids: list[UUID] = Field(min_length=1, max_length=128)


class PreviewDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["replace", "keep"]


def speech_router(service, authorize):
    router = APIRouter(
        prefix=f"/api/v{API_PROTOCOL}/worlds/{{world_id}}", dependencies=[Depends(authorize)]
    )

    async def call(operation):
        try:
            return await operation
        except EntityNotFoundError as error:
            raise HTTPException(404, detail=str(error)) from error
        except (httpx.HTTPError, CredentialUnavailableError):
            raise HTTPException(503, detail="speech_service_unavailable") from None
        except SpeechError as error:
            code = str(error)
            status = (
                409
                if code
                in {
                    "speech_edit_conflict",
                    "speech_busy",
                    "speech_request_conflict",
                    "speech_review_pending",
                    "speech_review_conflict",
                }
                else 422
            )
            if code.endswith("not_found"):
                status = 404
            raise HTTPException(status, detail=code) from error

    @router.get("/speech", response_model=wire.SpeechStatus)
    async def status(world_id: UUID):
        return await call(service.status(world_id))

    @router.put("/speech", response_model=wire.SpeechStatus)
    async def save(world_id: UUID, body: SettingsWrite):
        return await call(service.save_settings(world_id, body.settings, body.expected_revision))

    @router.get("/speech/pricing", response_model=wire.SpeechPricing)
    async def pricing(world_id: UUID):
        settings, _ = await call(service.store.settings(world_id))
        if settings.provider != "compshare":
            raise HTTPException(422, detail="speech_cloud_required")
        return await call(service.providers.pricing(settings))

    @router.get("/voices", response_model=wire.VoiceCardPage)
    async def library(world_id: UUID, offset: int = 0):
        if offset < 0 or offset > 1000000:
            raise HTTPException(422, detail="voice_page_invalid")
        return await call(service.store.library(world_id, offset))

    async def parse_upload(world, request, audio_format, name):
        await call(service.store.require_world(world))
        data = bytearray()
        async for chunk in request.stream():
            if len(data) + len(chunk) > MAX_REFERENCE_BYTES + 32768:
                raise HTTPException(413, detail="voice_audio_size_limit")
            data.extend(chunk)
        try:
            if audio_format == "card":
                return await asyncio.to_thread(read_card, bytes(data))
            if audio_format not in {"wav", "mp3"}:
                raise SpeechError("voice_audio_format")
            manifest = VoiceManifest(name=name, reference="reference." + audio_format)
            duration, media = await asyncio.to_thread(
                inspect_audio, bytes(data), manifest.reference
            )
            return manifest, bytes(data), duration, media
        except ValueError as error:
            raise HTTPException(
                422, detail=str(error) if isinstance(error, SpeechError) else "voice_card_invalid"
            ) from error

    @router.post("/voices/preview", response_model=wire.VoiceCardPreview)
    async def preview(
        world_id: UUID, request: Request, audio_format: str = "card", name: str = "音色卡"
    ):
        manifest, _audio, duration, _media = await parse_upload(
            world_id, request, audio_format, name
        )
        return {"manifest": manifest.model_dump(), "duration_ms": duration}

    @router.post("/voices", response_model=wire.VoiceCard)
    async def import_voice(
        world_id: UUID, request: Request, audio_format: str = "card", name: str = "音色卡"
    ):
        manifest, audio, duration, _media = await parse_upload(
            world_id, request, audio_format, name
        )
        return await call(service.store.import_card(world_id, manifest, audio, duration))

    @router.get("/voices/{card_id}/reference")
    async def reference(world_id: UUID, card_id: UUID):
        row = await call(service.store.card(world_id, card_id))
        import json

        filename = json.loads(row.manifest_json)["reference"]
        return Response(
            row.audio,
            media_type="audio/wav" if filename.endswith("wav") else "audio/mpeg",
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    @router.get("/voices/{card_id}/export")
    async def export(world_id: UUID, card_id: UUID):
        row = await call(service.store.card(world_id, card_id))
        import json

        return Response(
            await asyncio.to_thread(write_card, json.loads(row.manifest_json), row.audio),
            media_type="application/zip",
            headers={"Cache-Control": "no-store"},
        )

    @router.delete("/voices/{card_id}", response_model=wire.RemoveVoiceCardResult)
    async def remove(world_id: UUID, card_id: UUID):
        if service.busy:
            raise HTTPException(409, detail="speech_busy")
        await call(service.store.remove_card(world_id, card_id))
        return {"deleted": True}

    @router.get("/character-voices/{root}", response_model=wire.VoiceBindingResult)
    async def binding(world_id: UUID, root: UUID):
        return {"card_id": await call(service.store.binding(world_id, root))}

    @router.put("/character-voices/{root}", response_model=wire.VoiceBindingResult)
    async def bind(world_id: UUID, root: UUID, body: BindingWrite):
        if service.busy:
            raise HTTPException(409, detail="speech_busy")
        await call(service.store.bind(world_id, root, body.card_id))
        return {"card_id": body.card_id}

    @router.post(
        "/conversations/{conversation}/messages/{message}/speech", response_model=wire.SpeechJob
    )
    async def generate(
        world_id: UUID, conversation: UUID, message: UUID, body: GenerationRequest | None = None
    ):
        return await call(
            service.generate(world_id, conversation, message, body.request_id if body else None)
        )

    @router.get("/speech/audio/{identity}")
    async def audio(world_id: UUID, identity: UUID, inspect_signal: bool = False):
        operation = (
            service.audio(world_id, identity, inspect_signal=True)
            if inspect_signal
            else service.audio(world_id, identity)
        )
        return Response(
            await call(operation),
            media_type="audio/wav",
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    @router.post(
        "/conversations/{conversation}/messages/{message}/speech/regenerate",
        response_model=wire.SpeechJob,
    )
    async def regenerate(
        world_id: UUID, conversation: UUID, message: UUID, body: GenerationRequest
    ):
        return await call(
            service.generate(world_id, conversation, message, body.request_id, regenerate=True)
        )

    @router.post(
        "/conversations/{conversation}/speech/previews/query",
        response_model=wire.SpeechPreviewsResult,
    )
    async def previews(world_id: UUID, conversation: UUID, body: PreviewQuery):
        return await call(service.reviews(world_id, conversation, body.message_ids))

    @router.post("/speech/previews/{identity}/completed", response_model=wire.SpeechJob)
    async def completed(world_id: UUID, identity: UUID):
        return await call(service.preview_completed(world_id, identity))

    @router.post("/speech/previews/{identity}/decision", response_model=wire.SpeechJob)
    async def decision(world_id: UUID, identity: UUID, body: PreviewDecision):
        return await call(service.decide(world_id, identity, body.decision == "replace"))

    @router.get("/speech/jobs/{identity}", response_model=wire.SpeechJob)
    async def job(world_id: UUID, identity: UUID):
        return await call(service.job_status(world_id, identity))

    return router
