"""Run a real browser against the owned development Core/Vite lifecycle."""

import argparse
import json
import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright
from runtime_support import terminate_owned_tree

parser = argparse.ArgumentParser()
parser.add_argument("--channel", default="msedge" if os.name == "nt" else None)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
node = shutil.which("node")
if node is None:
    raise SystemExit("Node is required")
process = subprocess.Popen(
    [node, "scripts/dev-web.mjs", "--smoke"],
    cwd=root,
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
            with opener.open("http://127.0.0.1:5173/", timeout=1):
                break
        except OSError:
            time.sleep(0.1)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel=args.channel, headless=True)
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda _error: errors.append(True))
        page.goto("http://127.0.0.1:5173/", wait_until="networkidle")
        page.get_by_role("status").filter(has_text="Core Ready").wait_for(timeout=20_000)
        page.get_by_role("heading", name="Developer Runtime Inspector").wait_for(timeout=20_000)
        if errors:
            raise RuntimeError("browser_page_error")
        browser.close()
    output, _ = process.communicate("stop\n", timeout=12)
    events = [json.loads(line)["event"] for line in output.splitlines() if line.startswith("{")]
    if process.returncode != 0 or "runtime_stopped" not in events:
        raise RuntimeError("browser_graceful_shutdown_failed")
    print(
        json.dumps(
            {
                "event": "browser_smoke_passed",
                "state": "Core Ready",
                "inspector": "visible",
                "page_errors": 0,
            }
        )
    )
finally:
    if process.poll() is None:
        try:
            process.communicate("stop\n", timeout=12)
        except (OSError, subprocess.TimeoutExpired, ValueError):
            terminate_owned_tree(process)
