"""Verify draft, publish the authorized Android prerelease, then verify public bytes."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
root=Path(__file__).resolve().parents[1]
out=root/"artifacts/github-android-personal-012"
tag="android-v0.1.2-personal.1"
repo="repos/zhangyeS12/dreamtalk"
env=dict(os.environ)
env["NO_PROXY"]="github.com,.github.com,api.github.com,uploads.github.com,objects.githubusercontent.com,release-assets.githubusercontent.com,raw.githubusercontent.com"
def api(path):
    return json.loads(subprocess.check_output(["gh","api",path],env=env))
def get_release():
    item=api(repo+"/releases/437491556")
    assert item["tag_name"]==tag
    return item
def verify(value):
    manifest=json.loads((out/"asset-manifest.json").read_text())
    assert value["prerelease"] and value["target_commitish"]==json.loads((out/"windows-before.json").read_text(encoding="utf-8"))["main"]
    assert value["body"].replace("\r\n","\n").strip()==(out/"release-notes.md").read_text(encoding="utf-8").strip()
    assert len(value["assets"])==len(manifest)==4
    for expected in manifest:
        asset=next(item for item in value["assets"] if item["name"]==expected["name"])
        assert asset["size"]==expected["bytes"]
        assert asset["digest"]=="sha256:"+expected["sha256"]
    return value
mode=sys.argv[1]
if mode=="publish":
    value=verify(get_release()); assert value["draft"]
    (out/"draft-verified.json").write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding="utf-8")
    subprocess.run(["gh","release","edit",tag,"--repo","zhangyeS12/dreamtalk","--draft=false","--prerelease","--latest=false"],env=env,check=True)
    value=verify(get_release()); assert not value["draft"] and value["published_at"]
    (out/"published-release.json").write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"release_id":value["id"],"url":value["html_url"],"prerelease":value["prerelease"],"assets":len(value["assets"])}))
elif mode=="download":
    value=verify(get_release()); assert not value["draft"]
    asset=next(item for item in value["assets"] if item["name"]=="dreamtalk-android-0.1.2-arm64.apk")
    target=out/"anonymous-download.apk"
    partial=out/"anonymous-download.part"
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request=urllib.request.Request(asset["browser_download_url"],headers={"User-Agent":"dreamtalk-release-verifier"})
    digest=hashlib.sha256(); size=0
    with opener.open(request,timeout=60) as response, partial.open("wb") as stream:
        status=response.status
        assert status==200
        while True:
            block=response.read(1024*1024)
            if not block: break
            stream.write(block); digest.update(block); size+=len(block)
    assert size==asset["size"] and "sha256:"+digest.hexdigest()==asset["digest"]
    partial.replace(target)
    result={"checked_at_jst":datetime.now(timezone(timedelta(hours=9))).isoformat(),"url":asset["browser_download_url"],"http_status":status,"authentication_sent":False,"bytes":size,"sha256":digest.hexdigest(),"matches_published_and_local_apk":True}
    (out/"anonymous-download-verification.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(result))
else:
    raise ValueError("unsupported_mode")
