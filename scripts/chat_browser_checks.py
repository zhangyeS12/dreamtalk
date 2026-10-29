"""Long synthetic history checks for the real chat layout; never generates or saves messages."""

import json
import re
from datetime import UTC, datetime, timedelta

from playwright.sync_api import Page, expect

AT_BOTTOM = """s => s.clientHeight > 40 && s.scrollHeight > s.clientHeight + 100
    && Math.abs(s.scrollHeight - s.clientHeight - s.scrollTop) < 3"""


def check_chat_scroll(page: Page, label: str) -> None:
    """Check each shared chat surface, re-entry, polling and narrow/immersive layouts."""
    messages_pattern = re.compile(r".*/conversations/([^/]+)/messages/page.*")
    read_pattern = re.compile(r".*/conversations/[^/]+/read$")
    reads: list[int] = []

    def history(route):
        match = messages_pattern.match(route.request.url)
        conversation = match.group(1)
        start = datetime(2026, 10, 29, tzinfo=UTC)
        items = [
            {
                "message_id": f"{index:08d}-0000-4000-8000-000000000000",
                "turn_id": f"{index:08d}-0000-4000-8000-000000000001",
                "conversation_id": conversation,
                "position": index,
                "sender_kind": "character",
                "sender_id": "00000000-0000-4000-8000-000000000002",
                "text": f"合成滚动回归记录 {index}。“这是一段用于检查聊天高度和最新位置的文字。”",
                "created_at_utc": (start + timedelta(minutes=index)).isoformat(),
                "story_sent_at_utc": None,
                "media": None,
                "feedback": None,
            }
            for index in range(1, 41)
        ]
        route.fulfill(json={"items": items, "next_before_position": None})

    def read(route):
        reads.append(json.loads(route.request.post_data)["position"])
        route.fulfill(json={"read": True})

    page.route(messages_pattern, history)
    page.route(read_pattern, read)
    original_viewport = page.viewport_size
    thread = page.get_by_role("region", name=label, exact=True)
    scroller = thread.locator("[data-chat-scroll]")
    directory = page.get_by_role("complementary", name="会话列表")
    nav = page.get_by_role("navigation", name="主导航")

    def latest():
        page.wait_for_function(AT_BOTTOM, arg=scroller.element_handle())
        assert page.locator("main").evaluate("e => e.scrollHeight - e.clientHeight") < 3
        assert page.evaluate("document.scrollingElement.scrollTop") == 0
        box = thread.bounding_box()
        assert box["y"] + box["height"] <= page.viewport_size["height"] + 2

    try:
        thread.get_by_role("button", name="刷新记录", exact=True).click()
        expect(thread.get_by_text("合成滚动回归记录 40。", exact=False)).to_be_visible()
        for width, height in [(1440, 900), (780, 800)]:
            page.set_viewport_size({"width": width, "height": height})
            # Reopening a conversation must start at its newest loaded message.
            nav.get_by_role("button", name="我", exact=True).click()
            nav.get_by_role("button", name="聊天", exact=True).click()
            latest()
            before_directory = directory.bounding_box() if directory.is_visible() else None
            before_thread = thread.bounding_box()
            before = scroller.evaluate("e => e.scrollTop")
            scroller.hover()
            page.mouse.wheel(0, -650)
            page.wait_for_function(
                "([s, before]) => s.scrollTop < before - 100",
                arg=[scroller.element_handle(), before],
            )
            position = scroller.evaluate("e => e.scrollTop")
            # The normal transcript poll must not pull a reader away from old messages.
            page.wait_for_timeout(2300)
            assert abs(scroller.evaluate("e => e.scrollTop") - position) < 3
            assert abs(thread.bounding_box()["y"] - before_thread["y"]) < 1
            if before_directory:
                assert abs(directory.bounding_box()["y"] - before_directory["y"]) < 1
            assert page.locator("main").evaluate("e => e.scrollTop") == 0
            # Wheel input at either edge must stay within the transcript.
            for edge, delta in [(0, -800), (10**7, 800)]:
                scroller.evaluate("(e, top) => { e.scrollTop = top; }", edge)
                page.mouse.wheel(0, delta)
                page.wait_for_timeout(150)
                assert page.locator("main").evaluate("e => e.scrollTop") == 0
            latest()
        page.set_viewport_size({"width": 1440, "height": 900})
        page.get_by_role("group", name="聊天显示模式").get_by_role(
            "button", name="沉浸", exact=True
        ).click()
        # The mode can be resized without letting the whole page become the scroller.
        page.set_viewport_size({"width": 1440, "height": 800})
        scroller.evaluate("e => { e.scrollTop = e.scrollHeight; }")
        latest()
        assert not directory.is_visible()
        assert 40 in reads, "latest visible messages were not acknowledged by the chat scroller"
    finally:
        page.get_by_role("group", name="聊天显示模式").get_by_role(
            "button", name="普通", exact=True
        ).click()
        if original_viewport:
            page.set_viewport_size(original_viewport)
        page.unroute(messages_pattern, history)
        page.unroute(read_pattern, read)
        thread.get_by_role("button", name="刷新记录", exact=True).click()
