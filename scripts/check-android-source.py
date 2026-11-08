"""Portable Android source CI; no APK or live provider execution."""

import argparse
import importlib.util
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", choices=["all", "core", "web", "static"], default="all")
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location(
        "android_checks", ROOT / "scripts/check-windows-sync.py"
    )
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    runner.PYTHON = runner.TOOLS_PYTHON = Path(sys.executable)
    runner.WORK = ROOT / "artifacts/android-ci"
    runner.WORK.mkdir(parents=True, exist_ok=True)
    targets = json.loads((ROOT / "ci/python-targets.json").read_text(encoding="utf-8"))
    (runner.WORK / "source-state.json").write_text(
        json.dumps({"transfers": [{"path": name} for name in targets]}), encoding="utf-8"
    )
    groups = ["core", "web", "static"] if args.group == "all" else [args.group]
    with ThreadPoolExecutor(max_workers=len(groups)) as pool:
        passed = list(pool.map(runner.check, groups))
    for name, successful in zip(groups, passed, strict=True):
        if not successful:
            print("FAILED CHECK DETAILS: " + name, flush=True)
            log = runner.WORK / (name + "-checks.log")
            print(log.read_text(encoding="utf-8", errors="replace")[-50000:], flush=True)
    return 0 if all(passed) else 1


if __name__ == "__main__":
    sys.exit(main())
