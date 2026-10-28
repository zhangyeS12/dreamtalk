import asyncio
import secrets
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.middleware.trustedhost import TrustedHostMiddleware

from livingworld.adapters.http.character_activity_setup import character_activity_setup_router
from livingworld.adapters.http.character_evolution import character_evolution_router
from livingworld.adapters.http.chat_conversations import chat_conversation_router
from livingworld.adapters.http.chat_media import chat_media_router, media_error_handler
from livingworld.adapters.http.chat_messages import chat_message_router
from livingworld.adapters.http.chat_paths import chat_path_router
from livingworld.adapters.http.chat_visuals import create_chat_visual_router
from livingworld.adapters.http.content_authoring import content_authoring_router
from livingworld.adapters.http.contracts import CoreHealth as HealthResponse
from livingworld.adapters.http.conversation_memory import conversation_memory_router
from livingworld.adapters.http.developer import developer_router
from livingworld.adapters.http.director import director_router
from livingworld.adapters.http.example_worlds import example_world_router
from livingworld.adapters.http.factions import faction_router
from livingworld.adapters.http.file_exports import file_export_router
from livingworld.adapters.http.long_chat_memory import long_chat_memory_router
from livingworld.adapters.http.offline_contact import (
    offline_contact_router,
    session_visibility_router,
)
from livingworld.adapters.http.player_events import player_events_router
from livingworld.adapters.http.player_persona import player_persona_router
from livingworld.adapters.http.proactive_contact import proactive_contact_router
from livingworld.adapters.http.profiles import profile_router
from livingworld.adapters.http.services import HttpServices
from livingworld.adapters.http.speech import speech_router
from livingworld.adapters.http.update_maintenance import UpdateMaintenanceMiddleware
from livingworld.adapters.http.world_content import world_content_router
from livingworld.adapters.http.world_covers import create_world_cover_router
from livingworld.adapters.http.world_locations import world_locations_router
from livingworld.adapters.http.world_story import world_story_router
from livingworld.adapters.http.world_style import world_style_router
from livingworld.adapters.http.worlds import world_router
from livingworld.application.chat_media import MediaError
from livingworld.application.runtime import RuntimeStatus, ShutdownRequests
from livingworld.application.speech_contracts import SpeechError
from livingworld.domain.contracts import API_PROTOCOL, LOOPBACK_HOST, RequestId
from livingworld.domain.identifiers import WorldId
from livingworld.infrastructure.logging import StructuredLogger


