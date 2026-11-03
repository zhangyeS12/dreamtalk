"""Exercise only the synthetic React preview. No Core, saves or providers."""

import io
import json
import re
from pathlib import Path

from PIL import Image
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/card-packs-preview"
URL = "http://127.0.0.1:8768/card-packs-preview.html"


def switch(page, name):
    page.get_by_role("navigation", name="选择档案库").get_by_role(
        "button", name=name, exact=True
    ).click()


def choose(page, name):
    # Floating object deliberately never meets Playwright's "stable" condition.
    page.get_by_role("button", name=f"选择卡包：{name}", exact=True).click(force=True)
    page.wait_for_timeout(700)


def cut_open(page, *, reverse=False, partial=False):
    cut = page.get_by_role("slider", name=re.compile("卡包封口"))
    expect(cut).to_have_attribute("aria-disabled", "false")
    rect = cut.bounding_box()
    left, right = rect["x"] + rect["width"] * 0.06, rect["x"] + rect["width"] * 0.94
    start, end = (right, left) if reverse else (left, right)
    if partial:
        end = start + (end - start) * 0.2
    y = rect["y"] + rect["height"] / 2
    page.mouse.move(start, y)
    page.mouse.down()
    page.mouse.move(end, y, steps=22)
    page.mouse.up()
    if partial:
        expect(cut).to_have_attribute("aria-valuenow", "0")
    else:
        page.get_by_role("button", name=re.compile("返回卡包")).wait_for(timeout=7000)


