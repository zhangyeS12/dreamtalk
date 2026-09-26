import secrets
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict
from starlette.middleware.trustedhost import TrustedHostMiddleware

from livingworld.application.chat_conversations import ChatConversationService
from livingworld.application.chat_messages import ChatMessageService
from livingworld.application.chat_reply import DirectChatReplyService
from livingworld.application.developer_inspector import DeveloperInspectorService
from livingworld.application.group_chat_reply import GroupChatReplyService
from livingworld.application.local_profile import LocalProfileStore
from livingworld.application.player_event_feed import PlayerEventFeedService
from livingworld.application.player_onboarding import LocalPlayerOnboardingService
from livingworld.application.runtime import RuntimeStatus, ShutdownRequests
from livingworld.application.world_content import WorldContentService
from livingworld.application.world_settings import WorldSettingsService
from livingworld.domain.contracts import API_PROTOCOL, LOOPBACK_HOST, RequestId
from livingworld.infrastructure.logging import StructuredLogger


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ready: bool
    core_version: str
    api_protocol: int
    generation: str
    llm_status: str


def create_app(
    status: RuntimeStatus,
    shutdown: ShutdownRequests,
    session_token: str,
    initialize: Callable[[], None],
    logger: StructuredLogger,
    allowed_origins: list[str] | None = None,
    developer_inspector: DeveloperInspectorService | None = None,
    world_settings: WorldSettingsService | None = None,
    player_event_feed: PlayerEventFeedService | None = None,
    local_profiles: LocalProfileStore | None = None,
    world_content: WorldContentService | None = None,
    player_onboarding: LocalPlayerOnboardingService | None = None,
    chat_conversations: ChatConversationService | None = None,
    chat_messages: ChatMessageService | None = None,
    chat_reply: DirectChatReplyService | None = None,
    group_chat_reply: GroupChatReplyService | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        import asyncio

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
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "X-Request-Id"],
    )
    bearer = HTTPBearer(auto_error=False)

    def authorize(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ) -> None:
        if credentials is None or not secrets.compare_digest(
            credentials.credentials.encode("utf-8"), session_token.encode("utf-8")
        ):
            raise HTTPException(401, "unauthorized", headers={"WWW-Authenticate": "Bearer"})

    if developer_inspector is not None:
        from livingworld.adapters.http.developer import developer_router

        app.include_router(developer_router(developer_inspector, authorize))

    if world_settings is not None:
        from livingworld.adapters.http.worlds import world_router

        app.include_router(world_router(world_settings, authorize))

    if player_event_feed is not None:
        from livingworld.adapters.http.player_events import player_events_router

        app.include_router(player_events_router(player_event_feed, authorize, player_onboarding))

    if local_profiles is not None:
        from livingworld.adapters.http.profiles import profile_router

        app.include_router(profile_router(local_profiles, authorize))

    if world_content is not None:
        from livingworld.adapters.http.world_content import world_content_router

        app.include_router(world_content_router(world_content, authorize))

    if chat_conversations is not None:
        from livingworld.adapters.http.chat_conversations import chat_conversation_router

        app.include_router(chat_conversation_router(chat_conversations, authorize))

    if chat_messages is not None:
        from livingworld.adapters.http.chat_messages import chat_message_router

        app.include_router(
            chat_message_router(chat_messages, authorize, chat_reply, group_chat_reply)
        )

    @app.get("/system/live")
    async def live() -> dict[str, bool]:
        return {"live": True}

    @app.get("/system/health", dependencies=[Depends(authorize)])
    async def health() -> HealthResponse:
        return HealthResponse(
            ready=status.ready and not shutdown.requested,
            core_version=status.core_version,
            api_protocol=API_PROTOCOL,
            generation=status.generation,
            llm_status=status.llm_status,
        )

    @app.post("/system/shutdown", dependencies=[Depends(authorize)])
    async def stop(x_request_id: Annotated[str | None, Header()] = None) -> dict[str, bool | str]:
        try:
            request_id = RequestId.parse(x_request_id or "")
        except ValueError:
            raise HTTPException(400, "valid_request_id_required") from None
        result = shutdown.request(request_id)
        logger.emit("http", "shutdown_requested", trace_id=str(request_id))
        return result

    return app
