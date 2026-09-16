import secrets
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict
from starlette.middleware.trustedhost import TrustedHostMiddleware

from livingworld.application.runtime import RuntimeStatus, ShutdownRequests
from livingworld.domain.contracts import API_PROTOCOL, LOOPBACK_HOST, RequestId
from livingworld.infrastructure.logging import StructuredLogger


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ready: bool
    core_version: str
    api_protocol: int
    generation: str


def create_app(
    status: RuntimeStatus,
    shutdown: ShutdownRequests,
    session_token: str,
    initialize: Callable[[], None],
    logger: StructuredLogger,
    allowed_origins: list[str] | None = None,
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
