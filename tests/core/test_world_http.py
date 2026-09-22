import io
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from livingworld.adapters.http.app import create_app
from livingworld.application.runtime import RuntimeStatus, ShutdownRequests
from livingworld.application.world_settings import WorldSettings
from livingworld.domain.contracts import API_PROTOCOL
from livingworld.domain.identifiers import WorldId
from livingworld.domain.values import WorldTime
from livingworld.infrastructure.logging import StructuredLogger


class FakeWorldSettings:
    def __init__(self):
        self.calls = []

    async def list_worlds(self):
        return (
            WorldSettings(
                WorldId(uuid4()), "我的世界", WorldTime(2), "running", Decimal("1"), "ready"
            ),
        )

    async def create_world(self, request_id, name):
        self.calls.append((request_id, name))
        return WorldId(uuid4())

    async def pause(self, world_id):
        self.calls.append(("pause", world_id))

    async def resume(self, world_id):
        self.calls.append(("resume", world_id))

    async def change_scale(self, world_id, scale):
        self.calls.append(("scale", world_id, scale))


def test_world_api_is_authenticated_and_requires_request_identity():
    service = FakeWorldSettings()
    app = create_app(
        RuntimeStatus("test", "generation"),
        ShutdownRequests(),
        "session-secret",
        lambda: None,
        StructuredLogger(io.StringIO()),
        world_settings=service,
    )
    prefix = f"/api/v{API_PROTOCOL}"
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.get(f"{prefix}/worlds").status_code == 401
        headers = {"Authorization": "Bearer session-secret"}
        assert client.get(f"{prefix}/worlds", headers=headers).json()[0]["name"] == "我的世界"
        assert (
            client.post(f"{prefix}/worlds", headers=headers, json={"name": "世界"}).status_code
            == 400
        )
        headers["X-Request-Id"] = str(uuid4())
        response = client.post(f"{prefix}/worlds", headers=headers, json={"name": "世界"})
        assert response.status_code == 201
        assert service.calls[0][1] == "世界"
        world_id = response.json()["world_id"]
        assert (
            client.post(f"{prefix}/worlds/{world_id}/clock/pause", headers=headers).status_code
            == 200
        )
        assert (
            client.post(
                f"{prefix}/worlds/{world_id}/clock/scale", headers=headers, json={"scale": "2.5"}
            ).status_code
            == 200
        )
        assert (
            client.post(f"{prefix}/worlds/{world_id}/clock/resume", headers=headers).status_code
            == 200
        )
        assert service.calls[-2][2] == Decimal("2.5")
