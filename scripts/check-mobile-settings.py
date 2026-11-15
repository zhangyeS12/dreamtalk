"""Isolated browser/Core check; never calls a real model or installs an APK."""

import importlib
import json
import re
import sys
import tempfile
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/core/src"))
mobile_host = importlib.import_module("livingworld.bootstrap.mobile_host")

outbound = []


async def deny_network(self, request, *args, **kwargs):
    outbound.append(str(request.url.host))
    raise AssertionError("Remote network is prohibited in this check")


httpx.AsyncClient.send = deny_network


class Host:
    def __init__(self, root):
        self.root, self.value = root, "{}"

    def dataDirectory(self):
        return str(self.root)

    def secureRead(self):
        return self.value

    def secureWrite(self, value):
        self.value = value

    def isForeground(self):
        return True

    def isBackgroundRunning(self):
        return False


output = ROOT / "artifacts/settings-browser"
output.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(
    prefix="android-settings-browser-", dir="D:/dreamtalk"
) as temporary:
    runtime = importlib.reload(mobile_host)
    runtime._allowed_origins = ("http://127.0.0.1:1430",)
    host = Host(Path(temporary) / "app")

    def dispatch(operation, value):
        if operation == "notification_target":
            return None
        if operation == "background_status":
            return {
                "enabled": False,
                "running": False,
                "start_on_boot": False,
                "notifications_allowed": False,
                "battery_unrestricted": False,
                "problem": None,
            }
        if operation == "app_info":
            return {"version": "source-browser-check", "android": "not-a-device"}
        return json.loads(runtime.dispatch(operation, json.dumps(value or {}), host))["result"]

    dispatch("connection", {})
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                headless=True,
            )
            page = browser.new_page(viewport={"width": 390, "height": 844})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("dialog", lambda dialog: dialog.accept())
            page.expose_function("mobileNativeCheck", dispatch)
            page.add_init_script(
                "window.__DREAMTALK_MOBILE_TEST_HOST__=(operation,payload)=>window.mobileNativeCheck(operation,payload);"
            )
            try:
                page.goto("http://127.0.0.1:1430")
                page.wait_for_load_state("networkidle")
                page.get_by_role("button", name="应用设置", exact=True).click()
                page.get_by_role("button", name=re.compile("^模型与聊天")).click()
                page.get_by_label("每轮 Token 上限").fill("16384")
                page.get_by_role("button", name="应用聊天额度", exact=True).click()
                page.get_by_text(re.compile("当前已应用 16,384 Token")).wait_for()
                page.get_by_role("button", name="返回世界列表", exact=True).click()
                page.get_by_role("button", name="体验校园示例", exact=True).click()
                page.get_by_role("button", name="确认设定并创建示例世界", exact=True).click()
                page.get_by_role("button", name="设置", exact=True).wait_for()
                start = page.get_by_role("button", name="从家开始", exact=True)
                if start.count():
                    start.click()
                page.get_by_role("button", name="设置", exact=True).click()
                page.get_by_text("主动联系", exact=True).wait_for()
                page.screenshot(path=str(output / "settings-index.png"), full_page=True)
                pages = [
                    "模型与聊天",
                    "聊天视觉",
                    "表情与图片",
                    "角色配音",
                    "后台运行与通知",
                    "数据与备份",
                    "世界时间",
                    "角色活动",
                    "主动联系",
                    "世界动态",
                    "关于与诊断",
                ]
                checked = []
                for name in pages:
                    page.get_by_role("button", name=re.compile("^" + re.escape(name))).click()
                    page.wait_for_load_state("networkidle")
                    page.get_by_role("button", name="‹ 设置目录", exact=True).wait_for()
                    # Observe the rendered page before checking supported phone widths.
                    visible = page.locator(".mobile-settings").inner_text()
                    if (
                        "本地 IndexTTS" in visible
                        or "本机Ollama视觉模型" in visible
                        or "选择模型目录" in visible
                    ):
                        raise AssertionError(
                            "Local-model deployment entry leaked into Android settings"
                        )
                    for width in (320, 390, 720):
                        page.set_viewport_size({"width": width, "height": 844})
                        if page.evaluate("document.documentElement.scrollWidth > innerWidth"):
                            raise AssertionError(
                                "Horizontal overflow: " + name + " at " + str(width)
                            )
                    page.set_viewport_size({"width": 390, "height": 844})
                    if name in ("主动联系", "后台运行与通知", "数据与备份"):
                        page.screenshot(
                            path=str(output / (str(len(checked)) + "-settings.png")), full_page=True
                        )
                    checked.append(name)
                    page.get_by_role("button", name="‹ 设置目录", exact=True).click()
                assert not errors, errors
                assert not outbound, outbound
                result = {
                    "campus_preview_confirm": True,
                    "settings_categories": checked,
                    "widths": [320, 390, 720],
                    "page_errors": errors,
                    "remote_calls": outbound,
                    "platform": "isolated-headless-browser-and-real-Core",
                    "android_runtime": "not-tested",
                }
                (output / "result.json").write_text(
                    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                print(json.dumps(result, ensure_ascii=False))
            except Exception:
                page.screenshot(path=str(output / "failure.png"), full_page=True)
                print(page.locator("body").inner_text()[-2500:])
                raise
            finally:
                browser.close()
    finally:
        runtime._stop_if_idle()
