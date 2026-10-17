"""Compile a stable local EXE outside Cargo's shared test/debug outputs; never run it."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path

IDENTITY = "app.livingworld.desktop"


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def publish_entry(source: Path, directory: Path, version: str) -> dict:
    """Replace only our own previous receipt-matched executable, without touching saves."""
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / "dreamtalk-desktop.exe"
    receipt = directory / "entry.json"
    if directory.is_symlink() or destination.is_symlink() or receipt.is_symlink():
        raise ValueError("local_entry_path_invalid")
    if destination.exists():
        previous = json.loads(receipt.read_text("utf-8"))
        if previous.get("identity") != IDENTITY or previous.get("sha256") != digest(destination):
            raise ValueError("local_entry_modified")
    record = {"identity": IDENTITY, "version": version, "sha256": digest(source)}
    staged = directory / f"entry-{uuid.uuid4().hex}.tmp"
    staged_receipt = directory / f"receipt-{uuid.uuid4().hex}.tmp"
    try:
        shutil.copyfile(source, staged)
        if digest(staged) != record["sha256"]:
            raise ValueError("local_entry_copy_invalid")
        staged_receipt.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        os.replace(staged, destination)
        os.replace(staged_receipt, receipt)
    finally:
        staged.unlink(missing_ok=True)
        staged_receipt.unlink(missing_ok=True)
    return record


def main() -> None:
    if os.name != "nt":
        raise SystemExit("local_desktop_requires_windows")
    root = Path(__file__).resolve().parents[1]
    artifacts = root / "artifacts"
    target = artifacts / "local-desktop-build"
    output = artifacts / "local-desktop"
    for path in (artifacts, target, output):
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise SystemExit("local_desktop_path_invalid")
    npm = shutil.which("npm")
    if not npm:
        raise SystemExit("npm_not_found")
    # A separate Cargo target prevents a test/clippy build from replacing the
    # executable the user launches. The app's compiled project root is unchanged.
    subprocess.run(
        [
            npm,
            "exec",
            "--workspace",
            "@dreamtalk/desktop",
            "--",
            "tauri",
            "build",
            "--debug",
            "--no-bundle",
            "--features",
            "custom-protocol",
        ],
        cwd=root,
        env={**os.environ, "CARGO_TARGET_DIR": str(target)},
        check=True,
    )
    config = json.loads((root / "apps/desktop/src-tauri/tauri.conf.json").read_text("utf-8"))
    if config["identifier"] != IDENTITY:
        raise SystemExit("local_desktop_identity_changed")
    record = publish_entry(target / "debug/dreamtalk-desktop.exe", output, config["version"])
    print(json.dumps({**record, "entry": str(output / "dreamtalk-desktop.exe")}))


if __name__ == "__main__":
    main()
