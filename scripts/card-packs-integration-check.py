"""Approved fixed visuals against the real UI/Core in an owned disposable runtime."""

import hashlib
import io
import json
import re
from pathlib import Path

from browser_runtime import owned_dev_web
from PIL import Image, ImageChops
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/card-packs-integration"
REFERENCE = ROOT / "tests/fixtures/card_pack_visual_reference"


def switch(page, name="角色卡"):
    page.get_by_role("navigation", name="选择档案库").get_by_role(
        "button", name=name, exact=True
    ).click()


def choose(page, name="月下拾光"):
    page.get_by_role("button", name="选择卡包：" + name, exact=True).click(force=True)
    expect(page.get_by_role("slider", name=re.compile("卡包封口"))).to_have_attribute(
        "aria-disabled", "false"
    )


def real_client(expression):
    return (
        """async () => {
      const {discoverConnection} = await import('/src/connection.ts');
      const {CoreClient} = await import('/@fs/D:/LivingWorld/packages/api-client/src/index.ts');
      const client = new CoreClient(await discoverConnection());
    """
        + expression
        + "}"
    )


def seed(page):
    return page.evaluate(
        real_client("""
      const {getSnapshot,previewClient} = await import('/src/previews/card-packs/previewStore.ts');
      const state=getSnapshot(), ids=new Map();
      for (const card of state.cards) {
        const {draft}=await previewClient().libraryCard(card.card_id);
        const review=await client.previewLibraryEditor(draft);
        const saved=await client.confirmLibraryCard(review);
        await client.saveLibraryDesign({...saved,design:card.design},card.design);
        ids.set(card.card_id,saved.card_id);
      }
      for (const pack of state.packs) await client.saveCardPack({
        ...pack,revision:0,cardIds:pack.cardIds.map(id=>ids.get(id))});
      return {cards:(await client.libraryCards()).length,packs:(await client.cardPacks()).length};
    """)
    )


def compare(locator, filename):
    raw = locator.screenshot()
    actual, expected = (
        Image.open(io.BytesIO(raw)).convert("RGB"),
        Image.open(REFERENCE / filename).convert("RGB"),
    )
    (OUT / filename).write_bytes(raw)
    assert actual.size == expected.size, (filename, actual.size, expected.size)
    pixels = list(ImageChops.difference(actual, expected).get_flattened_data())
    mean = sum(sum(pixel) for pixel in pixels) / (len(pixels) * 3)
    over = sum(max(pixel) > 20 for pixel in pixels) / len(pixels)
    # CSS 3D back-face rasterization varies between compositor runs, especially
    # the tiny count label. Keep raw deltas; validate its live geometry/styles
    # separately against the preview using this exact component.
    limits = (1.25, 0.02) if filename.endswith("-back.png") else (0.3, 0.003)
    assert mean < limits[0] and over < limits[1], (filename, mean, over)
    return {
        "image": filename,
        "size": actual.size,
        "mean_channel_error": mean,
        "pixels_over_20": over,
    }


def visuals(browser, url):
    results = []
    for width, height in [(1440, 1000), (900, 800), (390, 844)]:
        page = browser.new_page(
            viewport={"width": width, "height": height}, reduced_motion="reduce"
        )
        page.goto(url, wait_until="networkidle")
        switch(page)
        choose(page)
        slot = page.locator('[class*="packSlot"][data-selected=true]')
        page.wait_for_timeout(350)
        results.append(compare(slot, f"{width}-front.png"))
        page.get_by_role("button", name="背面", exact=True).click()
        page.wait_for_timeout(350)
        results.append(compare(slot, f"{width}-back.png"))
        approved = browser.new_page(
            viewport={"width": width, "height": height}, reduced_motion="reduce"
        )
        approved.goto(url + "card-packs-preview.html", wait_until="networkidle")
        switch(approved)
        choose(approved)
        approved.get_by_role("button", name="背面", exact=True).click()
        approved.wait_for_timeout(350)
        reference_slot = approved.locator('[class*="packSlot"][data-selected=true]')
        actual_rect, reference_rect = slot.bounding_box(), reference_slot.bounding_box()
        for key in ["x", "y", "width", "height"]:
            assert abs(actual_rect[key] - reference_rect[key]) < 0.01, (width, key)
        read_styles = """e => [e,...e.querySelectorAll('*')].map(node=>{
          const s=getComputedStyle(node);return [s.width,s.height,s.font,s.color,s.transform,
            s.backgroundImage,s.backgroundColor,s.opacity,s.borderRadius];})"""
        assert slot.evaluate(read_styles) == reference_slot.evaluate(read_styles), width
        approved.close()
        page.get_by_role("button", name="设计与装卡", exact=True).click()
        editor = page.get_by_role("dialog", name="设计卡包", exact=True)
        page.wait_for_timeout(180)
        results.append(compare(editor.locator("[data-pack-canvas]"), f"{width}-canvas.png"))
        results.append(compare(editor.locator("aside"), f"{width}-panel.png"))
        page.screenshot(path=str(OUT / f"formal-{width}.png"))
        page.close()
    return results


