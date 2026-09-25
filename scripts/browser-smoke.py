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
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        errors = []
        page.on("pageerror", lambda _error: errors.append(True))
        page.goto("http://127.0.0.1:5173/", wait_until="networkidle")
        page.get_by_role("status").filter(has_text="核心已就绪").wait_for(timeout=20_000)
        page.get_by_role("navigation", name="主导航").wait_for(timeout=20_000)
        for width in (1024, 1440, 1920):
            page.set_viewport_size({"width": width, "height": 900})
            assert page.locator(".chat-workspace").bounding_box()["width"] > width * 0.9
            assert page.locator(".conversation-list").is_visible()
            assert page.locator(".conversation-detail").is_visible()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.set_viewport_size({"width": 1440, "height": 900})
        if screenshot_path := os.environ.get("LW_BROWSER_SCREENSHOT"):
            page.screenshot(path=screenshot_path, full_page=True)
        if mobile_screenshot_path := os.environ.get("LW_BROWSER_MOBILE_SCREENSHOT"):
            page.set_viewport_size({"width": 390, "height": 844})
            page.screenshot(path=mobile_screenshot_path, full_page=True)
        page.set_viewport_size({"width": 1440, "height": 900})
        page.locator(".conversation-row.pinned").wait_for()
        page.locator(".conversation-row.pinned").click()
        page.get_by_role("region", name="世界事件时间线").wait_for()
        page.get_by_role("button", name="设置", exact=True).click()
        page.get_by_placeholder("给世界起个名字").fill("world_profile_smoke")
        page.get_by_role("button", name="创建世界", exact=True).click()
        page.get_by_text("世界已创建。", exact=True).wait_for()
        page.get_by_label("选择文件", exact=True).set_input_files(
            root / "tests/fixtures/character_cards/v2.json"
        )
        page.get_by_role("heading", name="导入预览", exact=True).wait_for(timeout=10_000)
        page.get_by_role("button", name="确认加入当前世界", exact=True).click()
        page.get_by_text("已加入当前世界，可在通讯录查看角色。", exact=True).wait_for()
        page.get_by_role("button", name="通讯录", exact=True).click()
        page.locator(".contacts-workspace .conversation-row").click()
        page.get_by_role("heading", name="角色资料", exact=True).wait_for()
        if contacts_screenshot := os.environ.get("LW_CONTACTS_SCREENSHOT"):
            page.screenshot(path=contacts_screenshot, full_page=True)
        page.get_by_role("button", name="先进入世界，再打开会话").click()
        page.get_by_role("button", name="进入世界", exact=True).click()
        page.get_by_text("已绑定：我", exact=True).wait_for()
        page.get_by_role("button", name="通讯录", exact=True).click()
        page.locator(".contacts-workspace .conversation-row").click()
        page.get_by_role("button", name="打开会话", exact=True).click()
        page.get_by_role("region", name="Fixture Alice的会话").wait_for()
        page.get_by_text("尚未配置可用的聊天模型或路由", exact=False).wait_for()
        expect(page.locator(".conversation-list .conversation-row.pinned")).to_have_count(1)
        if chat_screenshot := os.environ.get("LW_CHAT_SCREENSHOT"):
            page.screenshot(path=chat_screenshot, full_page=True)
        page.get_by_role("button", name="设置", exact=True).click()
        page.get_by_role("button", name="更新", exact=True).click()
        page.get_by_label("选择文件", exact=True).set_input_files(
            root / "tests/fixtures/character_cards/v3.json"
        )
        page.get_by_role("heading", name="导入预览", exact=True).wait_for(timeout=10_000)
        page.get_by_role("button", name="确认更新当前世界", exact=True).click()
        page.get_by_text("当前世界的内容已更新。", exact=True).wait_for()
        page.get_by_role("button", name="通讯录", exact=True).click()
        expect(page.locator(".contacts-workspace .conversation-row")).to_have_count(1)
        page.get_by_role("button", name="设置", exact=True).click()
        page.get_by_role("combobox", name="内容类型").select_option("lorebook")
        page.get_by_label("选择文件", exact=True).set_input_files(
            root / "tests/fixtures/lorebooks/world_info.json"
        )
        page.get_by_role("heading", name="导入预览", exact=True).wait_for(timeout=10_000)
        page.get_by_role("button", name="确认加入当前世界", exact=True).click()
        page.get_by_text("世界书已加入当前世界。", exact=True).wait_for()
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
        if desktop_profile := os.environ.get("LW_DESKTOP_PROFILE_SCREENSHOT"):
            page.set_viewport_size({"width": 1440, "height": 900})
            page.screenshot(path=desktop_profile, full_page=True)
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
        page.get_by_role("button", name="通讯录", exact=True).click()
        page.get_by_role("heading", name="当前世界还没有角色", exact=True).wait_for()
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
