"""Offline browser regression: only synthetic HTTP fixtures; no Core or user storage."""
import json,re
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, expect
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/mobile-archive-reshape-20261113/touch"
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
    page.add_init_script("window.archiveFrames=0;const native=window.requestAnimationFrame.bind(window);window.requestAnimationFrame=cb=>native(t=>{window.archiveFrames++;cb(t)});")
    page.goto(BASE);page.wait_for_load_state("networkidle")
    expect(page.get_by_role("button",name="新卡／导入")).to_be_enabled()
    cdp=page.context.new_cdp_session(page)
    def touch(kind,x=0,y=0):
        cdp.send("Input.dispatchTouchEvent",dict(type=kind,touchPoints=[] if kind in ("touchEnd","touchCancel") else [dict(x=x,y=y)]))
    book=page.get_by_role("button",name="预览世界："+worlds[0]["name"],exact=True)
    def book_x():
        return book.evaluate("n=>new DOMMatrix(getComputedStyle(n).transform).m41*Number(getComputedStyle(n.closest('.mobile-native-books-frame')).zoom)")
    for direction in (-1,1):
        before=book_x();touch("touchStart",195,180);samples=[]
        for i in range(1,7):
            touch("touchMove",195+direction*90*i/6,180);page.wait_for_timeout(25)
            measured=book_x()-before;expected=direction*90*i/6
            assert abs(measured-expected)<4,(measured,expected)
            samples.append(measured)
        touch("touchCancel")
        assert not page.locator("[data-native-shelf][data-chosen]").count()
        page.wait_for_timeout(2400);checks.append(dict(stage="books",direction=direction,tracked_pixels=samples))
    page.get_by_role("button",name="全部角色卡",exact=True).click()
    root=page.get_by_role("group",name="角色卡")
    def blank():
        return root.evaluate("""n=>{
          const r=n.getBoundingClientRect();
          for(const u of [.87,.82,.75])for(const v of [.02,.98,.08,.92]){
            const x=r.x+r.width*u,y=r.y+r.height*v;
            if(document.elementFromPoint(x,y)===n)return {x,y};
          }throw new Error('synthetic_blank_touch_point_missing');
        }""")
    page.evaluate("""()=>{
      window.syntheticPointerTrace=[];
      for(const type of ['pointerdown','pointermove','pointerup','pointercancel'])window.addEventListener(type,e=>{
        window.syntheticPointerTrace.push({type,id:e.pointerId,x:e.clientX,y:e.clientY,card:e.target.closest?.('[data-card-id]')?.dataset.cardId,tag:e.target.tagName});
        if(window.syntheticPointerTrace.length>30)window.syntheticPointerTrace.shift();
      },true);
    }""")
    wraps=0
    for run in range(18):
        point=blank();x=point["x"];y=point["y"];before=float(root.get_attribute("data-offset"))
        step=float(root.get_attribute("data-step"));total=8*step
        touch("touchStart",x,y)
        for i in range(1,7):
            touch("touchMove",x-220*i/6,y);page.wait_for_timeout(18)
            actual=float(root.get_attribute("data-offset"))
            wanted=(before+220*i/6)%total
            if abs(actual-wanted)>=.15:
                diagnostic=dict(run=run,point=point,actual=actual,wanted=wanted,trace=page.evaluate("window.syntheticPointerTrace"))
                (OUT/"touch-failure.json").write_text(json.dumps(diagnostic,ensure_ascii=False,indent=2),encoding="utf-8")
                raise AssertionError(diagnostic)
        touch("touchCancel" if run==0 else "touchEnd");page.wait_for_timeout(80)
        after=float(root.get_attribute("data-offset"));wraps+=int(after<before)
        assert root.locator("[data-card-slot]").count()<=5
        assert not page.get_by_role("button",name="归位角色卡").count()
        assert not page.get_by_role("dialog").count()
    assert wraps>=1,wraps
    actor=root.locator("[data-card-id]").filter(has_not=page.locator("[disabled]"))
    visible=page.locator("[data-card-slot][data-card-id]").evaluate_all("nodes=>nodes.filter(n=>n.dataset.cardId&&getComputedStyle(n).pointerEvents!=='none').map(n=>({id:n.dataset.cardId,rect:n.getBoundingClientRect().toJSON()}))")
    chosen=next(item for item in visible if 40<item["rect"]["x"]+item["rect"]["width"]/2<350)
    page.locator('[data-card-id="'+chosen["id"]+'"]').focus();page.keyboard.press("Enter")
    expect(page.get_by_role("button",name="归位角色卡")).to_be_visible()
    page.wait_for_timeout(800);before=page.evaluate("window.archiveFrames");page.wait_for_timeout(650)
    idle=page.evaluate("window.archiveFrames")-before
    assert idle<=2,("Unexpected continuing frame loop while inspecting a stationary card",idle)
    assert not errors,errors
    assert not external,external
    assert not unexpected,unexpected
    (OUT/"touch-regression.json").write_text(json.dumps(dict(passed=True,checks=checks,card_full_laps=wraps,card_rendered_limit=5,stationary_selected_frames=idle,errors=errors,external=external),ensure_ascii=False,indent=2),encoding="utf-8")
    print("PASS physical book drag tracks both directions through scoped scale; native card blank-drag tracks, cancels and wraps; retained bounded actors; stationary selection has no continuing frame loop.")
    browser.close()
