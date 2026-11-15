from pathlib import Path
import importlib,json,sys,tempfile,asyncio
from urllib.request import Request,urlopen
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"services/core/src"))
from livingworld.bootstrap import mobile_host
from playwright.sync_api import sync_playwright,expect
import httpx
class MemoryHost:
    def __init__(self,root):
        self.root=root
        settings={"provider_kind":"openai-compatible","model_id":"offline-check-model","base_url":"https://example.invalid/v1","max_billable_input_tokens":8192,"max_output_tokens":1024,"streaming":True,"timeout_ms":120000}
        self.value=json.dumps({"setup":settings,"secret_ref":"e59ca729-4b55-4a20-bb1d-f03f554337b4","secret":"synthetic-offline-credential"})
    def dataDirectory(self):return str(self.root)
    def secureRead(self):return self.value
    def secureWrite(self,value):self.value=value
class OfflineReply(httpx.AsyncByteStream):
    async def __aiter__(self):
        for text in ['“你好，','很高兴认识你。”']:
            yield ("data: "+json.dumps({"id":"offline","object":"chat.completion.chunk","model":"offline-check-model","choices":[{"index":0,"delta":{"content":text},"finish_reason":None}]},ensure_ascii=False)+"\n\n").encode()
            await asyncio.sleep(.04)
        yield ("data: "+json.dumps({"id":"offline","object":"chat.completion.chunk","model":"offline-check-model","choices":[{"index":0,"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":500,"completion_tokens":16,"total_tokens":516}})+"\n\ndata: [DONE]\n\n").encode()
outbound=[]
async def offline_send(self,request,*args,**kwargs):
    if request.url.host!="example.invalid":raise AssertionError("Unexpected outbound provider request")
    outbound.append(request.url.path)
    return httpx.Response(200,headers={"content-type":"text/event-stream"},stream=OfflineReply(),request=request)
httpx.AsyncClient.send=offline_send
screens=ROOT/"artifacts/screenshots";screens.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix="dreamtalk-mobile-browser-") as temp:
    host=importlib.reload(mobile_host)
    host._allowed_origins=("http://127.0.0.1:1430",)
    bridge=MemoryHost(Path(temp)/"data")
    connection=json.loads(host.dispatch("connection","{}",bridge))["result"]
    try:
        p=sync_playwright().start()
        browser=p.chromium.launch(executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",headless=True)
        page=browser.new_page(viewport={"width":390,"height":844},device_scale_factor=1)
        errors=[];page.on("pageerror",lambda e:errors.append(str(e)))
        page.add_init_script("window.__DREAMTALK_MOBILE_TEST_HOST__=async function(op){const conn="+json.dumps(connection)+";if(op==='connection')return conn;if(op==='model_status')return "+json.dumps(json.loads(bridge.value)["setup"])+";throw new Error('unsupported_test_host_operation');};")
        page.goto("http://127.0.0.1:1430")
        page.wait_for_load_state("networkidle")
        page.get_by_role("heading",name="我的世界").wait_for()
        page.screenshot(path=str(screens/"01-worlds.png"),full_page=True)
        page.get_by_label("新世界名称").fill("手机离线检查")
        page.get_by_role("button",name="创建世界",exact=True).click()
        page.get_by_role("button",name="手机离线检查 打开世界").click()
        page.get_by_role("button",name="从家开始",exact=True).wait_for()
        page.get_by_role("button",name="从家开始",exact=True).click()
        page.get_by_role("heading",name="会话",exact=True).wait_for()
        page.get_by_role("button",name="通讯录",exact=True).click()
        page.get_by_text("导入／管理角色卡与世界书",exact=True).click()
        card={"spec":"chara_card_v2","spec_version":"2.0","data":{"name":"林澄","description":"一位喜欢读书与散步的旅人。","personality":"温和、坦率，回答简洁。","scenario":"","first_mes":"你好，旅人。","mes_example":"","creator_notes":"","system_prompt":"","post_history_instructions":"","alternate_greetings":[],"tags":[],"creator":"","character_version":"","extensions":{}}}
        page.locator('input[type="file"]').first.set_input_files({"name":"synthetic-character.json","mimeType":"application/json","buffer":json.dumps(card,ensure_ascii=False).encode()})
        page.get_by_role("button",name="确认加入当前世界",exact=True).wait_for(timeout=15000)
        page.get_by_role("button",name="确认加入当前世界",exact=True).click()
        page.get_by_role("button",name="林 林澄 打开聊天").wait_for(timeout=15000)
        page.screenshot(path=str(screens/"02-contacts.png"),full_page=True)
        page.get_by_role("button",name="林 林澄 打开聊天").click()
        composer=page.get_by_role("textbox",name="发送给林澄的消息")
        composer.wait_for(timeout=15000)
        composer.fill("你好，可以介绍一下自己吗？")
        page.screenshot(path=str(screens/"03-composer.png"),full_page=True)
        page.get_by_role("button",name="发送",exact=True).click()
        page.get_by_text("“你好，很高兴认识你。”",exact=True).wait_for(timeout=20000)
        expect(composer).to_be_enabled(timeout=20000)
        expect(page.get_by_role("button",name="停止生成",exact=True)).to_have_count(0,timeout=20000)
        def read(path):
            with urlopen(Request(connection["endpoint"]+"/api/v1"+path,headers={"Authorization":"Bearer "+connection["token"]}),timeout=15) as response:return json.load(response)
        world_id=read("/worlds")[0]["world_id"]
        conversation_id=read("/worlds/"+world_id+"/conversations")[0]["conversation_id"]
        messages=read("/worlds/"+world_id+"/conversations/"+conversation_id+"/messages")
        assert any(message["sender_kind"]=="character" and message["text"]=="“你好，很高兴认识你。”" for message in messages), "Reply has not been durably saved"
        page.screenshot(path=str(screens/"04-chat.png"),full_page=True)
        overflow=page.evaluate("document.documentElement.scrollWidth>innerWidth")
        if overflow:raise AssertionError("Mobile layout horizontally overflows")
        checked=[]
        for width,height in [(320,640),(360,800),(390,844),(430,932),(390,440)]:
            page.set_viewport_size({"width":width,"height":height})
            expect(composer).to_be_visible()
            state=page.evaluate("""() => { const input=document.querySelector('textarea'); const r=input.getBoundingClientRect();return {overflow:document.documentElement.scrollWidth>innerWidth,bottom:r.bottom,top:r.top,height:innerHeight}; }""")
            assert not state["overflow"],(width,height,state)
            assert 0 <= state["top"] < state["bottom"] <= height+1,(width,height,state)
            checked.append(str(width)+"x"+str(height))
        page.set_viewport_size({"width":390,"height":844})
        page.screenshot(path=str(screens/"04-chat.png"),full_page=True)
        print("Responsive layouts checked: "+", ".join(checked),flush=True)
        if errors:raise AssertionError("Browser errors: "+repr(errors))
        print(json.dumps({"browser":"isolated Chrome","viewport":"390x844","world_create":True,"identity":True,"character_import":True,"chat_saved":True,"offline_provider_calls":len(outbound),"page_errors":errors,"horizontal_overflow":overflow},ensure_ascii=False),flush=True)
        browser.close()
    except Exception:
        try:
            page.screenshot(path=str(screens/"failure.png"),full_page=True)
            print(page.locator("body").inner_text()[-3500:],flush=True)
        except Exception:pass
        raise
    finally:
        try: browser.close();p.stop()
        finally: host._stop_if_idle()
