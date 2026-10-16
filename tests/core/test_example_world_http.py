import io
from uuid import uuid4

from fastapi.testclient import TestClient
from livingworld.adapters.http.app import create_app
from livingworld.application.errors import IdempotencyConflictError
from livingworld.application.runtime import RuntimeStatus, ShutdownRequests
from livingworld.domain.identifiers import WorldId
from livingworld.infrastructure.logging import StructuredLogger


def test_example_confirmation_requires_authentication_identity_and_review():
    class Examples:
        calls = []
        failure = None

        async def catalog(self):
            return {"id": "campus-v1", "reviewed_hash": "a" * 64}

        async def create(self, *args):
            self.calls.append(args)
            if self.failure:
                raise self.failure
            return WorldId(uuid4())

    service = Examples()
    app = create_app(
        RuntimeStatus("test", "generation"),
        ShutdownRequests(),
        "synthetic-session-secret",
        lambda: None,
        StructuredLogger(io.StringIO()),
        example_worlds=service,
    )
    url = "/api/v1/world-examples"
    body = {"confirmed": True, "reviewed_hash": "a" * 64, "public_entries": ["school"]}
    headers = {"Authorization": "Bearer synthetic-session-secret"}
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.get(url).status_code == 401
        assert client.post(f"{url}/campus-v1", json=body).status_code == 401
        assert client.get(url, headers=headers).status_code == 200
        assert client.post(f"{url}/campus-v1", headers=headers, json=body).status_code == 400
        headers["X-Request-Id"] = str(uuid4())
        for invalid in (
            {**body, "confirmed": False},
            {**body, "reviewed_hash": "not-a-hash"},
            {**body, "arbitrary_template": {}},
        ):
            assert client.post(f"{url}/campus-v1", headers=headers, json=invalid).status_code == 422
        assert not service.calls
        result = client.post(f"{url}/campus-v1", headers=headers, json=body)
        assert result.status_code == 201 and result.json()["world_id"]
        assert service.calls[0][1].value.hex == headers["X-Request-Id"].replace("-", "")
        assert service.calls[0][2:] == (body["reviewed_hash"], ["school"])
        for failure, code in (
            (ValueError(), "example_preview_changed"),
            (IdempotencyConflictError("world_deleted"), "example_world_deleted"),
            (IdempotencyConflictError("scope_changed"), "example_setup_conflict"),
        ):
            service.failure = failure
            response = client.post(f"{url}/campus-v1", headers=headers, json=body)
            assert response.status_code == 409
            assert response.json()["detail"] == code
