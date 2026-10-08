"""Build signed full Windows NSIS payload and update manifest; never run or publish it."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-only", action="store_true", required=True)
    parser.add_argument("--output-name", required=True)
    parser.add_argument(
        "--reuse-portable", action="store_true", help="Use matching already built named payload"
    )
    args = parser.parse_args()
    import re

    if os.name != "nt" or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", args.output_name):
        raise SystemExit("installer_build_parameters_invalid")
    root = Path(__file__).resolve().parents[1]
    artifacts = root / "artifacts"
    output = artifacts / "installers" / args.output_name
    if artifacts.is_symlink() or not artifacts.resolve().is_relative_to(root) or output.exists():
        raise SystemExit("installer_output_must_be_new_and_inside_artifacts")
    if not os.environ.get("TAURI_SIGNING_PRIVATE_KEY"):
        raise SystemExit("publisher_signing_key_required")
    if not args.reuse_portable:
        subprocess.run(
            [
                sys.executable,
                str(root / "scripts/build-portable.py"),
                "--build-only",
                "--output-name",
                args.output_name,
            ],
            check=True,
            cwd=root,
        )
    package = artifacts / "portable" / args.output_name / "dreamtalk"
    config = json.loads(
        (root / "apps/desktop/src-tauri/tauri.conf.json").read_text(encoding="utf-8")
    )
    version = config["version"]
    marker = json.loads((package / ".dreamtalk-package.json").read_text(encoding="utf-8"))
    if marker["identity"] != config["identifier"] or marker["version"] != version:
        raise SystemExit("installer_portable_version_mismatch")
    output.mkdir(parents=True)
    stage = output / "payload"
    shutil.copytree(package, stage)
    (stage / "dreamtalk-desktop.exe").unlink()  # Tauri supplies the main binary.
    (stage / ".dreamtalk-installed").write_text(config["identifier"] + "\n", encoding="utf-8")
    tauri_root = root / "apps/desktop/src-tauri"
    resources = {
        str(p.resolve()): p.relative_to(stage).as_posix()
        for p in sorted(stage.rglob("*"))
        if p.is_file()
    }
    bundle_config = {
        "bundle": {
            "active": True,
            "targets": ["nsis"],
            "createUpdaterArtifacts": True,
            "resources": resources,
            "publisher": "dreamtalk",
            "licenseFile": str(root / "LICENSE"),
            "homepage": "https://github.com/zhangyeS12/dreamtalk",
            "windows": {
                "allowDowngrades": False,
                "nsis": {
                    "installMode": "currentUser",
                    "languages": ["SimpChinese", "English"],
                    "installerHooks": str(tauri_root / "installer-hooks.nsh"),
                },
            },
        },
    }
    configuration = output / "tauri.installer.json"
    configuration.write_text(
        json.dumps(bundle_config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    npm = shutil.which("npm")
    if not npm:
        raise SystemExit("npm_not_found")
    command = [npm, "exec", "--workspace", "@dreamtalk/desktop", "--", "tauri"]
    subprocess.run(
        command
        + ["build", "--no-bundle", "--features", "custom-protocol", "--config", str(configuration)],
        check=True,
        cwd=root,
    )
    binary = tauri_root / "target/release/dreamtalk-desktop.exe"
    marker["files"]["dreamtalk-desktop.exe"] = file_hash(binary)
    marker["files"][".dreamtalk-installed"] = file_hash(stage / ".dreamtalk-installed")
    (stage / ".dreamtalk-package.json").write_text(
        json.dumps(marker, indent=2) + "\n", encoding="utf-8"
    )
    subprocess.run(
        command
        + [
            "bundle",
            "--features",
            "custom-protocol",
            "--bundles",
            "nsis",
            "--config",
            str(configuration),
            "--ci",
        ],
        check=True,
        cwd=root,
    )
    # The bundler may patch PE bundle-type metadata. If that changes the main
    # binary, regenerate the payload marker and bundle once more before delivery.
    patched_hash = file_hash(binary)
    if patched_hash != marker["files"]["dreamtalk-desktop.exe"]:
        marker["files"]["dreamtalk-desktop.exe"] = patched_hash
        (stage / ".dreamtalk-package.json").write_text(
            json.dumps(marker, indent=2) + "\n", encoding="utf-8"
        )
        subprocess.run(
            command
            + [
                "bundle",
                "--features",
                "custom-protocol",
                "--bundles",
                "nsis",
                "--config",
                str(configuration),
                "--ci",
            ],
            check=True,
            cwd=root,
        )
        if file_hash(binary) != patched_hash:
            raise SystemExit("installer_binary_hash_not_stable")
    source = tauri_root / "target/release/bundle/nsis" / f"dreamtalk_{version}_x64-setup.exe"
    if not source.is_file() or not source.with_suffix(".exe.sig").is_file():
        raise SystemExit("signed_installer_missing")
    installer = output / source.name
    shutil.copy2(source, installer)
    shutil.copy2(source.with_suffix(".exe.sig"), installer.with_suffix(".exe.sig"))
    notes = (root / "docs/releases" / f"v{version}.md").read_text(encoding="utf-8")
    manifest = {
        "version": version,
        "notes": notes,
        "pub_date": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "platforms": {
            "windows-x86_64": {
                "signature": installer.with_suffix(".exe.sig").read_text(encoding="utf-8").strip(),
                "url": f"https://github.com/zhangyeS12/dreamtalk/releases/download/v{version}/{quote(installer.name)}",
            }
        },
    }
    (output / "windows.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    shutil.copy2(root / "docs/releases" / f"v{version}.md", output / "RELEASE_NOTES.md")
    checksums = [
        f"{file_hash(path)}  {path.name}"
        for path in (
            installer,
            installer.with_suffix(".exe.sig"),
            output / "windows.json",
            output / "RELEASE_NOTES.md",
        )
    ]
    (output / "SHA256SUMS.txt").write_text("\n".join(checksums) + "\n", encoding="utf-8")
    print(f"signed_installer={installer}")
    print(f"update_manifest={output / 'windows.json'}")


if __name__ == "__main__":
    main()
