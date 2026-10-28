"""Screenshot the in-world UI with real Core/Vite and catch two known visual regressions.

Starts the owned isolated runtime (never the user's saves), creates the school
example world, injects a short synthetic chat history at the network layer so
the script view has something to show, and writes PNGs to
artifacts/browser-checks/visual/. It fails when a visible button label is
(nearly) transparent or the contacts detail pane cannot scroll; both shipped once.

usage: uv run --frozen --group browser-test python scripts/visual-check.py
       [--width 1440] [--height 900] [--sky-time HH:MM] [--channel msedge]
"""

import argparse
import json
import os
import re
from datetime import UTC, datetime, timedelta

from browser_runtime import ROOT, owned_dev_web
from playwright.sync_api import expect, sync_playwright

START = datetime(2026, 10, 27, 11, 0, tzinfo=UTC)
SCRIPT = [
    ("player", "清禾，图书馆三楼靠窗那个位置今天有人吗？"),
    (
        "character",
        "（她从书页间抬起头）“还空着。我帮你占了半张桌子，不过……”\n\n“你得先把第十二题讲给我听。”",
    ),
    ("player", "成交。我带了两盒草莓牛奶。"),
    ("character", "“图书馆不能喝东西。”她说得一本正经，手却已经把书包往旁边挪了挪。"),
]
INVISIBLE_LABELS = """() => [...document.querySelectorAll('button, summary, a.primary-button')]
.filter(e => {
  const r = e.getBoundingClientRect();
  if (!r.width || !r.height || !e.textContent.trim()) return false;
  const c = getComputedStyle(e).color.match(/[\\d.]+/g).map(Number);
  return (c.length > 3 ? c[3] : 1) < 0.5;
}).map(e => e.textContent.trim().slice(0, 30))"""
SETTINGS = ("模型与聊天", "聊天视觉", "数据与备份", "世界时间", "主动联系", "关于与诊断")

parser = argparse.ArgumentParser()
parser.add_argument("--width", type=int, default=1440)
parser.add_argument("--height", type=int, default=900)
parser.add_argument("--sky-time", help="override every world's clock, e.g. 18:40")
parser.add_argument("--channel", default="msedge" if os.name == "nt" else None)
args = parser.parse_args()
output = ROOT / "artifacts/browser-checks/visual"
output.mkdir(parents=True, exist_ok=True)


def history(conversation):
    return [
        {
            "message_id": f"{index:08d}-0000-4000-8000-000000000000",
            "turn_id": f"{index // 2:08d}-0000-4000-8000-000000000001",
            "conversation_id": conversation["conversation_id"],
            "position": index + 1,
            "sender_kind": kind,
            "sender_id": conversation["player_id" if kind == "player" else "character_id"],
            "text": text,
            "media": None,
            "created_at_utc": (START + timedelta(minutes=3 * index)).isoformat(),
            "story_sent_at_utc": None,
            "feedback": None,
        }
        for index, (kind, text) in enumerate(SCRIPT)
    ]


def main(url: str) -> list[str]:
    problems: list[str] = []
    conversations: dict[str, dict] = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel=args.channel, headless=True)
        page = browser.new_page(
            viewport={"width": args.width, "height": args.height}, locale="zh-CN"
        )
        page.on("pageerror", lambda error: problems.append(f"page error: {error}"))

        def remember(response):
            if response.request.method == "GET" and re.search(
                r"/worlds/[^/]+/conversations$", response.url
            ):
                for item in response.json():
                    conversations[item["conversation_id"]] = item

        page.on("response", remember)

        def inject(route):
            response = route.fetch()
            body = response.json()
            match = re.search(r"/conversations/([^/]+)/messages/page", route.request.url)
            conversation = conversations.get(match.group(1)) if match else None
            first_page = "before_position" not in route.request.url
            if conversation and first_page and not body.get("items"):
                body = {"items": history(conversation), "next_before_position": None}
            route.fulfill(response=response, body=json.dumps(body))

        page.route(re.compile(r".*/messages/page.*"), inject)
        if args.sky_time:
            hour, minute = (int(part) for part in args.sky_time.split(":"))
            micros = str((2 * 1440 + hour * 60 + minute) * 60_000_000)

            def clock(route):
                response = route.fetch()
                body = response.json()
                for item in body:
                    item["world_time"] = micros
                route.fulfill(response=response, body=json.dumps(body))

            page.route(re.compile(r".*/worlds$"), clock)

        def shot(name):
            page.wait_for_timeout(900)
            page.screenshot(path=str(output / f"{name}.png"))

        def labels(where):
            if found := page.evaluate(INVISIBLE_LABELS):
                problems.append(f"invisible labels on {where}: {found}")

        def nav(name):
            page.get_by_role("navigation", name="主导航").get_by_role(
                "button", name=name, exact=True
            ).click()

        page.goto(url, wait_until="networkidle")
        page.get_by_role("region", name="世界书架", exact=True).wait_for(timeout=30_000)
        shot("archive")
        page.get_by_role("button", name="体验校园示例", exact=True).click()
        page.get_by_role("button", name="确认设定并创建示例世界", exact=True).click()
        page.get_by_role("button", name="进入世界 →", exact=True).click()
        page.get_by_role("navigation", name="主导航").wait_for()

        nav("通讯录")
        contacts = page.locator(".contacts-workspace")
        contacts.get_by_role("button", name=re.compile("沈清禾")).click()
        detail = contacts.locator(".conversation-detail")
        page.wait_for_timeout(600)
        before = detail.evaluate("element => element.scrollTop")
        detail.hover()
        page.mouse.wheel(0, 900)
        page.wait_for_timeout(500)
        if detail.evaluate("element => element.scrollHeight > element.clientHeight + 4") and (
            detail.evaluate("element => element.scrollTop") <= before
        ):
            problems.append("contacts detail pane does not scroll")
        labels("contacts")
        shot("contacts")
        contacts.get_by_role("button", name="打开会话", exact=True).click()
        thread = page.get_by_role("region", name="沈清禾的会话")
        thread.wait_for()
        expect(thread.get_by_text("你得先把第十二题讲给我听。", exact=False)).to_be_visible()
        labels("chat")
        shot("chat")
        mode = page.get_by_role("group", name="聊天显示模式")
        mode.get_by_role("button", name="沉浸", exact=True).click()
        shot("chat-immersive")
        mode.get_by_role("button", name="普通", exact=True).click()

        nav("设置")
        for name in SETTINGS:
            page.get_by_role("navigation", name="设置分类").get_by_role(
                "button", name=re.compile("^" + name)
            ).click()
            page.wait_for_timeout(400)
            labels(f"settings/{name}")
        shot("settings")
        nav("我")
        labels("me")
        shot("me")
        browser.close()
    return problems


with owned_dev_web("livingworld-visual-") as url:
    found = main(url)
report = {"event": "visual_check", "output": str(output), "problems": found}
print(json.dumps(report, ensure_ascii=False))
if found:
    raise SystemExit(1)
