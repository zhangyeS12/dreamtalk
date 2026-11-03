"""Actual React/Core/SQLite card flow in an owned, disposable browser runtime."""

import io
import json
from pathlib import Path

from browser_runtime import owned_dev_web
from PIL import Image
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts" / "card-library-checks"
OUTPUT.mkdir(parents=True, exist_ok=True)


def check(page):
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.get_by_role("region", name="世界书架", exact=True).wait_for(timeout=30000)
    switch = page.get_by_role("navigation", name="选择档案库")
    # Real world creation, preserving the existing native book implementation.
    blank = page.get_by_role("button", name="创建或导入一个新世界，空白书 1", exact=True)
    expect(blank).to_be_enabled()
    blank.focus()
    blank.press("Enter")
    page.get_by_role("button", name="创建世界", exact=True).click()
    page.get_by_role("textbox", name="世界名称", exact=True).fill("Card library test world")
    page.get_by_role("button", name="创建档案并添加世界书", exact=True).click()
    sheet = page.get_by_role("dialog", name="「Card library test world」的世界书", exact=True)
    sheet.get_by_role("button", name="收起", exact=True).click()
    switch.get_by_role("button", name="角色卡", exact=True).click()
    page.get_by_role("button", name="全部角色卡", exact=True).click()
    page.get_by_role("button", name="空白角色卡", exact=True).first.click(force=True)
    author = page.get_by_role("dialog", name="新建角色卡", exact=True)
    author.get_by_label("角色名称", exact=True).fill("Library synthetic character")
    author.get_by_label("人物描述", exact=True).fill("A synthetic offline regression character.")
    author.get_by_role("button", name="预览角色设定", exact=True).click()
    review = page.get_by_role("dialog", name="核对角色卡", exact=True)
    review.get_by_role("button", name="确认保存到卡库", exact=True).click()
    print("card_authoring_passed", flush=True)
    expect(review).to_have_count(0)
    page.get_by_role("button", name="✧ 设计卡面", exact=True).wait_for()
    card = page.locator("[data-card-id][data-selected=true]")
    expect(card).to_have_count(1)
    page.wait_for_timeout(500)
    start = card.evaluate("e => e.style.transform")
    bounds = card.bounding_box()
    x, y = bounds["x"] + bounds["width"] / 2, bounds["y"] + bounds["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 90, y + 35, steps=8)
    page.mouse.up()
    assert card.evaluate("e => e.style.transform").startswith("translate3d(0px, -14px, 100px)")
    assert card.evaluate("e => e.style.transform") != start
    rotated = card.evaluate("e => e.style.transform")
    card.press("ArrowRight")
    assert card.evaluate("e => e.style.transform") != rotated
    assert page.locator("[class*='dragCaption']").count() == 0
    page.get_by_role("button", name="背面", exact=True).click()
    assert card.locator("[data-face=front]").evaluate("e => e.hidden")
    assert not card.locator("[data-face=back]").evaluate("e => e.hidden")
    page.get_by_role("button", name="正面", exact=True).click()
    page.get_by_role("button", name="✧ 设计卡面", exact=True).click()
    designer = page.get_by_role("dialog", name="设计角色卡面", exact=True)
    designer.get_by_role("button", name="背面", exact=True).click()
    designer.get_by_role("button", name="暮色紫", exact=True).click()
    designer.get_by_role("button", name="＋ 添加自定义文字", exact=True).click()
    designer.get_by_label("文字内容", exact=True).fill("Independent back")
    designer.get_by_role("button", name="正面", exact=True).click()
    assert "Independent back" not in designer.locator("[data-card-canvas]").inner_text()
    designer.get_by_role("button", name="对称到背面", exact=True).click()
    expect(designer.get_by_role("button", name="月夜蓝", exact=True)).to_have_attribute(
        "aria-pressed", "true"
    )
    designer.get_by_role("button", name="撤销上次对称", exact=True).click()
    expect(designer.get_by_role("button", name="暮色紫", exact=True)).to_have_attribute(
        "aria-pressed", "true"
    )
    assert "Independent back" in designer.locator("[data-card-canvas]").inner_text()
    designer.get_by_role("button", name="正面", exact=True).click()
    image = io.BytesIO()
    photo = Image.new("RGB", (900, 600), "#a14466")
    photo.paste("#305c8e", (450, 0, 900, 600))
    photo.save(image, format="PNG")
    designer.locator('input[type="file"]').set_input_files(
        {"name": "synthetic.png", "mimeType": "image/png", "buffer": image.getvalue()}
    )
    cropper = page.get_by_role("dialog", name="裁剪卡面图片", exact=True)
    cropper.get_by_role("button", name="使用此区域", exact=True).wait_for()
    cropper.get_by_role("button", name="旋转90°", exact=True).click()
    cropper.get_by_label("图片缩放", exact=True).focus()
    cropper.get_by_label("图片缩放", exact=True).press("ArrowRight")
    cropper.get_by_label("裁剪框大小", exact=True).focus()
    cropper.get_by_label("裁剪框大小", exact=True).press("ArrowLeft")
    cropper.get_by_role("button", name="使用此区域", exact=True).click()
    expect(cropper).to_have_count(0)
    expect(designer.locator("[data-card-canvas] img")).to_have_count(1)
    designer.get_by_role("button", name="保存设计", exact=True).click()
    print("card_faces_and_crop_passed", flush=True)
    expect(designer).to_have_count(0)
    page.reload(wait_until="networkidle")
    switch.get_by_role("button", name="角色卡", exact=True).click()
    page.get_by_role("button", name="全部角色卡", exact=True).click()
    shown = page.get_by_role("button", name="查看角色卡：Library synthetic character", exact=True)
    shown.click(force=True)
    assert not page.locator("[data-card-id][data-selected=true] [data-face=front]").evaluate(
        "e => e.hidden"
    )
    page.get_by_role("button", name="背面", exact=True).click()
    expect(page.locator("[data-card-id][data-selected=true] [data-face=back]")).to_contain_text(
        "Independent back"
    )
    page.get_by_role("button", name="归位", exact=True).click()
    # Carry must work only after returning to the natural floating state.
    page.wait_for_timeout(500)
    bounds = shown.bounding_box()
    x, y = bounds["x"] + bounds["width"] / 2, bounds["y"] + bounds["height"] / 2
    nav = switch.bounding_box()
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(nav["x"] + nav["width"] / 2, nav["y"] + nav["height"] / 2, steps=15)
    expect(switch.get_by_role("button", name="世界书", exact=True)).to_have_attribute(
        "aria-pressed", "true"
    )
    book = page.locator("[data-book-key^='world:']").evaluate_all(
        """nodes => nodes.map(e => {
          const r=e.getBoundingClientRect();
          return {key:e.dataset.bookKey,x:r.x,y:r.y,w:r.width,h:r.height};
        }).find(r=>r.w>0 && r.x>20 && r.x+r.w<innerWidth-20)"""
    )
    assert book
    page.mouse.move(book["x"] + book["w"] / 2, book["y"] + book["h"] / 2, steps=10)
    page.mouse.up()
    join = page.get_by_role("dialog", name="将「Library synthetic character」加入世界", exact=True)
    join.get_by_role("button", name="预览加入内容", exact=True).click()
    expect(join).to_contain_text("初始地点：无")
    join.get_by_role("button", name="确认加入「Card library test world」", exact=True).click()
    print("card_carry_join_passed", flush=True)
    expect(join).to_have_count(0)
    switch.get_by_role("button", name="角色卡", exact=True).click()
    page.get_by_role("button", name="全部角色卡", exact=True).click()
    shown.click(force=True)
    expect(page.get_by_role("button", name="✧ 设计卡面", exact=True)).to_be_visible()
    page.wait_for_timeout(500)
    page.screenshot(path=str(OUTPUT / "integrated-wide.png"))
    # Escape cancellation releases capture, then a fresh click can still open a card.
    page.get_by_role("button", name="归位", exact=True).click()
    page.wait_for_timeout(500)
    page.emulate_media(reduced_motion="reduce")
    page.wait_for_timeout(100)
    pose = shown.evaluate("e => e.style.transform")
    page.wait_for_timeout(150)
    assert shown.evaluate("e => e.style.transform") == pose
    page.emulate_media(reduced_motion="no-preference")
    bounds = shown.bounding_box()
    page.mouse.move(bounds["x"] + bounds["width"] / 2, bounds["y"] + bounds["height"] / 2)
    page.mouse.down()
    page.mouse.move(bounds["x"] + bounds["width"] / 2 + 20, bounds["y"] + bounds["height"] / 2 + 20)
    page.keyboard.press("Escape")
    page.mouse.up()
    shown.click(force=True)
    expect(page.get_by_role("button", name="✧ 设计卡面", exact=True)).to_be_visible()
    page.get_by_role("button", name="角色设定", exact=True).click()
    editor = page.get_by_role("dialog", name="编辑角色设定", exact=True)
    editor.get_by_label("性格", exact=True).fill("A deliberate template edit.")
    editor.get_by_role("button", name="预览角色设定", exact=True).click()
    page.get_by_role("dialog", name="核对角色卡", exact=True).get_by_role(
        "button", name="确认保存到卡库", exact=True
    ).click()
    page.get_by_role("button", name="✧ 设计卡面", exact=True).wait_for()
    page.set_viewport_size({"width": 390, "height": 844})
    page.get_by_role("button", name="✧ 设计卡面", exact=True).click()
    designer = page.get_by_role("dialog", name="设计角色卡面", exact=True)
    expect(designer.get_by_role("button", name="保存设计", exact=True)).to_be_in_viewport()
    page.screenshot(path=str(OUTPUT / "integrated-mobile-diy.png"))
    designer.get_by_role("button", name="关闭设计器", exact=True).click()
    # Full CHARX sharing through the visible action, browser download, import preview and save.
    page.set_viewport_size({"width": 1440, "height": 1000})
    page.get_by_role("button", name="分享角色卡", exact=True).click()
    share = page.get_by_role("dialog", name="分享角色卡", exact=True)
    share.get_by_role("button", name="背面", exact=True).click()
    expect(share).to_contain_text("Independent back")
    with page.expect_download() as transfer:
        share.get_by_role("button", name="保存完整角色卡", exact=True).click()
    download = transfer.value
    assert download.suggested_filename.endswith(".charx")
    payload = Path(download.path()).read_bytes()
    share.get_by_role("button", name="关闭", exact=True).last.click()
    page.get_by_role("button", name="归位", exact=True).click()
    page.get_by_role("button", name="空白角色卡", exact=True).first.click(force=True)
    author = page.get_by_role("dialog", name="新建角色卡", exact=True)
    author.locator('input[type="file"]').set_input_files(
        {"name": download.suggested_filename, "mimeType": "application/zip", "buffer": payload}
    )
    review = page.get_by_role("dialog", name="核对角色卡", exact=True)
    expect(review).to_contain_text("完整角色卡：包含双面设计和")
    preview = review.get_by_role("region", name="分享卡面预览", exact=True)
    expect(preview.locator("img")).to_have_count(1)
    preview.get_by_role("button", name="背面", exact=True).click()
    expect(preview).to_contain_text("Independent back")
    page.set_viewport_size({"width": 390, "height": 844})
    page.screenshot(path=str(OUTPUT / "share-import-mobile.png"))
    review.get_by_role("button", name="确认保存到卡库", exact=True).click()
    page.get_by_role("button", name="✧ 设计卡面", exact=True).click()
    designer = page.get_by_role("dialog", name="设计角色卡面", exact=True)
    expect(designer.get_by_role("button", name="重新裁剪", exact=True)).to_be_visible()
    designer.get_by_role("button", name="背面", exact=True).click()
    expect(designer.locator("[data-card-canvas]")).to_contain_text("Independent back")
    designer.get_by_role("button", name="关闭设计器", exact=True).click()
    print("full_card_share_download_import_passed", flush=True)
    assert not errors, errors


if __name__ == "__main__":
    with owned_dev_web("dreamtalk-card-library-browser-") as url:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.goto(url, wait_until="networkidle")
            try:
                check(page)
            except Exception:
                page.screenshot(path=str(OUTPUT / "failure.png"))
                (OUTPUT / "failure-dom.txt").write_text(
                    page.locator("body").inner_text(), encoding="utf-8"
                )
                raise
            browser.close()
    print(
        json.dumps(
            {
                "card_library_ui_core_persistence": "passed",
                "independent_faces_crop_symmetry_undo": "passed",
                "fixed_view_and_cross_collection_carry": "passed",
                "mobile_diy": "passed",
                "full_card_share_download_import": "passed",
                "page_errors": 0,
            }
        )
    )
