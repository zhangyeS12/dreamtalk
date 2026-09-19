import asyncio
from uuid import uuid4

from livingworld.application.runtime import ShutdownRequests
from livingworld.domain.contracts import API_PROTOCOL, RequestId


def test_core_live(runtime_client):
    client, _, _ = runtime_client
    assert client.get("/system/live").json() == {"live": True}


def test_authenticated_health(runtime_client):
    client, _, _ = runtime_client
    response = client.get("/system/health", headers={"Authorization": "Bearer test-session-token"})
    assert response.status_code == 200
    assert response.json() == {
        "ready": True,
        "core_version": "test-version",
        "api_protocol": API_PROTOCOL,
        "generation": "test-generation",
        "llm_status": "unconfigured",
    }


def test_missing_token_rejected(runtime_client):
    client, _, _ = runtime_client
    assert client.get("/system/health").status_code == 401
    assert client.post("/system/shutdown").status_code == 401


def test_wrong_token_rejected(runtime_client):
    client, _, _ = runtime_client
    for path, method in [("/system/health", client.get), ("/system/shutdown", client.post)]:
        assert method(path, headers={"Authorization": "Bearer wrong-token"}).status_code == 401


def test_shutdown_request_id_and_repeated_mutation(runtime_client):
    client, shutdown, _ = runtime_client
    headers = {"Authorization": "Bearer test-session-token"}
    assert client.post("/system/shutdown", headers=headers).status_code == 400
    headers["X-Request-Id"] = str(uuid4())
    first = client.post("/system/shutdown", headers=headers)
    second = client.post("/system/shutdown", headers=headers)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert shutdown.event.is_set()
    assert client.get("/system/health", headers=headers).json()["ready"] is False


def test_request_identity_invokes_mutation_once():
    calls = []
    requests = ShutdownRequests(event=asyncio.Event(), on_request=lambda: calls.append(True))
    identity = RequestId.parse(str(uuid4()))
    assert requests.request(identity) == requests.request(identity)
    assert len(calls) == 1


def test_token_not_in_logs(runtime_client):
    client, _, stream = runtime_client
    client.get("/system/health", headers={"Authorization": "Bearer test-session-token"})
    client.get("/system/health", headers={"Authorization": "Bearer private-wrong-token"})
    assert "test-session-token" not in stream.getvalue()
    assert "private-wrong-token" not in stream.getvalue()


def test_only_system_api_and_host_boundary(runtime_client):
    client, _, _ = runtime_client
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/system/live", headers={"Host": "attacker.example"}).status_code == 400
