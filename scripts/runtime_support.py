"""Development launcher support. Credentials are never displayed or persisted as sessions."""

import json
import os
import secrets
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from uuid import uuid4

from livingworld.bootstrap.reader import derive_session
from livingworld.domain.contracts import API_PROTOCOL


def terminate_owned_tree(process):
    if os.name == "nt":
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
            creationflags=subprocess.CREATE_NO_WINDOW,
            check=False,
        )
    else:
        process.kill()
    process.wait(timeout=5)


def launch_core():
    base = (
        Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share"))
        / "LivingWorld/development"
    )
    runtime = base / "runtime" / str(uuid4())
    runtime.mkdir(parents=True)
    secret, nonce = secrets.token_hex(32), str(uuid4())
    path = runtime / "bootstrap.json"
    path.write_text(
        json.dumps(
            {
                "bootstrap_secret": secret,
                "instance_nonce": nonce,
                "protocol_min": API_PROTOCOL,
                "protocol_max": API_PROTOCOL,
                "data_dir": str(base / "data"),
                "log_dir": str(base / "logs"),
            }
        ),
        encoding="utf-8",
    )
    process = subprocess.Popen(
        [sys.executable, "-m", "livingworld.bootstrap", "--bootstrap-path", str(path)]
    )
    try:
        deadline = time.monotonic() + 15
        while not (runtime / "ready.json").exists():
            if process.poll() is not None or time.monotonic() >= deadline:
                raise RuntimeError("development_core_start_failed")
            time.sleep(0.05)
        ready = json.loads((runtime / "ready.json").read_text(encoding="utf-8"))
        token = derive_session(secret, nonce, ready["generation"])
        return process, ready, token, runtime
    except BaseException:
        if process.poll() is None:
            terminate_owned_tree(process)
        path.unlink(missing_ok=True)
        raise


def stop_core(process, ready, token, runtime):
    try:
        if process.poll() is None:
            request = urllib.request.Request(
                ready["endpoint"] + "/system/shutdown",
                method="POST",
                headers={"Authorization": f"Bearer {token}", "X-Request-Id": str(uuid4())},
            )
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(request, timeout=2):
                pass
    except OSError:
        pass
    finally:
        try:
            process.wait(timeout=6)
        except subprocess.TimeoutExpired:
            terminate_owned_tree(process)
        for name in ["bootstrap.json", "ready.json", "ready.tmp"]:
            (runtime / name).unlink(missing_ok=True)
        runtime.rmdir()
