"""Publish only verified Android assets, then independently verify anonymous downloads."""

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/github-android-personal-015"
TAG = "android-v0.1.5-personal.1"
REPOSITORY = "zhangyeS12/dreamtalk"
ENV = dict(os.environ)
ENV["GODEBUG"] = "http2client=0"
ENV["NO_PROXY"] = "github.com,.github.com,api.github.com,uploads.github.com,objects.githubusercontent.com,release-assets.githubusercontent.com,raw.githubusercontent.com"


def api(path):
    return json.loads(subprocess.check_output(["gh", "api", "repos/" + REPOSITORY + path], env=ENV))


def release():
    identity_file = OUT / "release-id.json"
    if not identity_file.exists():
        source = json.loads((OUT / "source-commit.json").read_text(encoding="utf-8"))
        candidates = [item for item in api("/releases?per_page=100") if item["tag_name"] == TAG]
        assert len(candidates) == 1 and candidates[0]["target_commitish"] == source["commit"]
        identity_file.write_text(json.dumps({"id": candidates[0]["id"], "target_commit": source["commit"]}), encoding="utf-8")
    identity = json.loads(identity_file.read_text(encoding="utf-8"))
    value = api("/releases/" + str(identity["id"]))
    assert value["tag_name"] == TAG and value["target_commitish"] == identity["target_commit"]
    return value


def verify(value):
    expected = json.loads((OUT / "asset-manifest.json").read_text(encoding="utf-8"))
    source = json.loads((OUT / "source-commit.json").read_text(encoding="utf-8"))
    assert value["tag_name"] == TAG and value["prerelease"]
    assert value["target_commitish"] == source["commit"]
    assert value["body"].replace("\r\n", "\n").strip() == (OUT / "release-notes.md").read_text(encoding="utf-8").strip()
    assert len(value["assets"]) == len(expected) == 4
    for item in expected:
        asset = next(asset for asset in value["assets"] if asset["name"] == item["name"])
        assert asset["size"] == item["bytes"] and asset["digest"] == "sha256:" + item["sha256"]
    return value


def main(mode):
    if mode == "create":
        source = json.loads((OUT / "source-commit.json").read_text(encoding="utf-8"))
        subprocess.run(["gh", "release", "create", TAG, "--repo", REPOSITORY,
                        "--target", source["commit"], "--draft", "--prerelease", "--latest=false",
                        "--title", "dreamtalk Android 0.1.5 personal test",
                        "--notes-file", str(OUT / "release-notes.md")], env=ENV, check=True)
        value = release()
        assert value["draft"] and not value["assets"]
        (OUT / "draft-created.json").write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"draft_id": value["id"], "tag": TAG}), flush=True)
    elif mode == "upload":
        value = release()
        assert value["draft"]
        expected = json.loads((OUT / "asset-manifest.json").read_text(encoding="utf-8"))
        for item in expected:
            existing = next((asset for asset in value["assets"] if asset["name"] == item["name"]), None)
            if existing:
                assert existing["size"] == item["bytes"] and existing["digest"] == "sha256:" + item["sha256"]
                continue
            subprocess.run(["gh", "release", "upload", TAG, str(OUT / "upload" / item["name"]),
                            "--repo", REPOSITORY], env=ENV, check=True)
            print("Uploaded " + item["name"], flush=True)
            value = release()
        value = verify(value)
        (OUT / "draft-verified.json").write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    elif mode == "publish":
        value = verify(release())
        assert value["draft"]
        subprocess.run(["gh", "release", "edit", TAG, "--repo", REPOSITORY,
                        "--draft=false", "--prerelease", "--latest=false"], env=ENV, check=True)
        value = verify(release())
        assert not value["draft"] and value["published_at"]
        (OUT / "published-release.json").write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"release_id": value["id"], "url": value["html_url"], "assets": len(value["assets"])}), flush=True)
    elif mode == "download":
        value = verify(release())
        assert not value["draft"]
        folder = OUT / "anonymous"
        folder.mkdir(exist_ok=True)
        checks = []
        for asset in value["assets"]:
            destination = folder / asset["name"]
            subprocess.run(["curl.exe", "--http1.1", "--noproxy", "*", "--fail", "--location",
                            "--silent", "--show-error", "--connect-timeout", "20", "--max-time", "300",
                            "--output", str(destination), asset["browser_download_url"]], check=True)
            data = destination.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            assert len(data) == asset["size"] and "sha256:" + digest == asset["digest"]
            checks.append({"name": asset["name"], "bytes": len(data), "sha256": digest,
                           "url": asset["browser_download_url"], "authentication_sent": False,
                           "complete_download_verified": True})
            print("Anonymous download verified: " + asset["name"], flush=True)
        result = {"checked_at": datetime.now(timezone.utc).isoformat(), "assets": checks,
                  "all_published_assets_match": True}
        (OUT / "anonymous-download-verification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    else:
        raise ValueError("unknown_release_action")


if __name__ == "__main__":
    main(sys.argv[1])
