"""Owned development Core + Vite for browser scripts, with isolated app data.

Starts ``scripts/dev-web.mjs --smoke`` against a throwaway LOCALAPPDATA/APPDATA,
waits for Vite, and on exit asks for the graceful stop path and checks that the
runtime reported ``runtime_stopped``. Never touches the user's own saves.
"""

import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from runtime_support import terminate_owned_tree

ROOT = Path(__file__).resolve().parents[1]
URL = "http://127.0.0.1:5173/"


@contextmanager
def owned_dev_web(prefix: str = "livingworld-browser-") -> Iterator[str]:
    node = shutil.which("node")
    if node is None:
        raise SystemExit("Node is required")
    isolated = tempfile.TemporaryDirectory(prefix=prefix)
    environment = os.environ.copy()
    environment["LOCALAPPDATA"] = isolated.name
    environment["APPDATA"] = isolated.name
    environment["HF_HUB_OFFLINE"] = "1"
    environment["TRANSFORMERS_OFFLINE"] = "1"
    process = subprocess.Popen(
        [node, "scripts/dev-web.mjs", "--smoke"],
        cwd=ROOT,
        env=environment,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        deadline = time.monotonic() + 20
        while True:
            if process.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError("browser_runtime_start_failed")
            try:
                with opener.open(URL, timeout=1):
                    break
            except OSError:
                time.sleep(0.1)
        yield URL
        output, _ = process.communicate("stop\n", timeout=12)
        events = [json.loads(line)["event"] for line in output.splitlines() if line.startswith("{")]
        if process.returncode != 0 or "runtime_stopped" not in events:
            raise RuntimeError("browser_graceful_shutdown_failed")
    finally:
        if process.poll() is None:
            try:
                process.communicate("stop\n", timeout=12)
            except (OSError, subprocess.TimeoutExpired, ValueError):
                terminate_owned_tree(process)
        isolated.cleanup()
