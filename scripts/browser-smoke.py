"""Run a real browser against the owned development Core/Vite lifecycle."""

import argparse
import json
import os
import re
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
environment["APPDATA"] = isolated_data.name
environment["HF_HUB_OFFLINE"] = "1"
environment["TRANSFORMERS_OFFLINE"] = "1"
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
        page.get_by_role("heading", name="世界书架", exact=True).wait_for(timeout=30_000)

        def archive():
            page.get_by_role("button", name="世界书架", exact=True).click()
            page.get_by_role("heading", name="世界书架", exact=True).wait_for()

        def enter_world(name):
            book = page.get_by_role("button", name=f"预览世界：{name}", exact=True)
            book.focus()
            book.press("Enter")
            page.get_by_role("button", name="进入世界 →", exact=True).click()
            page.get_by_role("navigation", name="主导航").wait_for()

        def create_world(name):
            blank = page.get_by_role("button", name="创建或导入一个新世界，空白书 1", exact=True)
            blank.focus()
            blank.press("Enter")
            page.get_by_role("button", name="创建世界", exact=True).click()
            page.get_by_role("textbox", name="世界名称", exact=True).fill(name)
            page.get_by_role("button", name="创建档案并添加世界书", exact=True).click()
            page.get_by_role("button", name="进入世界 →", exact=True).click()
            page.get_by_role("navigation", name="主导航").wait_for()

        def settings(name):
            page.get_by_role("button", name="设置", exact=True).click()
            page.get_by_role("navigation", name="设置分类").get_by_role(
                "button", name=re.compile("^" + name)
            ).click()

        def card_manager():
            page.get_by_role("button", name="通讯录", exact=True).click()
            manager = page.locator("section.import-section").filter(
                has=page.get_by_role("heading", name="角色卡", exact=True)
            )
            if not manager.is_visible():
                page.get_by_text("添加／编辑角色卡", exact=True).click()
            expect(manager).to_be_visible()
            options = manager.locator("details.file-import-options")
            if not options.evaluate("element => element.open"):
                options.locator("summary").click()
            return manager

        # Optional preview never adds a world; the confirmation creates ordinary data.
        page.get_by_role("button", name="体验校园示例", exact=True).click()
        expect(page.get_by_role("heading", name="晴川高中 · 青春日常", exact=True)).to_be_visible()
        expect(page.get_by_role("button", name="预览世界：晴川高中 · 青春日常")).to_have_count(0)
        if example_screenshot := os.environ.get("LW_EXAMPLE_SCREENSHOT"):
            page.screenshot(path=example_screenshot, full_page=True)
        page.get_by_role("button", name="确认设定并创建示例世界", exact=True).click()
        page.get_by_role("button", name="进入世界 →", exact=True).click()
        page.get_by_role("button", name="通讯录", exact=True).click()
        expect(page.locator(".contacts-workspace .conversation-row")).to_have_count(3)
        for name in ("沈清禾", "夏小满", "周明远"):
            expect(
                page.locator(".contacts-workspace").get_by_role("button", name=re.compile(name))
            ).to_be_visible()
        archive()
        create_world("world_profile_smoke")
        page.get_by_role("button", name="进入世界", exact=True).click()
        page.get_by_text("已绑定：我", exact=True).wait_for()
        page.get_by_role("button", name="聊天", exact=True).click()
        for width in (1024, 1440, 1920):
            page.set_viewport_size({"width": width, "height": 900})
            workspace = page.locator(".chat-workspace:visible")
            assert workspace.bounding_box()["width"] > width * 0.9
            assert workspace.locator(".conversation-list").is_visible()
            assert workspace.locator(".conversation-detail").is_visible()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.set_viewport_size({"width": 1440, "height": 900})
        if screenshot_path := os.environ.get("LW_BROWSER_SCREENSHOT"):
            page.screenshot(path=screenshot_path, full_page=True)
        if mobile_screenshot_path := os.environ.get("LW_BROWSER_MOBILE_SCREENSHOT"):
            page.set_viewport_size({"width": 390, "height": 844})
            page.screenshot(path=mobile_screenshot_path, full_page=True)
        page.set_viewport_size({"width": 1440, "height": 900})
        page.locator(".conversation-row.pinned").click()
        page.get_by_role("region", name="世界事件时间线").wait_for()
        settings("世界时间")
        clock_section = page.locator("section.settings-section").filter(
            has=page.get_by_role("heading", name="世界时间", exact=True)
        )
        clock_section.get_by_role("spinbutton", name="时间倍率").fill("1000")
        clock_section.get_by_role("button", name="应用", exact=True).click()
        page.get_by_text("时间倍率已更新。", exact=True).wait_for()
        clock_section.get_by_role("button", name="暂停", exact=True).click()
        page.get_by_text("世界已暂停。", exact=True).wait_for()
        paused_time = clock_section.locator(".section-heading p").inner_text()
        page.wait_for_timeout(2500)
        assert clock_section.locator(".section-heading p").inner_text() == paused_time
        clock_section.get_by_role("button", name="恢复", exact=True).click()
        page.get_by_text("世界已恢复。", exact=True).wait_for()
        page.wait_for_function(
            "previous => [...document.querySelectorAll('section.settings-section')]"
            ".find(section => section.querySelector('h2')?.textContent === '世界时间')"
            "?.querySelector('.section-heading p')?.textContent !== previous",
            arg=paused_time,
            timeout=10_000,
        )
        settings("模型与聊天")
        page.get_by_text("聊天额度", exact=True).filter(visible=True).click()
        budget_section = page.locator("section.settings-section").filter(
            has=page.get_by_role("heading", name="聊天额度", exact=True)
        )
        budget_section.get_by_role("spinbutton", name="每轮 Token 上限").fill("60000")
        budget_section.get_by_role("button", name="应用", exact=True).click()
        page.get_by_text("聊天额度已更新。", exact=True).wait_for()
        manager = card_manager()
        manager.get_by_label("选择文件", exact=True).set_input_files(
            root / "tests/fixtures/character_cards/v2.json"
        )
        manager.get_by_role("heading", name="导入预览", exact=True).wait_for()
        manager.get_by_role("combobox", name="初始地点（必选）", exact=True).select_option(
            label="家"
        )
        manager.get_by_role("button", name="确认加入当前世界", exact=True).click()
        page.get_by_text("已加入当前世界，可在通讯录查看角色。", exact=True).wait_for()
        page.locator(".contacts-workspace .conversation-row").click()
        page.get_by_role("heading", name="Fixture Alice", exact=True).wait_for()
        contacts = page.locator(".contacts-workspace")
        expect(contacts.get_by_role("heading", name="角色卡开场白（原文）")).to_be_visible()
        expect(contacts.get_by_text("Hello {{user}}.", exact=True)).to_be_visible()
        if contacts_screenshot := os.environ.get("LW_CONTACTS_SCREENSHOT"):
            page.screenshot(path=contacts_screenshot, full_page=True)
        contacts.get_by_role("button", name="打开会话", exact=True).click()
        page.get_by_role("region", name="Fixture Alice的会话").wait_for()
        page.get_by_text("当前聊天模型尚不可用，请在设置中核对模型与路由。", exact=True).wait_for()
        expect(page.get_by_role("textbox", name="发送给Fixture Alice的消息")).to_be_disabled()
        expect(page.get_by_role("button", name="发送", exact=True)).to_be_disabled()
        expect(page.locator(".conversation-list .conversation-row.pinned")).to_have_count(1)
        if chat_screenshot := os.environ.get("LW_CHAT_SCREENSHOT"):
            page.screenshot(path=chat_screenshot, full_page=True)
        settings("主动联系")
        availability_section = page.locator("section.settings-section").filter(
            has=page.get_by_role("heading", name="交流状态", exact=True)
        )
        availability_section.get_by_role("button", name="设为忙碌").click()
        expect(availability_section.locator("strong")).to_have_text("忙碌")
        availability_section.get_by_role("button", name="设为可用").click()
        expect(availability_section.locator("strong")).to_have_text("可用")
        page.reload(wait_until="networkidle")
        page.get_by_role("heading", name="世界书架", exact=True).wait_for()
        enter_world("world_profile_smoke")
        settings("模型与聊天")
        page.get_by_text("聊天额度", exact=True).filter(visible=True).click()
        expect(budget_section.get_by_role("spinbutton", name="每轮 Token 上限")).to_have_value(
            "60000"
        )
        settings("主动联系")
        expect(availability_section.locator("strong")).to_have_text("可用")
        manager = card_manager()
        manager.get_by_role("button", name="从文件更新", exact=True).click()
        manager.get_by_label("选择文件", exact=True).set_input_files(
            root / "tests/fixtures/character_cards/v3.json"
        )
        manager.get_by_role("heading", name="导入预览", exact=True).wait_for()
        manager.get_by_role("button", name="确认更新当前世界", exact=True).click()
        page.get_by_text("当前世界的内容已更新。", exact=True).wait_for()
        manager.get_by_label("选择文件", exact=True).set_input_files(
            root / "tests/fixtures/character_cards/group_second.json"
        )
        manager.get_by_role("heading", name="导入预览", exact=True).wait_for()
        manager.get_by_role("combobox", name="初始地点（必选）", exact=True).select_option(
            label="家"
        )
        manager.get_by_role("button", name="确认加入当前世界", exact=True).click()
        page.get_by_text("已加入当前世界，可在通讯录查看角色。", exact=True).wait_for()
        expect(page.locator(".contacts-workspace .conversation-row")).to_have_count(2)
        page.get_by_role("button", name="聊天", exact=True).click()
        page.get_by_role("button", name="新建群聊", exact=True).click()
        page.get_by_role("checkbox", name="Fixture Billy").check()
        page.get_by_role("checkbox", name="Fixture Charlie").check()
        page.get_by_role("button", name="创建群聊", exact=True).click()
        page.get_by_role("region", name="群聊").wait_for()
        expect(page.get_by_role("button", name="发送", exact=True)).to_be_disabled()
        page.reload(wait_until="networkidle")
        page.get_by_role("heading", name="世界书架", exact=True).wait_for()
        enter_world("world_profile_smoke")
        page.get_by_role("button", name="聊天", exact=True).click()
        group_row = page.locator(".conversation-list .conversation-row").filter(
            has_text="Fixture Billy、Fixture Charlie"
        )
        group_row.wait_for()
        group_row.click()
        page.get_by_role("region", name="群聊").wait_for()
        archive()
        book = page.get_by_role("button", name="预览世界：world_profile_smoke", exact=True)
        book.focus()
        book.press("Enter")
        page.get_by_role("button", name="管理 / 导入世界书", exact=True).click()
        page.get_by_label("选择文件", exact=True).set_input_files(
            root / "tests/fixtures/lorebooks/world_info.json"
        )
        page.get_by_role("heading", name="导入预览", exact=True).wait_for()
        page.get_by_role("button", name="确认加入当前世界", exact=True).click()
        page.get_by_text("世界书已加入当前世界。", exact=True).wait_for()
        page.get_by_role("button", name="进入世界 →", exact=True).click()
        page.get_by_role("button", name="我", exact=True).click()
        page.get_by_label("我的称呼", exact=True).fill("player_a")
        page.get_by_label("关于我", exact=True).fill("喜欢阅读")
        page.get_by_role("button", name="保存通用信息", exact=True).click()
        page.get_by_label("我在这个世界的身份", exact=True).fill("旅人")
        page.get_by_role("button", name="保存世界身份", exact=True).click()
        page.reload(wait_until="networkidle")
        page.get_by_role("heading", name="世界书架", exact=True).wait_for()
        enter_world("world_profile_smoke")
        page.get_by_role("button", name="我", exact=True).click()
        expect(page.get_by_label("我的称呼", exact=True)).to_have_value("player_a")
        expect(page.get_by_label("关于我", exact=True)).to_have_value("喜欢阅读")
        expect(page.get_by_label("我在这个世界的身份", exact=True)).to_have_value("旅人")
        archive()
        create_world("world_profile_other")
        page.get_by_role("button", name="我", exact=True).click()
        expect(page.get_by_label("关于我", exact=True)).to_have_value("喜欢阅读")
        expect(page.get_by_label("我在这个世界的身份", exact=True)).to_have_value("")
        page.get_by_role("button", name="通讯录", exact=True).click()
        page.get_by_role("heading", name="当前世界还没有角色", exact=True).wait_for()
        page.get_by_role("button", name="聊天", exact=True).click()
        expect(group_row).to_have_count(0)
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
