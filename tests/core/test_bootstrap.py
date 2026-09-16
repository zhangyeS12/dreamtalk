import json
import os
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from livingworld.bootstrap.reader import derive_session, read_bootstrap
from livingworld.domain.contracts import API_PROTOCOL


def bootstrap_input(tmp_path):
    return {
        "bootstrap_secret": "private-bootstrap-secret-" * 4,
        "instance_nonce": str(uuid4()),
        "protocol_min": API_PROTOCOL,
        "protocol_max": API_PROTOCOL,
        "data_dir": str(tmp_path / "data"),
        "log_dir": str(tmp_path / "logs"),
    }


def test_bootstrap_reader_consumes_file(tmp_path):
    path = tmp_path / "bootstrap.json"
    payload = bootstrap_input(tmp_path)
    path.write_text(json.dumps(payload))
    config = read_bootstrap(path)
    assert config.bootstrap_secret.get_secret_value() == payload["bootstrap_secret"]
    assert not path.exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows parent watcher only")
def test_parent_exit_shuts_core(tmp_path):
    payload = bootstrap_input(tmp_path)
    path = tmp_path / "bootstrap.json"
    path.write_text(json.dumps(payload))
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "livingworld.bootstrap",
            "--desktop",
            "--bootstrap-path",
            str(path),
            "--parent-pid",
            "4294967295",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert "parent_exited" in result.stdout and "runtime_stopped" in result.stdout
    assert not (tmp_path / "ready.json").exists()


def test_bootstrap_access_extension_called(tmp_path):
    payload = bootstrap_input(tmp_path)
    calls = []

    class Access:
        def validate(self, path):
            calls.append("validate")

        def consume(self, path):
            calls.append("consume")
            return json.dumps(payload).encode()

    assert (
        read_bootstrap(tmp_path / "not-used", Access()).instance_nonce == payload["instance_nonce"]
    )
    assert calls == ["validate", "consume"]


def test_source_data_directory_rejected(tmp_path):
    payload = bootstrap_input(tmp_path)
    payload["data_dir"] = str(Path(__file__).resolve().parents[2] / "data")
    path = tmp_path / "bootstrap.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="bootstrap_rejected"):
        read_bootstrap(path)


def test_bootstrap_secret_not_present_in_log(tmp_path):
    payload = bootstrap_input(tmp_path)
    payload["protocol_min"] = API_PROTOCOL + 1
    payload["protocol_max"] = API_PROTOCOL + 1
    path = tmp_path / "bootstrap.json"
    path.write_text(json.dumps(payload))
    result = subprocess.run(
        [sys.executable, "-m", "livingworld.bootstrap", "--bootstrap-path", str(path)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 1
    assert payload["bootstrap_secret"] not in result.stdout + result.stderr
    assert "startup_or_runtime_failed" in result.stdout


def test_random_loopback_readiness_and_graceful_shutdown(tmp_path):
    payload = bootstrap_input(tmp_path)
    path = tmp_path / "bootstrap.json"
    path.write_text(json.dumps(payload))
    process = subprocess.Popen(
        [sys.executable, "-m", "livingworld.bootstrap", "--bootstrap-path", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        ready_path = tmp_path / "ready.json"
        deadline = time.monotonic() + 10
        while not ready_path.exists():
            assert process.poll() is None, "core exited before readiness"
            assert time.monotonic() < deadline, "readiness timed out"
            time.sleep(0.05)
        ready = json.loads(ready_path.read_text())
        assert ready["endpoint"].startswith("http://127.0.0.1:")
        assert int(ready["endpoint"].rsplit(":", 1)[1]) > 0
        assert ready["api_protocol"] == API_PROTOCOL
        assert "token" not in ready and "bootstrap_secret" not in ready
        assert not path.exists()
        token = derive_session(
            payload["bootstrap_secret"], payload["instance_nonce"], ready["generation"]
        )
        with httpx.Client(base_url=ready["endpoint"], trust_env=False) as client:
            assert client.get("/system/live").status_code == 200
            assert client.get("/system/health").status_code == 401
            assert (
                client.get("/system/health", headers={"Authorization": "Bearer wrong"}).status_code
                == 401
            )
            headers = {"Authorization": f"Bearer {token}"}
            health = client.get("/system/health", headers=headers).json()
            assert health["ready"] is True
            assert health["generation"] == ready["generation"]
            headers["X-Request-Id"] = str(uuid4())
            assert client.post("/system/shutdown", headers=headers).status_code == 200
        output, _ = process.communicate(timeout=8)
        assert process.returncode == 0
        assert not ready_path.exists()
        assert payload["bootstrap_secret"] not in output and token not in output
        records = [json.loads(line) for line in output.splitlines()]
        assert all(
            {"timestamp", "level", "component", "event"} <= record.keys() for record in records
        )
        assert "runtime_stopped" in {record["event"] for record in records}
        disk_log = next((tmp_path / "logs").glob("core-*.jsonl")).read_text(encoding="utf-8")
        assert payload["bootstrap_secret"] not in disk_log and token not in disk_log
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
