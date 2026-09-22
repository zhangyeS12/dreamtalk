"""Exercise the real Windows Tauri WebView, Rust supervisor and window-close lifecycle."""

import json
import os
import subprocess
import tempfile
from pathlib import Path

if os.name != "nt":
    raise SystemExit("Windows desktop integration only")
root = Path(__file__).resolve().parents[1]
binary = root / "apps/desktop/src-tauri/target/debug/livingworld-desktop.exe"
environment = os.environ.copy()
environment["LW_DESKTOP_SMOKE"] = "1"
with tempfile.TemporaryDirectory(prefix="livingworld-desktop-smoke-") as app_data:
    environment["LW_DESKTOP_SMOKE_APP_DATA"] = app_data
    environment["WEBVIEW2_USER_DATA_FOLDER"] = str(Path(app_data) / "webview")
    try:
        result = subprocess.run(
            [str(binary)],
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=45,
        )
    except subprocess.TimeoutExpired as error:
        output = error.stdout or b""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        observed = [
            json.loads(line)["event"] for line in output.splitlines() if line.startswith("{")
        ]
        print(json.dumps({"event": "desktop_smoke_timeout", "observed_events": observed}))
        raise SystemExit(1) from None
events = [json.loads(line)["event"] for line in result.stdout.splitlines() if line.startswith("{")]
required = [
    "supervisor_starting",
    "core_ready",
    "supervisor_ready",
    "ui_ready",
    "shutdown_requested",
    "runtime_stopped",
    "supervisor_stopped_gracefully",
]
if (
    result.returncode != 0
    or not all(event in events for event in required)
    or "supervisor_forced_termination" in events
):
    print(json.dumps({"event": "desktop_smoke_failed", "observed_events": events}))
    raise SystemExit(1)
print(json.dumps({"event": "desktop_smoke_passed", "observed_events": events}))
