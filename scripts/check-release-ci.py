"""Require clean committed release source; CI verification is explicitly opt-in."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "zhangyeS12/dreamtalk"


def validate_runs(payload: dict, commit: str) -> str:
    runs = [
        run
        for run in payload.get("workflow_runs", [])
        if run.get("head_sha") == commit
        # PR checks normally build a synthetic merge ref, not the release tree.
        and run.get("event") in {"push", "workflow_dispatch"}
        and run.get("path") == ".github/workflows/foundation.yml"
    ]
    if not runs:
        raise ValueError("release_ci_run_missing")
    # A failed/running latest attempt cannot be hidden by an older green result.
    latest = max(runs, key=lambda run: (run["run_number"], run.get("run_attempt", 1)))
    if latest.get("status") != "completed" or latest.get("conclusion") != "success":
        raise ValueError("release_ci_not_successful")
    return latest["html_url"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-ci",
        action="store_true",
        help="Verify CI only when the user explicitly requested it",
    )
    args = parser.parse_args()
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise SystemExit("release_ci_commit_invalid")
    dirty = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=normal"], cwd=ROOT, text=True
    )
    if dirty.strip():
        raise SystemExit("release_ci_requires_committed_clean_source")
    if not args.require_ci:
        print(f"Release source: CLEAN {commit}; CI NOT RUN (manual opt-in)")
        return
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "dreamtalk-release-check"}
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    query = urllib.parse.urlencode({"head_sha": commit, "per_page": 100})
    url = f"https://api.github.com/repos/{REPOSITORY}/actions/workflows/foundation.yml/runs?{query}"
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers=headers), timeout=30
        ) as response:
            payload = json.load(response)
        verified = validate_runs(payload, commit)
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError):
        raise SystemExit(
            "release_ci_verification_failed: require a successful exact-commit CI run"
        ) from None
    print(f"Release source CI: PASS {commit} {verified}")


if __name__ == "__main__":
    main()
