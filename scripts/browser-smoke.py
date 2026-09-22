"""Run a real browser against the owned development Core/Vite lifecycle."""

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright
from runtime_support import terminate_owned_tree

parser = argparse.ArgumentParser()
parser.add_argument("--channel", default="msedge" if os.name == "nt" else None)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
node = shutil.which("node")
if node is None:
    raise SystemExit("Node is required")
isolated_data = tempfile.TemporaryDirectory(prefix="livingworld-browser-smoke-")
environment = os.environ.copy()
environment["LOCALAPPDATA"] = isolated_data.name
process = subprocess.Popen(
    [node, "scripts/dev-web.mjs", "--smoke"],
    cwd=root,
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
        page.get_by_role("status").filter(has_text="核心已就绪").wait_for(timeout=20_000)
        page.get_by_role("navigation", name="主导航").wait_for(timeout=20_000)
        if screenshot_path := os.environ.get("LW_BROWSER_SCREENSHOT"):
            page.screenshot(path=screenshot_path, full_page=True)
        if mobile_screenshot_path := os.environ.get("LW_BROWSER_MOBILE_SCREENSHOT"):
            page.set_viewport_size({"width": 390, "height": 844})
            page.screenshot(path=mobile_screenshot_path, full_page=True)
        page.locator(".conversation-row.pinned").wait_for()
        page.locator(".conversation-row.pinned").click()
        page.get_by_role("region", name="世界事件时间线").wait_for()
        page.get_by_role("button", name="设置", exact=True).click()
        page.get_by_placeholder("给世界起个名字").fill("world_profile_smoke")
        page.get_by_role("button", name="创建世界", exact=True).click()
        page.get_by_text("世界已创建。", exact=True).wait_for()
        page.get_by_role("button", name="我", exact=True).click()
        page.get_by_label("我的称呼", exact=True).fill("player_a")
        page.get_by_label("关于我", exact=True).fill("喜欢阅读")
        page.get_by_role("button", name="保存通用信息", exact=True).click()
        page.get_by_text("已保存。", exact=True).wait_for()
        page.get_by_label("世界中的称呼", exact=True).fill("旅行者")
        page.get_by_label("我在这个世界的身份", exact=True).fill("在这个世界担任向导")
        page.get_by_role("button", name="保存世界身份", exact=True).click()
        expect(page.get_by_text("已保存。", exact=True)).to_have_count(2)
        if profile_screenshot := os.environ.get("LW_PROFILE_SCREENSHOT"):
            page.set_viewport_size({"width": 390, "height": 844})
            page.screenshot(path=profile_screenshot, full_page=True)
        page.reload(wait_until="networkidle")
        page.get_by_role("button", name="我", exact=True).click()
        expect(page.get_by_label("关于我", exact=True)).to_have_value("喜欢阅读")
        expect(page.get_by_label("我在这个世界的身份", exact=True)).to_have_value(
            "在这个世界担任向导"
        )
        page.get_by_role("button", name="设置", exact=True).click()
        page.get_by_placeholder("给世界起个名字").fill("world_profile_other")
        page.get_by_role("button", name="创建世界", exact=True).click()
        page.get_by_text("世界已创建。", exact=True).wait_for()
        page.get_by_role("button", name="我", exact=True).click()
        expect(page.get_by_label("关于我", exact=True)).to_have_value("喜欢阅读")
        expect(page.get_by_label("我在这个世界的身份", exact=True)).to_have_value("")
        # Inspector polls every 500 ms, so network-idle is not a readiness condition.
        page.goto("http://127.0.0.1:5173/?developer=1", wait_until="domcontentloaded")
        page.get_by_role("heading", name="开发者运行时检查器").wait_for(timeout=20_000)
        page.get_by_role("heading", name="计划触发器", exact=True).wait_for(timeout=20_000)
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
                "state": "核心已就绪",
                "product": "visible",
                "inspector": "visible",
                "profile_persistence_and_world_isolation": "passed",
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
    isolated_data.cleanup()
