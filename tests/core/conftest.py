import asyncio
import io

import pytest
from fastapi.testclient import TestClient
from livingworld.adapters.http.app import create_app
from livingworld.application.runtime import RuntimeStatus, ShutdownRequests
from livingworld.infrastructure.logging import StructuredLogger


@pytest.fixture
def runtime_client():
    stream = io.StringIO()
    status = RuntimeStatus("test-version", "test-generation")
    shutdown = ShutdownRequests(event=asyncio.Event())
    app = create_app(status, shutdown, "test-session-token", lambda: None, StructuredLogger(stream))
    with TestClient(app, base_url="http://127.0.0.1") as client:
        yield client, shutdown, stream
