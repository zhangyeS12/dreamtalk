import importlib
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4
import pytest
from livingworld.bootstrap import mobile_host
class MemorySecureHost:
    def __init__(self, root):
        self.root = root
        self.value = "{}"
        self.foreground = True
    def isForeground(self):
        return self.foreground
    def dataDirectory(self):
        return str(self.root)
    def secureRead(self):
        return self.value
    def secureWrite(self, value):
        self.value = value
@pytest.fixture
def runtime(tmp_path):
    host = importlib.reload(mobile_host)
    bridge = MemorySecureHost(tmp_path / "mobile-data")
    yield host, bridge
    if host._thread and host._thread.is_alive():
        host._stop_if_idle()
def setup(**changes):
    value = {"provider_kind": "openai-compatible", "model_id": "test-model", "base_url": "https://example.invalid/v1", "max_billable_input_tokens": 8192, "max_output_tokens": 1024, "streaming": True, "timeout_ms": 120000, "secret": "synthetic-test-credential"}
    return value | changes
@pytest.mark.parametrize("changes", [
    {"base_url": "http://example.invalid/v1"},
    {"base_url": "https://user:password@example.invalid/v1"},
    {"max_billable_input_tokens": True},
    {"streaming": "yes"},
    {"model_id": ""},
    {"secret": ""},
])
def test_reject_invalid_setup(changes):
    with pytest.raises(ValueError, match="mobile_invalid"):
        mobile_host.validate_model(setup(**changes), {})
def test_configuration_document_never_contains_secret():
    value = mobile_host.validate_model(setup(), {})
    document = mobile_host.production_document(value)
    assert "synthetic-test-credential" not in json.dumps(document)
    assert document["providers"][0]["secret_ref"] == value["secret_ref"]
def test_empty_secret_retains_existing_credential():
    previous = mobile_host.validate_model(setup(), {})
    updated = mobile_host.validate_model(setup(secret=""), previous)
    assert updated["secret"] == previous["secret"]
    assert updated["secret_ref"] == previous["secret_ref"]
def test_core_starts_with_private_data_and_authenticates(runtime):
    host, bridge = runtime
    connection = json.loads(host.dispatch("connection", "{}", bridge))["result"]
    def request(path, body=None, token=True):
        headers = {"Authorization": "Bearer " + connection["token"]} if token else {}
        if body is not None: headers["Content-Type"] = "application/json"
        req = Request(connection["endpoint"] + path, data=json.dumps(body).encode() if body is not None else None, headers=headers)
        with urlopen(req, timeout=15) as response:
            return json.load(response)
    assert request("/system/health")["ready"]
    with pytest.raises(HTTPError) as rejection:
        request("/api/v1/worlds", token=False)
    assert rejection.value.code == 401
    assert request("/api/v1/worlds") == []
    req = Request(connection["endpoint"] + "/api/v1/worlds", data=json.dumps({"name": "离线检查世界"}).encode(), headers={"Authorization": "Bearer " + connection["token"], "Content-Type": "application/json", "X-Request-Id": str(uuid4())})
    with urlopen(req, timeout=15) as response: world = json.load(response)
    worlds = request("/api/v1/worlds")
    assert worlds[0]["world_id"] == world["world_id"]
    request("/api/v1/worlds/" + world["world_id"] + "/me/start", {})
    identity = request("/api/v1/worlds/" + world["world_id"] + "/me/player")
    assert identity["player_id"]
    import time
    bridge.foreground = False
    host.dispatch("visibility", "{}", bridge)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try: request("/api/v1/worlds")
        except HTTPError as error:
            assert error.code == 503
            break
        time.sleep(.02)
    else: pytest.fail("Background requests were not fenced")
    bridge.foreground = True
    host.dispatch("visibility", "{}", bridge)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            assert request("/api/v1/worlds")[0]["world_id"] == world["world_id"]
            break
        except HTTPError as error:
            assert error.code == 503
        time.sleep(.02)
    else: pytest.fail("Foreground requests did not resume")
    assert Path(bridge.dataDirectory(), "data/runtime.sqlite3").is_file()
    assert "synthetic-test-credential" not in Path(bridge.dataDirectory(), "llm.json").read_text()

def test_background_barrier_survives_update_lease_expiry(monkeypatch):
    from livingworld.application.update_maintenance import UpdateMaintenance
    barrier = UpdateMaintenance()
    barrier.suspended = True
    barrier._until = 1.0
    monkeypatch.setattr("livingworld.application.update_maintenance.monotonic", lambda: 999.0)
    with barrier.operation() as admitted:
        assert not admitted
    barrier.suspended = False
    with barrier.operation() as admitted:
        assert admitted

@pytest.mark.parametrize("partial", [False, True])
def test_connection_retries_ready_file_replacement(tmp_path, monkeypatch, partial):
    from types import SimpleNamespace
    host = importlib.reload(mobile_host)
    monkeypatch.setattr(host, "_root", tmp_path)
    monkeypatch.setattr(host, "_thread", SimpleNamespace(is_alive=lambda: True))
    monkeypatch.setattr(host, "_start", lambda: None)
    monkeypatch.setattr(host, "_nonce", "test-instance-nonce")
    monkeypatch.setattr(host, "_bootstrap_secret", "s" * 64)
    ready = tmp_path / "runtime/ready.json"
    ready.parent.mkdir()
    ready.write_text(json.dumps({"endpoint": "http://127.0.0.1:12345", "generation": "test-generation", "instance_nonce": host._nonce}))
    original = Path.read_text
    reads = 0
    def replacement(path, *args, **kwargs):
        nonlocal reads
        if path == ready:
            reads += 1
            if reads == 1:
                if partial:
                    return "{"
                raise FileNotFoundError("producer replaced ready file")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", replacement)
    connection = host._connection()
    assert reads == 2
    assert connection["endpoint"] == "http://127.0.0.1:12345"
    assert connection["generation"] == "test-generation"
    assert connection["token"]
