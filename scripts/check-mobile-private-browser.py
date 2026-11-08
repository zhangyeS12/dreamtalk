"""Browser-only mobile privacy regression with synthetic text and blocked external traffic."""

import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/windows-sync-20261108/browser"

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(
        executable_path="C:/Program Files/Google/Chrome/Application/chrome.exe", headless=True
    )
    page = browser.new_page(viewport={"width": 390, "height": 844})
    errors, external, checks = [], [], []
    page.on("pageerror", lambda error: errors.append(str(error)))

    def guard(route):
        if route.request.url.startswith("http://127.0.0.1:1437/"):
            route.continue_()
        else:
            external.append(route.request.url.split("?")[0])
            route.abort()

    page.route("**/*", guard)
    try:
        page.goto(
            "http://127.0.0.1:1437/artifacts/windows-sync-20261108/browser/index.html",
            wait_until="domcontentloaded",
        )
        page.wait_for_load_state("networkidle")
        expect(page.get_by_role("heading", name="安卓私密片段检查")).to_be_visible()
        for width in (320, 390, 720):
            page.set_viewport_size({"width": width, "height": 844})
            for index in range(3):
                case = page.get_by_test_id(f"case-{index}")
                mask = case.get_by_role("button", name="查看私密片段，仅你与 合成角色 可见")
                expect(mask).to_be_visible()
                assert "只对你说的合成私密片段" not in case.inner_text()
                mask.click()
                collapse = case.get_by_role("button", name="收起私密片段，仅你与 合成角色 可见")
                expect(collapse).to_be_focused()
                tick = int(page.get_by_test_id("tick").inner_text())
                page.wait_for_function(
                    "previous => Number(document.querySelector('[data-testid=tick]').textContent)"
                    " >= previous + 20",
                    arg=tick,
                )
                expect(collapse).to_be_visible()
                expect(collapse).to_be_focused()
                assert "只对你说的合成私密片段" in case.inner_text()
                assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
                assert page.locator("p p").count() == 0
                collapse.click()
                expect(mask).to_be_focused()
                mask.press("Space")
                expect(collapse).to_be_visible()
                collapse.click()
                checks.append(
                    {
                        "width": width,
                        "case": index,
                        "refreshes": 20,
                        "reveal_focus_keyboard": True,
                        "overflow": False,
                    }
                )
            page.screenshot(path=str(OUT / f"private-{width}.png"), full_page=True)
        assert not errors and not external
        (OUT / "result.json").write_text(
            json.dumps(
                {
                    "checks": checks,
                    "page_errors": errors,
                    "external_requests": external,
                    "real_provider_calls": 0,
                    "synthetic_fixture": True,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print("Mobile privacy browser checks: 9 cases passed; no external requests or page errors.")
    finally:
        browser.close()
