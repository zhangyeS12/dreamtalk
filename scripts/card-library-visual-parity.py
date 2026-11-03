"""Compare the approved, immutable preview with the actual isolated product UI."""

import functools
import hashlib
import io
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from browser_runtime import owned_dev_web
from PIL import Image, ImageChops
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/card-library-parity"
REFERENCE = ROOT / "tests/fixtures/character_card_visual_reference"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def pixels(locator):
    return Image.open(io.BytesIO(locator.screenshot())).convert("RGB")


def card_pixels(page, rectangle):
    # One shared device-pixel clip avoids a 1px screenshot crop jump caused by
    # equivalent 3D rectangles rounding to opposite sides of an integer.
    clip = {key: round(rectangle[key]) for key in ["x", "y", "width", "height"]}
    return Image.open(io.BytesIO(page.screenshot(clip=clip))).convert("RGB")


def difference(a, b):
    if a.size != b.size:
        return {"size_a": a.size, "size_b": b.size, "different_size": True}
    diff = ImageChops.difference(a, b)
    values = list(diff.get_flattened_data())
    return {
        "mean_channel_error": sum(sum(pixel) for pixel in values) / (len(values) * 3),
        "pixels_over_20": sum(max(pixel) > 20 for pixel in values) / len(values),
    }


def check(browser, reference, url):
    formal = browser.new_page(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
    approved = browser.new_page(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
    formal.goto(url, wait_until="networkidle")
    formal.get_by_role("navigation", name="选择档案库").get_by_role(
        "button", name="角色卡", exact=True
    ).click()
    formal.get_by_role("button", name="全部角色卡", exact=True).click()
    blank = formal.get_by_role("button", name="空白角色卡", exact=True).first
    expect(blank).to_be_enabled()
    blank.click(force=True)
    author = formal.get_by_role("dialog", name="新建角色卡", exact=True)
    author.get_by_label("角色名称", exact=True).fill("林见月")
    author.get_by_role("button", name="预览角色设定", exact=True).click()
    formal.get_by_role("button", name="确认保存到卡库", exact=True).click()
    formal.get_by_role("button", name="✧ 设计卡面", exact=True).click()
    editor = formal.get_by_role("dialog", name="设计角色卡面", exact=True)
    editor.get_by_label("身份描述", exact=True).fill("档案修复师")
    approved.goto(reference, wait_until="networkidle")
    approved.locator("#card-tab").click()
    approved.locator('#card-ring .card-object[data-id="c-moon"]:visible').first.click(force=True)
    approved.locator("#design-button").click()
    results = []
    for width, height in [(1440, 900), (900, 800), (390, 844)]:
        for page in [formal, approved]:
            page.set_viewport_size({"width": width, "height": height})
        # Allow ResizeObserver geometry, fonts and the reference's CSS to settle.
        formal.wait_for_timeout(180)
        approved.wait_for_timeout(180)
        native_panel = editor.locator("aside")
        native_card = editor.locator("[data-card-canvas]")
        approved_panel = approved.locator("#designer")
        approved_card = approved.locator("#card-ring .card-object.selected")
        formal.screenshot(path=str(OUT / f"formal-{width}.png"))
        approved.screenshot(path=str(OUT / f"approved-{width}.png"))
        for lhs, rhs in [(native_panel, approved_panel), (native_card, approved_card)]:
            a, b = lhs.bounding_box(), rhs.bounding_box()
            for key in ["x", "y", "width", "height"]:
                assert abs(a[key] - b[key]) <= 0.1, (width, key, a, b)
        # Data identifiers differ; mask only the ID stamp in this comparison.
        formal.add_style_tag(content='[data-card-canvas] [class*="number"] { visibility:hidden }')
        approved.add_style_tag(content=".card-object.selected .card-number { visibility:hidden }")
        panel_diff = difference(pixels(native_panel), pixels(approved_panel))
        rectangle = approved_card.bounding_box()
        native_pixels, reference_pixels = (
            card_pixels(formal, rectangle),
            card_pixels(approved, rectangle),
        )
        card_diff = difference(native_pixels, reference_pixels)
        native_pixels.save(OUT / f"formal-card-{width}.png")
        reference_pixels.save(OUT / f"approved-card-{width}.png")
        probes = {}
        for name, lhs, rhs in [
            (
                "heading",
                native_panel.locator("header"),
                approved_panel.locator(".designer-heading"),
            ),
            (
                "close",
                native_panel.get_by_role("button", name="关闭设计器"),
                approved_panel.locator("#cancel-design"),
            ),
            (
                "glyph",
                native_card.locator('[class*="_glyph_"]'),
                approved_card.locator(".card-front .card-glyph"),
            ),
            (
                "orbit",
                native_card.locator('[class*="_orbit_"]'),
                approved_card.locator(".card-front .card-orbit"),
            ),
            (
                "name",
                native_card.locator('[data-kind="name"]'),
                approved_card.locator('.card-front [data-kind="name"]'),
            ),
            (
                "face",
                native_card.locator('[data-face="front"]'),
                approved_card.locator(".card-front"),
            ),
        ]:
            read = """e => {const s=getComputedStyle(e),r=e.getBoundingClientRect();return {
                rect:{x:r.x,y:r.y,w:r.width,h:r.height},font:s.font,padding:s.padding,
                lineHeight:s.lineHeight,boxSizing:s.boxSizing,color:s.color,transform:s.transform
            };}"""
            probes[name] = {"formal": lhs.evaluate(read), "approved": rhs.evaluate(read)}
            all_styles = """e => { const s=getComputedStyle(e);return Object.fromEntries(
                Array.from(s).filter(k=>!k.startsWith('--')).map(k=>[k,s.getPropertyValue(k)])
            ); }"""
            actual_styles, expected_styles = lhs.evaluate(all_styles), rhs.evaluate(all_styles)
            probes[name]["different_styles"] = {
                key: [value, expected_styles[key]]
                for key, value in actual_styles.items()
                if value != expected_styles[key]
            }
        (OUT / f"probes-{width}.json").write_text(json.dumps(probes, indent=2), "utf-8")
        assert not panel_diff.get("different_size"), panel_diff
        assert not card_diff.get("different_size"), card_diff
        assert panel_diff["mean_channel_error"] < 0.1 and panel_diff["pixels_over_20"] < 0.005, (
            panel_diff
        )
        assert card_diff["mean_channel_error"] < 1 and card_diff["pixels_over_20"] < 0.005, (
            card_diff
        )
        results.append({"viewport": [width, height], "panel": panel_diff, "card": card_diff})
        formal.screenshot(path=str(OUT / f"formal-{width}.png"))
        approved.screenshot(path=str(OUT / f"approved-{width}.png"))
        pixels(native_panel).save(OUT / f"formal-panel-{width}.png")
        pixels(approved_panel).save(OUT / f"approved-panel-{width}.png")
        print(json.dumps(results[-1]), flush=True)
    (OUT / "comparison.json").write_text(json.dumps(results, indent=2), "utf-8")
    formal.close()
    approved.close()


if __name__ == "__main__":
    manifest = json.loads((REFERENCE / "sha256.json").read_text("utf-8"))
    for name, digest in manifest.items():
        assert hashlib.sha256((REFERENCE / name).read_bytes()).hexdigest() == digest
    OUT.mkdir(parents=True, exist_ok=True)
    handler = functools.partial(QuietHandler, directory=str(REFERENCE))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with owned_dev_web("dreamtalk-card-parity-") as url:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="msedge", headless=True)
                try:
                    check(browser, f"http://127.0.0.1:{server.server_port}/", url)
                finally:
                    browser.close()
    finally:
        server.shutdown()
        server.server_close()
