"""Require clean matching source and a successful exact-commit Android CI before APK packaging."""

import hashlib
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    version = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["version"]
    output = ROOT / "artifacts" / ("github-android-personal-" + version.replace(".", ""))
    receipt = json.loads((output / "source-commit.json").read_text(encoding="utf-8"))
    assert receipt["version"] == version
    source = ROOT / receipt["source_directory"]
    assert source.resolve().is_relative_to((ROOT / "artifacts").resolve())
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    assert commit == receipt["commit"]
    assert not subprocess.check_output(["git", "status", "--porcelain", "-uall"], cwd=source)
    for item in receipt["files"]:
        assert hashlib.sha256((ROOT / item["source"]).read_bytes()).hexdigest() == item["sha256"]
        assert hashlib.sha256((source / item["path"]).read_bytes()).hexdigest() == item["sha256"]
    environment = dict(os.environ)
    environment["GODEBUG"] = "http2client=0"
    environment["NO_PROXY"] = "api.github.com,github.com,.github.com"
    repository = "repos/zhangyeS12/dreamtalk"

    def api(path):
        return json.loads(subprocess.check_output(["gh", "api", path], env=environment))

    runs = api(repository + "/actions/runs?head_sha=" + commit + "&per_page=100")
    candidates = [
        run
        for run in runs["workflow_runs"]
        if run["head_sha"] == commit and run["path"] == ".github/workflows/android-personal.yml"
    ]
    assert candidates, "android_exact_commit_ci_missing"
    run = max(candidates, key=lambda item: item["id"])
    assert run["status"] == "completed" and run["conclusion"] == "success", (
        "android_exact_commit_ci_not_successful"
    )
    jobs = api(repository + f"/actions/runs/{run['id']}/jobs")["jobs"]
    assert jobs and all(job["conclusion"] == "success" for job in jobs)
    assert any(job["name"] == "Android CI Gate" for job in jobs)
    result = {
        "commit": commit,
        "run_id": run["id"],
        "url": run["html_url"],
        "conclusion": "success",
        "source_files": len(receipt["files"]),
        "source_matches_commit": True,
        "skip_ci_used": False,
    }
    (output / "ci-verification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("Android release source CI: PASS " + commit + " " + run["html_url"])


if __name__ == "__main__":
    main()
