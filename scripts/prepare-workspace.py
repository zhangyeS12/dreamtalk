from pathlib import Path
import concurrent.futures, hashlib, json, os, re, shutil, subprocess, sys, time, urllib.request, zipfile
import xml.etree.ElementTree as ET
ROOT=Path(r"D:\dreamtalk安卓版")
SRC=Path(r"D:\LivingWorld")
ROOT.mkdir(exist_ok=True)
for name in ("scripts","artifacts","build-tools","docs"):
    (ROOT/name).mkdir(exist_ok=True)
def log(*args): print(*args,flush=True)
def snapshot():
    manifest_path=ROOT/"docs/source-snapshot.json"
    if manifest_path.exists():
        log("Source snapshot already exists; retaining it")
        return
    names=subprocess.check_output(["git","ls-files","--cached","--others","--exclude-standard"],cwd=SRC).decode().splitlines()
    prefixes=("services/core/src/livingworld/","packages/api-client/","apps/web/","tools/deepseek-request-bound/","tests/","docs/licenses/")
    roots={"LICENSE","NOTICE","pyproject.toml","uv.lock","package.json","package-lock.json","tsconfig.json","eslint.config.js","vitest.config.ts","pyrightconfig.json"}
    entries=[]
    for name in names:
        if not (name.startswith(prefixes) or name in roots): continue
        source=SRC/name
        if not source.is_file(): continue
        data=source.read_bytes()
        target=ROOT/name
        if target.exists(): raise RuntimeError("Snapshot target already exists: "+name)
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(data)
        digest=hashlib.sha256(data).hexdigest()
        if hashlib.sha256(source.read_bytes()).hexdigest()!=digest: raise RuntimeError("Upstream changed during snapshot: "+name)
        entries.append({"path":name,"sha256":digest,"bytes":len(data)})
    record={"upstream":str(SRC),"head":subprocess.check_output(["git","rev-parse","HEAD"],cwd=SRC).decode().strip(),"captured_at_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"includes_worktree_changes":True,"files":entries}
    manifest_path.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding="utf-8")
    log("Captured source files",len(entries))
def fetch(url,path,expected=None,algorithm="sha256"):
    path=Path(path)
    if path.exists() and (not expected or hashlib.new(algorithm,path.read_bytes()).hexdigest()==expected): return
    partial=path.with_suffix(path.suffix+".part")
    req=urllib.request.Request(url,headers={"User-Agent":"dreamtalk-android-build/0.1"})
    with urllib.request.urlopen(req,timeout=90) as response,partial.open("wb") as out:
        length=int(response.headers.get("Content-Length","0")); count=0; reported=-1
        while True:
            chunk=response.read(1024*1024)
            if not chunk: break
            out.write(chunk);count+=len(chunk)
            progress=int(count*10/length) if length else count//(64*1024*1024)
            if progress!=reported: log(path.name,count//1048576,"MiB",f"/ {length//1048576}" if length else "");reported=progress
    if expected and hashlib.new(algorithm,partial.read_bytes()).hexdigest()!=expected: raise RuntimeError("Download checksum mismatch "+path.name)
    partial.replace(path)
def extract(archive,destination):
    destination=Path(destination)
    destination.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        for item in bundle.infolist():
            target=(destination/item.filename).resolve()
            if not target.is_relative_to(destination.resolve()): raise RuntimeError("Archive path outside tools")
        bundle.extractall(destination)
def sdk_packages():
    repo=ROOT/"build-tools/repository2-1.xml"
    fetch("https://dl.google.com/android/repository/repository2-1.xml",repo)
    tree=ET.parse(repo)
    want={"cmdline-tools;latest","platforms;android-36","build-tools;36.0.0","ndk;27.2.12479018"}
    found=[]
    def local(tag): return tag.split("}")[-1]
    def txt(element,name):
        for el in element.iter():
            if local(el.tag)==name: return el.text
    for pkg in tree.getroot():
        if local(pkg.tag)!="remotePackage" or pkg.attrib.get("path") not in want: continue
        for arch in pkg.iter():
            if local(arch.tag)!="archive": continue
            host=txt(arch,"host-os")
            if host not in (None,"windows"): continue
            complete=next((el for el in arch if local(el.tag)=="complete"),None)
            if complete is None: continue
            found.append((pkg.attrib["path"],txt(complete,"url"),txt(complete,"checksum")));break
    chosen={}
    for item in found:
        package,url,_=item
        if package=="platforms;android-36" and not re.fullmatch(r"platform-36_r\d+\.zip",url): continue
        chosen[package]=item
    found=list(chosen.values())
    if {x[0] for x in found}!=want: raise RuntimeError("SDK package metadata missing: "+str(want-{x[0] for x in found}))
    sdk=ROOT/"build-tools/android-sdk"
    def install(entry):
        package,url,sha1=entry
        target=sdk.joinpath(*package.split(";"))
        if (target/".dreamtalk-installed").exists(): log("SDK already installed",package);return
        archive=ROOT/"build-tools"/Path(url).name
        fetch("https://dl.google.com/android/repository/"+url,archive,sha1,"sha1")
        stage=ROOT/"build-tools"/("unpack-"+package.replace(";","-"))
        extract(archive,stage)
        children=list(stage.iterdir())
        content=children[0] if len(children)==1 and children[0].is_dir() else stage
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists(): raise RuntimeError("SDK destination exists without completion: "+str(target))
        shutil.move(str(content),str(target))
        (target/".dreamtalk-installed").write_text(url,encoding="utf-8")
        log("Installed SDK package",package)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for _ in pool.map(install,found): pass
def jdk():
    tool=ROOT/"build-tools/jdk21"
    if list(tool.glob("*/bin/java.exe")): log("JDK already installed");return
    archive=ROOT/"build-tools/microsoft-jdk-21-windows-x64.zip"
    fetch("https://aka.ms/download-jdk/microsoft-jdk-21-windows-x64.zip",archive)
    extract(archive,tool)
    log("Installed workspace JDK21")
def inspect_wheels():
    for name in ("numpy","pillow","greenlet"):
        url="https://chaquo.com/pypi-13.1/"+name+"/"
        try:
            with urllib.request.urlopen(url,timeout=30) as response: body=response.read().decode()
            (ROOT/"build-tools"/(name+"-index.html")).write_text(body,encoding="utf-8")
            links=re.findall(r'href="([^"]+)"',body)
            arm=[x for x in links if "cp313" in x and ("arm64_v8a" in x or "aarch64" in x)]
            log("Python native package",name,"cp313-arm64 candidates",len(arm),arm[-1:] if arm else "")
        except Exception as error:log("Python package index",name,type(error).__name__,str(error)[:80])
snapshot()
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    futures=[pool.submit(sdk_packages),pool.submit(jdk),pool.submit(inspect_wheels)]
    for task in concurrent.futures.as_completed(futures):
        try:task.result()
        except Exception as error:log("BUILD TOOL SETUP ERROR",type(error).__name__,str(error));raise
log("SOURCE_AND_TOOL_SETUP_COMPLETE")
