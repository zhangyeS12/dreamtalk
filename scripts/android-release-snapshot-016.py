"""Capture Windows isolation evidence; read-only network and local Git access."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone, timedelta

root = Path(__file__).resolve().parents[1]
out = root / "artifacts/github-android-personal-016"
out.mkdir(exist_ok=True)
phase = sys.argv[1]
assert phase in {"before", "after"}
env = dict(os.environ)
env["GODEBUG"] = "http2client=0"
env["NO_PROXY"] = ",".join(filter(None, [env.get("NO_PROXY", ""), "github.com,.github.com,api.github.com,uploads.github.com,objects.githubusercontent.com,release-assets.githubusercontent.com,raw.githubusercontent.com"]))
def api(path, optional=False):
    reply = subprocess.run(["gh", "api", path], env=env, capture_output=True)
    if reply.returncode:
        if optional and b"HTTP 404" in reply.stderr: return None
        raise RuntimeError("github_read_failed:" + path)
    return json.loads(reply.stdout)
def compact(value):
    if value is None: return None
    return {k: value.get(k) for k in ("id", "tag_name", "target_commitish", "name", "draft", "prerelease", "html_url", "body")} | {"assets": [{k: item.get(k) for k in ("id", "name", "size", "digest", "browser_download_url")} for item in value["assets"]]}
def git(*args):
    return subprocess.run(["git", "-C", "D:/LivingWorld", *args], capture_output=True, check=True).stdout
repo = "repos/zhangyeS12/dreamtalk"
info = api(repo)
main = api(repo + "/git/ref/heads/main")["object"]["sha"]
windows = compact(api(repo + "/releases/tags/v0.2.1"))
channel = compact(api(repo + "/releases/tags/update-preview"))
latest = compact(api(repo + "/releases/latest", optional=True))
asset = next(item for item in channel["assets"] if item["name"] == "windows.json")
channel_path = out / ("windows-channel-" + phase + ".json")
subprocess.run(["curl.exe", "--disable", "--http1.1", "--noproxy", "*", "--fail", "--location", "--silent", "--show-error", "--connect-timeout", "20", "--max-time", "90", "--output", str(channel_path), asset["browser_download_url"]], check=True)
data = channel_path.read_bytes()
state = {"captured_at_jst": datetime.now(timezone(timedelta(hours=9))).isoformat(), "repository": info["full_name"], "private": info["private"], "main": main, "windows": windows, "channel": channel, "channel_sha256": hashlib.sha256(data).hexdigest(), "latest": latest, "local": {"head": git("rev-parse", "HEAD").decode().strip(), "status_sha256": hashlib.sha256(git("status", "--porcelain=v1", "-uall")).hexdigest(), "tracked_diff_sha256": hashlib.sha256(git("diff", "--binary", "HEAD")).hexdigest()}}
(out / ("windows-" + phase + ".json")).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
if phase == "after":
    before = json.loads((out / "windows-before.json").read_text(encoding="utf-8"))
    checks = {key: state[key] == before[key] for key in ("main", "windows", "channel", "channel_sha256", "latest", "local")}
    (out / "isolation-verification.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
    assert all(checks.values()), checks
    print(json.dumps({"isolation": checks}))
else:
    print(json.dumps({"main": main, "windows_release": windows["id"], "latest": latest["tag_name"] if latest else None, "channel_sha256": state["channel_sha256"], "local_head": state["local"]["head"]}))