def behavior(page, url):
    page.goto(url, wait_until="networkidle")
    switch(page)
    choose(page)
    solid = page.locator("[data-selected=true] [data-pack-solid]")
    rect = solid.bounding_box()
    x, y = rect["x"] + rect["width"] / 2, rect["y"] + rect["height"] * 0.58
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 280, y + 16, steps=20)
    page.mouse.up()
    expect(solid).to_have_attribute("data-visible-face", "back")
    assert solid.locator("[data-pack-face]").count() == 2
    assert solid.locator('[class*="foldedRim"]').count() == 2
    page.get_by_role("button", name="正面", exact=True).click()
    page.wait_for_timeout(350)
    page.get_by_role("button", name="设计与装卡", exact=True).click()
    editor = page.get_by_role("dialog", name="设计卡包", exact=True)
    editor.get_by_role("checkbox", name=re.compile("白榆")).check()
    editor.get_by_role("checkbox", name=re.compile("陆听澜")).uncheck()
    editor.get_by_role("button", name="背面", exact=True).click()
    editor.get_by_role("button", name="暮色紫", exact=True).click()
    image = io.BytesIO()
    photo = Image.new("RGB", (700, 1000), "#315775")
    photo.paste("#986b69", (350, 0, 700, 1000))
    photo.save(image, "PNG")
    editor.locator('input[type="file"]').set_input_files(
        {"name": "synthetic.png", "mimeType": "image/png", "buffer": image.getvalue()}
    )
    crop = page.get_by_role("dialog", name="裁剪卡包图片", exact=True)
    crop.get_by_role("button", name="使用此区域", exact=True).click()
    expect(crop).to_have_count(0)
    expect(editor.locator("[data-pack-canvas] img:not([aria-hidden=true])")).to_have_count(1)
    editor.get_by_role("button", name="保存卡包", exact=True).click()
    expect(editor).to_have_count(0)
    page.reload(wait_until="networkidle")
    switch(page)
    choose(page)
    page.get_by_role("button", name="背面", exact=True).click()
    page.wait_for_timeout(350)
    expect(
        page.locator("[data-selected=true] [data-pack-face=back] img:not([aria-hidden=true])")
    ).to_have_count(1)
    page.get_by_role("button", name="设计与装卡", exact=True).click()
    editor = page.get_by_role("dialog", name="设计卡包", exact=True)
    editor.get_by_role("button", name="背面", exact=True).click()
    editor.get_by_role("button", name="重新裁剪", exact=True).click()
    expect(page.get_by_role("dialog", name="裁剪卡包图片", exact=True)).to_be_visible()
    page.get_by_role("dialog", name="裁剪卡包图片", exact=True).get_by_role(
        "button", name="取消", exact=True
    ).click()
    editor.get_by_role("button", name="关闭卡包设计器", exact=True).click()
    slider = page.get_by_role("slider", name=re.compile("卡包封口"))
    expect(slider).to_have_attribute("aria-disabled", "false")
    # Actually cut from right to left, including the edited back face.
    r = slider.bounding_box()
    y = r["y"] + r["height"] / 2
    page.mouse.move(r["x"] + r["width"] * 0.94, y)
    page.mouse.down()
    page.mouse.move(r["x"] + r["width"] * 0.06, y, steps=22)
    page.mouse.up()
    page.get_by_role("button", name=re.compile("返回卡包")).wait_for(timeout=7000)
    expect(page.get_by_role("button", name="查看角色卡：白榆", exact=True).first).to_be_visible()
    expect(page.get_by_role("button", name="查看角色卡：陆听澜", exact=True)).to_have_count(0)
    # New cards from an opened pack are enrolled without removing them from the global library.
    blank = page.get_by_role("button", name="空白角色卡", exact=True).first
    blank.focus()  # The ring brings a keyboard-focused slot into view.
    blank.press("Enter")
    author = page.get_by_role("dialog", name="新建角色卡", exact=True)
    author.get_by_label("角色名称", exact=True).fill("装包回归角色")
    author.get_by_role("button", name="预览角色设定", exact=True).click()
    page.get_by_role("button", name="确认保存到卡库", exact=True).click()
    expect(page.get_by_role("button", name="✧ 设计卡面", exact=True)).to_be_visible()
    state = page.evaluate(
        real_client("return {cards:await client.libraryCards(),packs:await client.cardPacks()};")
    )
    item = next(card for card in state["cards"] if card["name"] == "装包回归角色")
    assert (
        item["card_id"]
        in next(pack for pack in state["packs"] if pack["name"] == "月下拾光")["cardIds"]
    )
    assert len(state["cards"]) == 9 and not item["world_ids"]
    page.get_by_role("button", name=re.compile("返回卡包")).click()
    choose(page)
    expect(page.get_by_role("slider", name=re.compile("卡包封口"))).to_have_attribute(
        "aria-valuenow", "0"
    )
    switch(page, "世界书")
    switch(page)
    expect(page.get_by_role("heading", name="下一次相遇，正等待拆封。", exact=True)).to_be_visible()
    page.get_by_role("button", name="全部角色卡", exact=True).click()
    expect(page.get_by_role("button", name="查看角色卡：陆听澜", exact=True).first).to_be_visible()
    page.screenshot(path=str(OUT / "all-cards.png"))
    return {
        "rotation_depth": "passed",
        "membership_persisted": "passed",
        "back_image_recrop_after_reload": "passed",
        "actual_cut_spill_reseal": "passed",
        "new_card_auto_enrol_source_retained": "passed",
        "all_cards_preserved": "passed",
    }


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name, digest in json.loads((REFERENCE / "sha256.json").read_text()).items():
        assert hashlib.sha256((REFERENCE / name).read_bytes()).hexdigest() == digest, name
    with owned_dev_web("dreamtalk-pack-integration-") as url, sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto(url, wait_until="networkidle")
            assert seed(page) == {"cards": 8, "packs": 6}
            result = {
                "visuals": visuals(browser, url),
                "behavior": behavior(page, url),
                "page_errors": errors,
            }
            assert not errors, errors
            (OUT / "checks.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(json.dumps(result, ensure_ascii=False), flush=True)
        except Exception:
            page.screenshot(path=str(OUT / "failure.png"))
            (OUT / "failure-dom.txt").write_text(
                page.locator("body").inner_text(), encoding="utf-8"
            )
            raise
        finally:
            browser.close()
