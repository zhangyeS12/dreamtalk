"""Exercise a frozen Core with isolated app data and no source import path."""

import argparse
import hashlib
import hmac
import json
import os
import secrets
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from uuid import uuid4


def request(url: str, token: str, *, method: str = "GET") -> dict:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    headers = {"Authorization": f"Bearer {token}"}
    if method == "POST":
        headers["X-Request-Id"] = str(uuid4())
    with opener.open(urllib.request.Request(url, headers=headers, method=method), timeout=3) as r:
        return json.load(r)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("binary", type=Path)
    args = parser.parse_args()
    binary = args.binary.resolve(strict=True)
    if os.name != "nt":
        raise SystemExit("standalone_core_smoke_requires_windows")
    root = Path(__file__).resolve().parents[1]
    contract = json.loads(
        (root / "services/core/src/livingworld/domain/api_contract.json").read_text(
            encoding="utf-8"
        )
    )
    protocol = contract["api_protocol"]
    with tempfile.TemporaryDirectory(prefix="dreamtalk-standalone-smoke-") as temp:
        base = Path(temp)
        runtime = base / "runtime"
        runtime.mkdir()
        nonce, secret = str(uuid4()), secrets.token_hex(32)
        bootstrap = runtime / "bootstrap.json"
        bootstrap.write_text(
            json.dumps(
                {
                    "bootstrap_secret": secret,
                    "instance_nonce": nonce,
                    "protocol_min": protocol,
                    "protocol_max": protocol,
                    "data_dir": str(base / "data"),
                    "log_dir": str(base / "logs"),
                }
            ),
            encoding="utf-8",
        )
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        process = subprocess.Popen(
            [
                str(binary),
                "--desktop",
                "--bootstrap-path",
                str(bootstrap),
                "--parent-pid",
                str(os.getpid()),
            ],
            cwd=base,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        try:
            deadline = time.monotonic() + 35
            ready_path = runtime / "ready.json"
            while not ready_path.is_file():
                if process.poll() is not None:
                    detail = "\n".join(
                        stream.read().decode("utf-8", errors="replace")
                        for stream in (process.stdout, process.stderr)
                        if stream
                    )
                    raise RuntimeError(
                        f"frozen_core_exited_before_ready:{process.returncode}:"
                        f"{detail.replace(secret, '[redacted]')[-2000:]}"
                    )
                if time.monotonic() >= deadline:
                    raise RuntimeError("frozen_core_ready_timeout")
                time.sleep(0.05)
            ready = json.loads(ready_path.read_text(encoding="utf-8"))
            assert ready["instance_nonce"] == nonce
            assert ready["api_protocol"] == protocol
            assert ready["endpoint"].startswith("http://127.0.0.1:")
            message = f"{contract['session_derivation']}:{nonce}:{ready['generation']}"
            token = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
            health = request(ready["endpoint"] + "/system/health", token)
            assert health["ready"] is True
            assert health["core_version"]
            assert (base / "data" / "runtime.sqlite3").is_file()
            request(ready["endpoint"] + "/system/shutdown", token, method="POST")
            if process.stdin:
                process.stdin.close()
            assert process.wait(timeout=12) == 0
            print("standalone_core_smoke_passed")
        finally:
            if process.poll() is None:
                subprocess.run(
                    [
                        str(Path(os.environ["SystemRoot"]) / "System32/taskkill.exe"),
                        "/PID",
                        str(process.pid),
                        "/T",
                        "/F",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                process.wait(timeout=5)


if __name__ == "__main__":
    main()