def check(page):
    errors, api_calls = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on(
        "request", lambda request: api_calls.append(request.url) if "/api/" in request.url else None
    )
    page.goto(URL, wait_until="networkidle")
    expect(page.get_by_role("region", name="世界书架", exact=True)).to_be_visible()
    page.screenshot(path=str(OUT / "worlds.png"))
    switch(page, "角色卡")
    page.screenshot(path=str(OUT / "packs-wide.png"))
    choose(page, "月下拾光")
    solid = page.locator("[data-selected=true] [data-pack-solid]")
    start = solid.get_attribute("style")
    bounds = solid.bounding_box()
    x, y = bounds["x"] + bounds["width"] / 2, bounds["y"] + bounds["height"] * 0.58
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 280, y + 16, steps=20)
    page.mouse.up()
    expect(solid).to_have_attribute("data-visible-face", "back")
    assert solid.get_attribute("style") != start
    # The transformed faces are distinct, and the sleeve has physical side planes.
    assert solid.locator("[data-pack-face]").count() == 2
    assert solid.locator("[class*='foldedRim']").count() == 2
    page.screenshot(path=str(OUT / "rotation-back.png"))
    page.get_by_role("button", name="正面", exact=True).click()
    page.wait_for_timeout(350)
    expect(solid).to_have_attribute("data-visible-face", "front")
    page.screenshot(path=str(OUT / "foil-front-checked.png"))
    cut_open(page, partial=True)
    # Cancelling capture resets the cut, including an out-of-band pointer gesture.
    slider = page.get_by_role("slider", name=re.compile("卡包封口"))
    slider.focus()
    page.keyboard.press("Escape")
    expect(page.get_by_role("heading", name="下一次相遇，正等待拆封。", exact=True)).to_be_visible()
    choose(page, "月下拾光")
    cut_open(page, reverse=True)
    expect(page.locator("[data-card-id]")).not_to_have_count(0)
    page.screenshot(path=str(OUT / "cards-wide.png"))
    page.get_by_role("button", name=re.compile("返回卡包")).click()
    choose(page, "月下拾光")
    expect(page.get_by_role("slider", name=re.compile("卡包封口"))).to_have_attribute(
        "aria-valuenow", "0"
    )
    page.get_by_role("button", name="设计与装卡", exact=True).click()
    editor = page.get_by_role("dialog", name="设计卡包", exact=True)
    editor.get_by_role("checkbox", name=re.compile("白榆")).check()
    editor.get_by_role("checkbox", name=re.compile("陆听澜")).uncheck()
    editor.get_by_role("button", name="背面", exact=True).click()
    editor.get_by_role("button", name="暮色紫", exact=True).click()
    image = io.BytesIO()
    source = Image.new("RGB", (700, 1000), "#315775")
    source.paste("#986b69", (350, 0, 700, 1000))
    source.save(image, format="PNG")
    editor.locator('input[type="file"]').set_input_files(
        {"name": "synthetic.png", "mimeType": "image/png", "buffer": image.getvalue()}
    )
    crop = page.get_by_role("dialog", name="裁剪卡包图片", exact=True)
    crop.get_by_role("button", name="使用此区域", exact=True).click()
    expect(crop).to_have_count(0)
    expect(editor.locator("[data-pack-canvas] img:not([aria-hidden=true])")).to_have_count(1)
    editor.get_by_role("button", name="正面", exact=True).click()
    expect(editor.locator("[data-pack-canvas] img:not([aria-hidden=true])")).to_have_count(0)
    editor.get_by_role("button", name="对称到背面", exact=True).click()
    expect(editor.locator("[data-pack-canvas] img:not([aria-hidden=true])")).to_have_count(0)
    editor.get_by_role("button", name="正面", exact=True).click()
    editor.get_by_role("button", name="撤销对称", exact=True).click()
    expect(editor.locator("[data-pack-canvas] img:not([aria-hidden=true])")).to_have_count(1)
    editor.get_by_role("button", name="保存卡包", exact=True).click()
    expect(editor).to_have_count(0)
    page.get_by_role("button", name="背面", exact=True).click()
    page.wait_for_timeout(350)
    expect(page.locator("[data-selected=true] [data-pack-solid]")).to_have_attribute(
        "data-visible-face", "back"
    )
    expect(
        page.locator("[data-selected=true] [data-pack-face=back] img:not([aria-hidden=true])")
    ).to_have_count(1)
    # The same top seal can also be opened while looking at the back.
    cut_open(page)
    names = set(
        page.locator("[data-card-id]").evaluate_all(
            "nodes=>nodes.map(e=>e.getAttribute('aria-label'))"
        )
    )
    assert "查看角色卡：白榆" in names, names
    assert "查看角色卡：陆听澜" not in names, names
    # The revealed objects retain the original fixed-view and DIY behavior.
    page.get_by_role("button", name="查看角色卡：林见月", exact=True).first.click(force=True)
    page.get_by_role("button", name="✧ 设计卡面", exact=True).click()
    card_editor = page.get_by_role("dialog", name="设计角色卡面", exact=True)
    expect(card_editor.get_by_role("button", name="保存设计", exact=True)).to_be_visible()
    card_editor.get_by_role("button", name="关闭设计器", exact=True).click()
    switch(page, "世界书")
    switch(page, "角色卡")
    expect(page.get_by_role("heading", name="下一次相遇，正等待拆封。", exact=True)).to_be_visible()
    # Create a real preview collection and explicitly choose its membership.
    page.get_by_role("button", name="创建卡包", exact=True).click()
    editor = page.get_by_role("dialog", name="设计卡包", exact=True)
    editor.get_by_label("卡包名称", exact=True).fill("我的测试卡包")
    editor.get_by_role("checkbox", name=re.compile("林见月")).check()
    editor.get_by_role("checkbox", name=re.compile("白榆")).check()
    editor.get_by_role("button", name="保存卡包", exact=True).click()
    expect(page.get_by_role("heading", name="我的测试卡包", exact=True)).to_be_visible()
    cut_open(page)
    assert (
        len(
            set(
                page.locator("[data-card-id]").evaluate_all("nodes=>nodes.map(e=>e.dataset.cardId)")
            )
        )
        == 2
    )
    page.get_by_role("button", name=re.compile("返回卡包")).click()
    page.set_viewport_size({"width": 390, "height": 844})
    page.screenshot(path=str(OUT / "packs-mobile.png"))
    choose(page, "我的测试卡包")
    cut_open(page)
    page.get_by_role("button", name=re.compile("返回卡包")).click()
    choose(page, "我的测试卡包")
    page.get_by_role("button", name="设计与装卡", exact=True).click()
    editor = page.get_by_role("dialog", name="设计卡包", exact=True)
    expect(editor.get_by_role("button", name="保存卡包", exact=True)).to_be_in_viewport()
    page.screenshot(path=str(OUT / "designer-mobile.png"))
    editor.get_by_role("button", name="关闭卡包设计器", exact=True).click()
    # Reduced-motion users can open using the same focused seal and keyboard.
    page.emulate_media(reduced_motion="reduce")
    slider = page.get_by_role("slider", name=re.compile("卡包封口"))
    slider.focus()
    slider.press("Enter")
    page.get_by_role("button", name=re.compile("返回卡包")).wait_for()
    assert not errors, errors
    assert not api_calls, api_calls
    return {
        "cut_partial_cancel_reverse": "passed",
        "free_rotation_depth_back_face": "passed",
        "pack_membership_creation": "passed",
        "independent_faces_crop_symmetry_undo": "passed",
        "existing_card_ring_and_designer": "passed",
        "reseal_on_return_and_reentry": "passed",
        "mobile_and_reduced_motion": "passed",
        "page_errors": 0,
        "core_api_calls": 0,
    }


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        try:
            result = check(page)
            (OUT / "checks.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(json.dumps(result), flush=True)
        except Exception:
            page.screenshot(path=str(OUT / "failure.png"))
            (OUT / "failure-dom.txt").write_text(
                page.locator("body").inner_text(), encoding="utf-8"
            )
            raise
        finally:
            browser.close()
