import io
from uuid import uuid4

from fastapi.testclient import TestClient
from livingworld.adapters.http.app import create_app
from livingworld.application.local_profile import LocalProfile
from livingworld.application.runtime import RuntimeStatus, ShutdownRequests
from livingworld.domain.contracts import API_PROTOCOL
from livingworld.domain.errors import ConcurrencyConflictError
from livingworld.domain.values import Revision
from livingworld.infrastructure.logging import StructuredLogger


class Profiles:
    def __init__(self):
        self.items = {}

    async def load(self, world_id=None):
        return self.items.get(world_id, LocalProfile())

    async def save(self, profile, world_id=None):
        previous = await self.load(world_id)
        if previous.revision != profile.revision:
            raise ConcurrencyConflictError("profile_edit_conflict")
        result = LocalProfile(
            profile.name, profile.description, Revision(profile.revision.value + 1)
        )
        self.items[world_id] = result
        return result


def test_profile_http_auth_validation_conflict_and_scope():
    logs = io.StringIO()
    app = create_app(
        RuntimeStatus("test", "generation"),
        ShutdownRequests(),
        "secret",
        lambda: None,
        StructuredLogger(logs),
        local_profiles=Profiles(),
    )
    root = f"/api/v{API_PROTOCOL}"
    headers = {"Authorization": "Bearer secret"}
    body = {"name": "名字", "description": "private-profile-canary", "expected_revision": 0}
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.get(f"{root}/me/profile").status_code == 401
        assert client.post(f"{root}/me/profile", json=body).status_code == 401
        saved = client.post(f"{root}/me/profile", headers=headers, json=body)
        assert saved.status_code == 200
        assert saved.json()["revision"] == 1
        assert client.post(f"{root}/me/profile", headers=headers, json=body).status_code == 409
        invalid = {**body, "expected_revision": True}
        assert client.post(f"{root}/me/profile", headers=headers, json=invalid).status_code == 422
        world_path = f"{root}/worlds/{uuid4()}/me/profile"
        assert client.get(world_path, headers=headers).json()["description"] == ""
        assert client.post(world_path, headers=headers, json=body).status_code == 200
    assert "private-profile-canary" not in logs.getvalue()
