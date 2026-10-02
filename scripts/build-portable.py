"""Build a relocatable Windows desktop folder with its own Python Core."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--build-only", action="store_true", help="Build the package without lifecycle smoke checks"
    )
    parser.add_argument(
        "--output-name", help="Build into a new named folder; preserve prior packages"
    )
    args = parser.parse_args()
    if args.output_name and not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", args.output_name):
        raise SystemExit("portable_output_name_invalid")
    if os.name != "nt":
        raise SystemExit("portable_build_requires_windows")
    root = Path(__file__).resolve().parents[1]
    artifacts = root / "artifacts"
    if artifacts.is_symlink() or not artifacts.resolve().is_relative_to(root.resolve()):
        raise SystemExit("artifacts_directory_invalid")
    package_parent = artifacts / "portable"
    if args.output_name:
        package_parent /= args.output_name
    package = package_parent / "dreamtalk"
    if package.is_symlink() or not package.resolve().is_relative_to(artifacts.resolve()):
        raise SystemExit("portable_output_directory_invalid")
    if args.output_name and (package.exists() or (package_parent / "dreamtalk.zip").exists()):
        raise SystemExit("named_portable_output_must_be_new")
    cargo = shutil.which("cargo")
    if cargo is None:
        raise SystemExit("cargo_not_found")
    subprocess.run(
        [
            cargo,
            "build",
            "--locked",
            "--release",
            "--manifest-path",
            str(root / "tools" / "deepseek-request-bound" / "Cargo.toml"),
        ],
        check=True,
        cwd=root,
    )
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--distpath",
            str(artifacts / "standalone"),
            "--workpath",
            str(artifacts / "pyinstaller-build"),
            str(root / "scripts" / "dreamtalk-core.spec"),
        ],
        check=True,
        cwd=root,
    )
    core = artifacts / "standalone" / "dreamtalk-core"
    core_binary = core / "dreamtalk-core.exe"
    if not core_binary.is_file():
        raise SystemExit("standalone_core_output_missing")
    if not args.build_only:
        subprocess.run(
            [sys.executable, str(root / "scripts" / "standalone-core-smoke.py"), str(core_binary)],
            check=True,
            cwd=root,
        )
    npm = shutil.which("npm")
    if npm is None:
        raise SystemExit("npm_not_found")
    subprocess.run([npm, "run", "build:desktop:release"], check=True, cwd=root)
    desktop = (
        root / "apps" / "desktop" / "src-tauri" / "target" / "release" / "dreamtalk-desktop.exe"
    )
    if not desktop.is_file():
        raise SystemExit("portable_build_output_missing")
    if package.is_symlink() or not package.resolve().is_relative_to(artifacts.resolve()):
        raise SystemExit("portable_output_directory_invalid")
    if package.exists():
        shutil.rmtree(package)
    package.mkdir(parents=True)
    shutil.copytree(core, package / "core")
    shutil.copy2(desktop, package / "dreamtalk-desktop.exe")
    shutil.copy2(root / "LICENSE", package / "LICENSE")
    shutil.copy2(root / "docs" / "licenses" / "jieba-0.42.1.txt", package / "JIEBA_LICENSE.txt")
    shutil.copytree(root / "docs" / "licenses", package / "third-party-licenses")
    shutil.copy2(root / "docs" / "PORTABLE_WINDOWS.md", package / "README.md")
    if not args.build_only:
        environment = os.environ.copy()
        environment["DREAMTALK_PACKAGED_CORE_ROOT"] = str(package)
        cargo = shutil.which("cargo")
        if cargo is None:
            raise SystemExit("cargo_not_found")
        subprocess.run(
            [
                cargo,
                "test",
                "--locked",
                "--manifest-path",
                str(root / "apps" / "desktop" / "src-tauri" / "Cargo.toml"),
                "--test",
                "supervisor",
                "windows_packaged_core_lifecycle",
                "--",
                "--exact",
            ],
            check=True,
            cwd=root,
            env=environment,
        )
    archive = package.with_suffix(".zip")
    # Reproducible dependency wheels can carry dates before ZIP's 1980 epoch.
    with zipfile.ZipFile(
        archive, "w", compression=zipfile.ZIP_DEFLATED, strict_timestamps=False
    ) as bundle:
        for source in sorted(package.rglob("*")):
            if source.is_file():
                bundle.write(source, source.relative_to(package.parent).as_posix())
    print(f"portable_package={package}")
    print(f"portable_archive={archive}")


if __name__ == "__main__":
    main()
