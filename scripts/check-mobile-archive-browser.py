"""Offline browser regression: only synthetic HTTP fixtures; no Core or user storage."""
import json,re
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, expect
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/mobile-archive-reshape-20261113/browser"
OUT.mkdir(parents=True,exist_ok=True)
BASE = "http://127.0.0.1:1441"
worlds = [dict(world_id="synthetic-world-"+str(i), name=name, world_time="0", time_scale="1", clock_state="paused", runtime_state="ready") for i,name in enumerate(["星海回响","雨后咖啡馆","未完的夏日"])]
cards = [dict(card_id="synthetic-card-"+str(i), name=name, revision=1, design=None, world_ids=[]) for i,name in enumerate(["林间来信","晴川","星野","冬日旅人"])]
packs=[]
mutations=[]
worlds[0]["world_time"]="43200000000"
errors, external, unexpected, checks = [], [], [], []
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe", headless=True)
    page = browser.new_page(viewport={"width":390,"height":844}, device_scale_factor=1,has_touch=True,is_mobile=True,reduced_motion="no-preference")
    page.on("pageerror", lambda error: errors.append(str(error)))
    def route(request):
        path=urlsplit(request.request.url)
        if path.netloc != "127.0.0.1:1441":
            external.append(path.netloc);request.abort();return
        if not path.path.startswith("/api/"):
            request.continue_();return
        method=request.request.method
        if path.path.endswith("/card-packs") and method=="GET": value=packs
        elif "/card-packs/" in path.path and path.path.endswith("/discard"):
            value={"discarded":True}
        elif "/card-packs/" in path.path and method in ("PUT","DELETE"):
            pack_id=path.path.rsplit("/",1)[-1];body=request.request.post_data_json
            existing=next((item for item in packs if item["id"]==pack_id),None)
            revision=existing["revision"] if existing else 0
            if body["expected_revision"]!=revision:
                request.fulfill(status=409,json={"error":"synthetic_revision_conflict"});return
            mutations.append(dict(method=method,id=pack_id,expected_revision=revision))
            if method=="PUT":
                value=dict(id=pack_id,revision=revision+1,name=body["name"],subtitle=body["subtitle"],cardIds=body["cardIds"],design=body["design"])
                if existing:packs[packs.index(existing)]=value
                else:packs.append(value)
            else:
                packs.remove(existing);value={"removed":True}
        elif path.path.endswith("/worlds"): value=worlds
        elif path.path.endswith("/world-covers"): value=[]
        elif path.path.endswith("/card-library"): value=cards
        elif path.path.endswith("/cover"): value=dict(world_id=worlds[0]["world_id"],mode="text",title=worlds[0]["name"],show_title=True,faces={},revision=0)
        else:
            unexpected.append(path.path);request.fulfill(status=500,json={"error":"synthetic_route_missing"});return
        request.fulfill(status=200,json=value)
    page.route("**/*", route)
    page.add_init_script("window.__DREAMTALK_MOBILE_TEST_HOST__=async function(op){if(op==='connection')return {endpoint:'"+BASE+"',token:'synthetic-offline',generation:'synthetic'};throw new Error('synthetic_unexpected_host');};")

    page.add_init_script("localStorage.setItem('livingworld.lastWorldId','synthetic-world-0')")
    page.goto(BASE);page.wait_for_load_state("networkidle")
    expect(page.get_by_role("button",name="新卡／导入")).to_be_enabled()
    page.get_by_role("button",name="创建新卡包",exact=True).click(force=True)
    page.get_by_role("textbox",name="卡包名称").fill("首次合成卡包")
    page.get_by_role("button",name="保存卡包",exact=True).click()
    expect(page.locator("[data-pack-collection]")).to_have_attribute("data-pack-mode","selected")
    assert len(packs)==1 and mutations[0]["expected_revision"]==0
    page.reload();page.wait_for_load_state("networkidle")
    page.get_by_role("button",name="选择卡包：首次合成卡包",exact=True).click(force=True)
    page.get_by_role("button",name="删除卡包",exact=True).click()
    page.get_by_role("button",name="确认删除卡包",exact=True).click()
    expect(page.locator("[data-pack-collection]")).to_have_attribute("data-pack-mode","browse",timeout=6000)
    assert not packs and len(cards)==4
    first_create_mutations=list(mutations);mutations.clear()
    pack=page.evaluate("async()=>{const m=await import('/src/world/cards/packs/packDesign.ts');const p=m.defaultPack('夜航来信');p.id='synthetic-pack';p.revision=1;p.cardIds=['synthetic-card-0','synthetic-card-1'];return p;}")
    packs.append(pack);page.reload();page.wait_for_load_state("networkidle")
    expect(page.locator(".mobile-archive-room [data-kind='sun']")).to_have_count(1)
    for width,height in [(390,844),(320,640),(412,915),(844,390),(768,1024)]:
        page.set_viewport_size({"width":width,"height":height});page.wait_for_timeout(200)
        geometry=page.evaluate("""() => {
          const a=document.querySelector('.mobile-archive-upper').getBoundingClientRect(),b=document.querySelector('.mobile-archive-lower').getBoundingClientRect();
          const book=document.querySelector('.mobile-native-books'),pack=document.querySelector('[data-pack-part="packStage"]');
          return {divider:b.y,top:a.height,bottom:b.height,overflow:document.documentElement.scrollWidth>innerWidth,bookActors:book.querySelectorAll('[data-book-key]').length,packActors:pack.querySelectorAll('[data-pack-slot]').length};
        }""")
        assert abs(geometry["divider"]-height/2)<=1 and abs(geometry["top"]-geometry["bottom"])<=1,geometry
        assert not geometry["overflow"] and 1<=geometry["bookActors"]<=25 and geometry["packActors"]<=5,geometry
        page.screenshot(path=str(OUT/("home-"+str(width)+"x"+str(height)+".png")));checks.append(dict(size=[width,height],**geometry))
    page.set_viewport_size({"width":390,"height":844});page.wait_for_timeout(200)
    cdp=page.context.new_cdp_session(page)
    def swipe(node,dx,dy=0,cancel=False,point=None):
        box=node.bounding_box();x,y=point or (box["x"]+box["width"]*.5,box["y"]+box["height"]*.5)
        cdp.send("Input.dispatchTouchEvent",dict(type="touchStart",touchPoints=[dict(x=x,y=y)]))
        for i in range(1,9):
            cdp.send("Input.dispatchTouchEvent",dict(type="touchMove",touchPoints=[dict(x=x+dx*i/8,y=y+dy*i/8)]));page.wait_for_timeout(16)
        cdp.send("Input.dispatchTouchEvent",dict(type="touchCancel" if cancel else "touchEnd",touchPoints=[]))
    book=page.get_by_role("button",name="预览世界："+worlds[0]["name"],exact=True)
    book.evaluate("node=>window.__syntheticBook=node");book.click()
    expect(page.get_by_role("button",name="进入世界")).to_be_enabled(timeout=6000)
    assert book.evaluate("node=>node===window.__syntheticBook&&node.classList.contains('is-chosen')")
    before=float(book.get_attribute("data-yaw"))
    for _ in range(5):swipe(page.locator("[data-native-shelf]"),110,point=(145,200))
    page.wait_for_timeout(300);assert abs(float(book.get_attribute("data-yaw"))-before)>300
    page.get_by_label("切换书本面").click();page.get_by_role("button",name="背面",exact=True).click()
    expect(book).to_have_attribute("data-face","back",timeout=4000);page.screenshot(path=str(OUT/"book-back.png"))
    page.set_viewport_size({"width":320,"height":640});page.wait_for_timeout(200);page.screenshot(path=str(OUT/"book-selected-320.png"))
    page.set_viewport_size({"width":390,"height":844});page.wait_for_timeout(200)
    page.get_by_role("button",name="设计书本").click();expect(page.get_by_role("dialog",name="设计世界书")).to_be_visible()
    page.get_by_role("button",name="关闭",exact=True).click();page.get_by_role("button",name="归位世界书").click();page.wait_for_timeout(1200)
    assert page.evaluate("window.__syntheticBook.isConnected")
    pack_actor=page.locator('[data-pack-id="synthetic-pack"]');pack_actor.evaluate("node=>window.__syntheticPack=node")
    page.get_by_role("button",name="选择卡包：夜航来信",exact=True).click(force=True)
    solid=pack_actor.locator("[data-pack-solid]");seal=page.get_by_role("slider",name=re.compile("卡包封口"))
    expect(seal).to_have_attribute("aria-disabled","false");assert pack_actor.evaluate("node=>node===window.__syntheticPack")
    for _ in range(5):swipe(solid,110)
    if page.get_by_role("button",name="背面",exact=True).count():page.get_by_role("button",name="背面",exact=True).click()
    expect(solid).to_have_attribute("data-visible-face","back");page.screenshot(path=str(OUT/"pack-back.png"))
    page.get_by_role("button",name="设计与装卡").click()
    editor=page.locator("[data-pack-editor]");expect(editor).to_be_visible()
    editor.get_by_label(cards[2]["name"],exact=False).check();page.screenshot(path=str(OUT/"pack-editor.png"))
    page.get_by_role("button",name="保存卡包",exact=True).click()
    expect(editor).to_have_count(0);assert packs[0]["revision"]==2 and len(packs[0]["cardIds"])==3 and len(mutations)==1
    seal=page.get_by_role("slider",name=re.compile("卡包封口"));expect(seal).to_have_attribute("aria-disabled","false")
    def cut(cancel):
        box=seal.bounding_box();x=box["x"]+box["width"]*.04;y=box["y"]+box["height"]*.5
        cdp.send("Input.dispatchTouchEvent",dict(type="touchStart",touchPoints=[dict(x=x,y=y)]))
        end=.55 if cancel else 1.04
        for i in range(1,9):
            cdp.send("Input.dispatchTouchEvent",dict(type="touchMove",touchPoints=[dict(x=x+box["width"]*end*i/8,y=y)]));page.wait_for_timeout(16)
        cdp.send("Input.dispatchTouchEvent",dict(type="touchCancel" if cancel else "touchEnd",touchPoints=[]))
    cut(True);expect(seal).to_have_attribute("aria-valuenow","0")
    cut(False);expect(page.locator("[data-pack-collection]")).to_have_attribute("data-pack-mode","cards",timeout=6000)
    deck=page.get_by_role("group",name="角色卡");expect(deck).to_have_attribute("data-items","8")
    actor=deck.locator('[data-card-id="synthetic-card-0"]').first;actor.evaluate("node=>window.__syntheticCard=node")
    actor.click(force=True);expect(page.get_by_role("button",name="归位角色卡")).to_be_visible()
    selected=page.get_by_role("group",name="旋转角色卡")
    assert actor.evaluate("node=>node===window.__syntheticCard&&node.dataset.selected==='true'")
    before=float(actor.get_attribute("data-yaw"))
    for _ in range(5):swipe(selected,110,point=(125,640))
    assert abs(float(actor.get_attribute("data-yaw"))-before)>300
    if page.get_by_role("button",name="背面",exact=True).count():page.get_by_role("button",name="背面",exact=True).click()
    expect(actor).to_have_attribute("data-face","back");page.screenshot(path=str(OUT/"card-back.png"))
    page.set_viewport_size({"width":320,"height":640});page.wait_for_timeout(200);page.screenshot(path=str(OUT/"card-selected-320.png"))
    page.set_viewport_size({"width":390,"height":844});page.wait_for_timeout(200)
    page.get_by_role("button",name="设计卡面").click();expect(page.locator("[data-card-editor]")).to_be_visible();page.screenshot(path=str(OUT/"card-editor.png"))
    page.get_by_role("button",name="关闭设计器",exact=True).click()
    expect(page.locator("[data-pack-collection]")).to_have_attribute("data-pack-mode","cards");assert page.evaluate("window.__syntheticCard.isConnected")
    page.get_by_role("button",name="归位角色卡").click();page.wait_for_timeout(600);assert page.evaluate("window.__syntheticCard.isConnected")
    page.get_by_role("button",name=re.compile("^返回卡包")).click()
    page.get_by_role("button",name="选择卡包：夜航来信",exact=True).click(force=True)
    page.get_by_role("button",name="删除卡包",exact=True).click()
    page.get_by_role("button",name="取消，保留卡包").click();assert len(mutations)==1
    page.get_by_role("button",name="删除卡包",exact=True).click();page.get_by_role("button",name="确认删除卡包",exact=True).click()
    expect(page.locator("[data-pack-collection]")).to_have_attribute("data-pack-mode","browse",timeout=6000)
    assert not packs and len(cards)==4 and [x["method"] for x in mutations]==["PUT","DELETE"]
    assert not errors,errors
    assert not external,external
    assert not unexpected,unexpected
    (OUT/"browser-check.json").write_text(json.dumps(dict(passed=True,checks=checks,first_create_mutations=first_create_mutations,mutations=mutations,errors=errors,external=external,unexpected=unexpected,same_actor_continuity=True,original_cards_retained=len(cards)),ensure_ascii=False,indent=2),encoding="utf-8")
    print("PASS five viewports; original Windows actors and actual touch; seal cancel/open; card editor return; CAS save; original cards retained. External traffic blocked.")
    browser.close()