def create_app(
    status: RuntimeStatus,
    shutdown: ShutdownRequests,
    session_token: str,
    initialize: Callable[[], None] | None,
    logger: StructuredLogger,
    allowed_origins: list[str] | None = None,
    *,
    services: HttpServices | None = None,
) -> FastAPI:
    """Build an HTTP embedding; production must use create_product_app."""
    services = services or HttpServices()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:

        if initialize is not None:
            await asyncio.to_thread(initialize)
        status.ready = True
        logger.emit("core", "runtime_initialized")
        try:
            yield
        finally:
            status.ready = False
            logger.emit("core", "runtime_stopped")

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[LOOPBACK_HOST])
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins or [],
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "X-Request-Id", "X-Media-Description"],
    )
    maintenance = services.maintenance
    if maintenance is not None:
        app.add_middleware(UpdateMaintenanceMiddleware, maintenance=services.maintenance)
    bearer = HTTPBearer(auto_error=False)

    def authorize(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ) -> None:
        if credentials is None or not secrets.compare_digest(
            credentials.credentials.encode("utf-8"), session_token.encode("utf-8")
        ):
            raise HTTPException(401, "unauthorized", headers={"WWW-Authenticate": "Bearer"})

    if services.example_worlds is not None:
        app.include_router(
            example_world_router(services.example_worlds, authorize, services.storage_observer)
        )

    if services.content_exports is not None and services.chat_exports is not None:
        app.include_router(
            file_export_router(services.content_exports, services.chat_exports, authorize)
        )

    if services.developer_inspector is not None:
        app.include_router(developer_router(services.developer_inspector, authorize))

    if services.character_activity_setup is not None:
        app.include_router(
            character_activity_setup_router(services.character_activity_setup, authorize)
        )

    if services.world_locations is not None:
        app.include_router(world_locations_router(services.world_locations, authorize))

    if services.world_settings is not None:
        app.include_router(
            world_router(
                services.world_settings,
                authorize,
                services.world_deletion,
                services.storage_observer,
            )
        )

    if services.player_event_feed is not None:
        app.include_router(
            player_events_router(services.player_event_feed, authorize, services.player_onboarding)
        )

    if services.player_persona is not None:
        app.include_router(player_persona_router(services.player_persona, authorize))
    if services.local_profiles is not None:
        app.include_router(profile_router(services.local_profiles, authorize))
    if services.chat_paths is not None:
        app.include_router(chat_path_router(services.chat_paths, authorize))
    if services.world_style is not None:
        app.include_router(world_style_router(services.world_style, authorize))

    if services.world_content is not None:
        app.include_router(
            world_content_router(
                services.world_content, authorize, services.character_activity_setup
            )
        )
        if services.content_builder is not None and services.content_repository is not None:
            app.include_router(
                content_authoring_router(
                    services.world_content,
                    services.content_repository,
                    services.content_builder,
                    authorize,
                    logger,
                )
            )
    if services.character_evolution is not None:
        app.include_router(character_evolution_router(services.character_evolution, authorize))

    if services.chat_conversations is not None:
        app.include_router(chat_conversation_router(services.chat_conversations, authorize))

    if services.chat_messages is not None:
        app.include_router(
            chat_message_router(
                services.chat_messages,
                authorize,
                services.chat_reply,
                services.group_chat_reply,
                services.chat_recall,
            )
        )

    if services.proactive_contact is not None:
        app.include_router(proactive_contact_router(services.proactive_contact, authorize, logger))
    if services.offline_contact is not None:
        app.include_router(offline_contact_router(services.offline_contact, authorize, logger))
        app.include_router(session_visibility_router(services.offline_contact, authorize))

    if services.long_chat_memory is not None:
        app.include_router(long_chat_memory_router(services.long_chat_memory, authorize))
    if services.world_story is not None:
        app.include_router(world_story_router(services.world_story, authorize))
    if services.director is not None:
        app.include_router(director_router(services.director, authorize))
    if services.conversation_memory is not None:
        app.include_router(conversation_memory_router(services.conversation_memory, authorize))

    @app.get("/system/live")
    async def live() -> dict[str, bool]:
        return {"live": True}

    @app.get("/system/health", dependencies=[Depends(authorize)])
    async def health(world_id: UUID | None = None) -> HealthResponse:
        return HealthResponse(
            ready=status.ready and not shutdown.requested,
            core_version=status.core_version,
            api_protocol=API_PROTOCOL,
            generation=status.generation,
            llm_status=(
                status.llm_status_for_world(WorldId(world_id))
                if world_id is not None
                else status.llm_status
            ),
        )

    maintenance = services.maintenance
    if maintenance is not None:

        @app.post("/system/update/prepare", dependencies=[Depends(authorize)])
        async def prepare_update():
            return maintenance.prepare()

        @app.get("/system/update/status", dependencies=[Depends(authorize)])
        async def update_status():
            return maintenance.snapshot()

        @app.post("/system/update/cancel", dependencies=[Depends(authorize)])
        async def cancel_update():
            return maintenance.cancel()

        @app.post("/system/update/verified", dependencies=[Depends(authorize)])
        async def verified_update():
            return maintenance.verified()

    storage_metadata = services.storage_metadata
    if storage_metadata is not None:

        @app.get("/system/storage", dependencies=[Depends(authorize)])
        async def storage_evidence():

            try:
                return await asyncio.to_thread(storage_metadata)
            except Exception:
                raise HTTPException(503, "save_database_unavailable") from None

    @app.post("/system/shutdown", dependencies=[Depends(authorize)])
    async def stop(x_request_id: Annotated[str | None, Header()] = None) -> dict[str, bool | str]:
        try:
            request_id = RequestId.parse(x_request_id or "")
        except ValueError:
            raise HTTPException(400, "valid_request_id_required") from None
        result = shutdown.request(request_id)
        logger.emit("http", "shutdown_requested", trace_id=str(request_id))
        return result

    if services.world_covers is not None:
        app.include_router(create_world_cover_router(services.world_covers, authorize))
    if services.chat_visuals is not None:
        app.include_router(create_chat_visual_router(services.chat_visuals, authorize))
    if services.factions is not None:
        app.include_router(faction_router(services.factions, authorize))
    chat_media = services.chat_media
    if chat_media is not None:
        app.add_exception_handler(MediaError, media_error_handler)
        app.include_router(chat_media_router(services.chat_media, authorize))

        @app.get("/system/media/local-demand", dependencies=[Depends(authorize)])
        async def local_media_demand():
            return {"enabled": await chat_media.store.local_requested()}

    speech = services.speech
    if speech is not None:
        app.include_router(speech_router(services.speech, authorize))

        @app.get("/system/speech/local-demand", dependencies=[Depends(authorize)])
        async def local_speech_demand():
            return {"enabled": await speech.store.local_requested()}

        @app.post("/system/speech/local-repair", dependencies=[Depends(authorize)])
        async def begin_local_speech_repair():

            try:
                return await speech.begin_local_repair()
            except SpeechError:
                raise HTTPException(409, detail="speech_local_repair_busy") from None

        @app.delete("/system/speech/local-repair/{lease}", dependencies=[Depends(authorize)])
        async def end_local_speech_repair(lease: UUID):
            return await speech.end_local_repair(str(lease))

    return app


def create_product_app(
    status: RuntimeStatus,
    shutdown: ShutdownRequests,
    session_token: str,
    initialize: Callable[[], None] | None,
    logger: StructuredLogger,
    allowed_origins: list[str] | None = None,
    *,
    services: HttpServices,
) -> FastAPI:
    """Reject incomplete product wiring before the server can report ready."""
    services.require_product()
    return create_app(
        status, shutdown, session_token, initialize, logger, allowed_origins, services=services
    )
