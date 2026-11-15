"""Private Android acceptance launcher; never targets physical devices or publishes."""

from __future__ import annotations

import argparse
import contextlib
import ctypes
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/android-local"
NAME = "DreamtalkLocalAcceptance001"
SERIAL = "emulator-5580"
ADB_PORT = "5049"
# Compatibility path for the local emulator only; Android APK rendering is unchanged.
GRAPHICS_MODE = "host"
PACKAGE = "app.livingworld.desktop"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class LocalError(RuntimeError):
    pass


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def source_fingerprint() -> dict:
    folders = [
        "services/core/src",
        "apps/web/src",
        "apps/web/public",
        "packages/api-client/src",
        "plugins/android/src",
        "apps/mobile/src-tauri/src",
        "apps/mobile/src-tauri/icons",
    ]
    files = set()
    for folder in folders:
        for path in (ROOT / folder).rglob("*"):
            if (
                path.is_file()
                and "__pycache__" not in path.parts
                and path.suffix not in {".pyc", ".pyo"}
                and ".test." not in path.name
            ):
                files.add(path)
    explicit = [
        "package.json",
        "package-lock.json",
        "tsconfig.json",
        "apps/web/index.html",
        "apps/web/vite.config.ts",
        "apps/web/package.json",
        "apps/mobile/package.json",
        "apps/mobile/src-tauri/Cargo.toml",
        "apps/mobile/src-tauri/Cargo.lock",
        "apps/mobile/src-tauri/build.rs",
        "apps/mobile/src-tauri/tauri.conf.json",
        "plugins/android/build.gradle.kts",
        "plugins/Cargo.toml",
        "plugins/build.rs",
        "apps/mobile/src-tauri/gen/android/app/src/main/AndroidManifest.xml",
        "apps/mobile/src-tauri/gen/android/build.gradle.kts",
        "apps/mobile/src-tauri/gen/android/gradle.properties",
        "apps/mobile/src-tauri/gen/android/app/build.gradle.kts",
    ]
    for name in explicit:
        if (ROOT / name).is_file():
            files.add(ROOT / name)
    for folder in [
        "apps/mobile/src-tauri/capabilities",
        "plugins/src",
        "apps/mobile/src-tauri/gen/android/app/src/main/res",
        "apps/mobile/src-tauri/gen/android/app/src/main/java",
        "plugins/permissions",
        "apps/mobile/src-tauri/gen/android/buildSrc/src",
    ]:
        for path in (ROOT / folder).rglob("*"):
            if path.is_file():
                files.add(path)
    manifest = []
    checksum = hashlib.sha256()
    for path in sorted(files):
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT):
            raise LocalError("local_source_path_invalid")
        name = path.relative_to(ROOT).as_posix()
        value = digest(path)
        checksum.update((name + "\0" + value + "\n").encode())
        manifest.append({"path": name, "sha256": value})
    return {"fingerprint": checksum.hexdigest(), "files": manifest}


def record_build(apk: Path) -> None:
    apk = apk.resolve()
    if apk.parent != OUT.resolve():
        raise LocalError("local_apk_path_invalid")
    before = json.loads((OUT / "source-before.json").read_text(encoding="utf-8"))
    current = source_fingerprint()
    if before != current:
        raise LocalError("local_source_changed_during_build")
    config = json.loads(
        (ROOT / "apps/mobile/src-tauri/tauri.conf.json").read_text(encoding="utf-8")
    )
    write_json(
        OUT / "pending-build.json",
        {
            "apk": "artifacts/android-local/dreamtalk-android-local.apk",
            "sha256": digest(apk),
            "bytes": apk.stat().st_size,
            "version": config["version"],
            "package": config["identifier"],
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "source": current,
            "local_only": True,
            "ci_run": False,
            "published": False,
            "real_api_used": False,
            "builder_sha256": digest(ROOT / "scripts/build-android-local.ps1"),
        },
    )


def finalize_build() -> None:
    value = json.loads((OUT / "pending-build.json").read_text(encoding="utf-8"))
    apk = ROOT / value["apk"]
    if (
        not value["local_only"]
        or apk.resolve().parent != OUT.resolve()
        or digest(apk) != value["sha256"]
    ):
        raise LocalError("local_apk_receipt_mismatch")
    write_json(OUT / "build-receipt.json", value)


def current_build() -> dict | None:
    path = OUT / "build-receipt.json"
    if not path.is_file():
        return None
    receipt = json.loads(path.read_text(encoding="utf-8"))
    apk = ROOT / receipt["apk"]
    if (
        not receipt.get("local_only")
        or apk.resolve().parent != OUT.resolve()
        or not apk.is_file()
        or digest(apk) != receipt["sha256"]
    ):
        raise LocalError("local_apk_receipt_mismatch")
    receipt["source_current"] = receipt["source"] == source_fingerprint()
    return receipt


def context() -> tuple[Path, Path, dict]:
    alias = Path("D:/dreamtalk/android-build-link")
    if alias.resolve() != ROOT:
        raise LocalError("local_sdk_alias_invalid")
    sdk = alias / "build-tools/android-sdk"
    home = alias / "build-tools/local-acceptance"
    home.mkdir(parents=True, exist_ok=True)
    marker = home / "owner.json"
    expected = {
        "source": str(ROOT),
        "purpose": "local-android-acceptance",
        "avd": NAME,
        "serial": SERIAL,
        "adb_port": ADB_PORT,
    }
    if marker.exists() and json.loads(marker.read_text(encoding="utf-8")) != expected:
        raise LocalError("local_profile_owner_mismatch")
    write_json(marker, expected)
    env = os.environ.copy()
    env.update(
        {
            "ANDROID_HOME": str(sdk),
            "ANDROID_SDK_ROOT": str(sdk),
            "ANDROID_USER_HOME": str(home / "user"),
            "ANDROID_EMULATOR_HOME": str(home / "emulator"),
            "ANDROID_AVD_HOME": str(home / "avd"),
            "ANDROID_ADB_SERVER_PORT": ADB_PORT,
            "ADB_VENDOR_KEYS": str(home / "user/adbkey"),
            "ANDROID_SDK_HOME": str(home / "user"),
        }
    )
    for part in ["user", "emulator", "avd"]:
        (home / part).mkdir(exist_ok=True)
    return sdk, home, env


def adb(sdk: Path, env: dict, *args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(sdk / "platform-tools/adb.exe"), "-P", ADB_PORT, "-s", SERIAL, *args],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=NO_WINDOW,
    )


def verify_device(sdk: Path, env: dict) -> None:
    qemu = adb(sdk, env, "shell", "getprop", "ro.kernel.qemu")
    name = adb(sdk, env, "emu", "avd", "name")
    if qemu.stdout.strip() != "1" or NAME not in name.stdout.splitlines():
        raise LocalError("local_device_identity_mismatch")


def emulator_command(sdk: Path) -> list[str]:
    return [
        str(sdk / "emulator/emulator.exe"),
        "-avd",
        NAME,
        "-port",
        SERIAL.removeprefix("emulator-"),
        "-no-boot-anim",
        "-no-snapshot",
        "-gpu",
        GRAPHICS_MODE,
        "-feature",
        "-Vulkan",
        "-camera-back",
        "none",
        "-camera-front",
        "none",
    ]


def start_device() -> tuple[Path, dict]:
    sdk, home, env = context()
    result = subprocess.run(
        [
            str(sdk / "platform-tools/adb.exe"),
            "-P",
            ADB_PORT,
            "--one-device",
            SERIAL,
            "start-server",
        ],
        env=env,
        capture_output=True,
        timeout=30,
        creationflags=NO_WINDOW,
    )
    if result.returncode:
        raise LocalError("local_adb_start_failed")
    process = None
    state = adb(sdk, env, "get-state", timeout=10).stdout.strip()
    if state not in {"device", "offline"}:
        profile = home / "avd" / (NAME + ".avd")
        profile.mkdir(exist_ok=True)
        (home / "avd" / (NAME + ".ini")).write_text(
            "avd.ini.encoding=UTF-8\npath=" + profile.as_posix() + "\ntarget=android-35\n",
            encoding="utf-8",
        )
        config = {
            "AvdId": NAME,
            "avd.ini.displayname": "dreamtalk Android Local",
            "abi.type": "x86_64",
            "hw.cpu.arch": "x86_64",
            "hw.cpu.ncore": "4",
            "hw.ramSize": "4096",
            "hw.lcd.width": "1080",
            "hw.lcd.height": "2400",
            "hw.lcd.density": "420",
            "hw.gpu.enabled": "yes",
            "hw.gpu.mode": GRAPHICS_MODE,
            "hw.keyboard": "yes",
            "hw.audioInput": "no",
            "hw.audioOutput": "yes",
            "disk.dataPartition.size": "4G",
            "image.sysdir.1": (sdk / "system-images/android-35/google_apis/x86_64").as_posix()
            + "/",
            "tag.id": "google_apis",
            "tag.display": "Google APIs",
            "target": "android-35",
            "showDeviceFrame": "no",
            "fastboot.forceColdBoot": "yes",
        }
        (profile / "config.ini").write_text(
            "\n".join(key + "=" + value for key, value in config.items()) + "\n", encoding="utf-8"
        )
        command = emulator_command(sdk)
        OUT.mkdir(parents=True, exist_ok=True)
        with (OUT / "emulator-console.log").open("ab") as log:
            process = subprocess.Popen(
                command, env=env, stdout=log, stderr=log, creationflags=NO_WINDOW
            )
        write_json(
            OUT / "emulator-session.json",
            {
                "pid": process.pid,
                "serial": SERIAL,
                "adb_port": ADB_PORT,
                "avd": NAME,
                "visible": True,
                "graphics_mode": GRAPHICS_MODE,
            },
        )
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            write_json(
                OUT / "emulator-exit.json",
                {
                    "stage": "boot",
                    "returncode": process.returncode,
                    "returncode_hex": f"{process.returncode & 0xFFFFFFFF:08x}",
                    "graphics_mode": GRAPHICS_MODE,
                },
            )
            raise LocalError("local_emulator_process_exited")
        if (
            adb(sdk, env, "shell", "getprop", "sys.boot_completed", timeout=10).stdout.strip()
            == "1"
        ):
            verify_device(sdk, env)
            abi = adb(sdk, env, "shell", "getprop", "ro.product.cpu.abilist").stdout.strip()
            if "arm64-v8a" not in abi:
                raise LocalError("local_arm_translation_unavailable")
            return sdk, env
        time.sleep(2)
    raise LocalError("local_emulator_boot_timeout")


def ensure_build(force: bool = False) -> dict:
    receipt = current_build()
    if force or receipt is None or not receipt["source_current"]:
        OUT.mkdir(parents=True, exist_ok=True)
        with (OUT / "update.log").open("w", encoding="utf-8") as log:
            result = subprocess.run(
                [
                    "pwsh.exe",
                    "-NoLogo",
                    "-NoProfile",
                    "-File",
                    str(ROOT / "scripts/build-android-local.ps1"),
                ],
                cwd=ROOT,
                stdout=log,
                stderr=log,
                creationflags=NO_WINDOW,
            )
        if result.returncode:
            raise LocalError("local_build_failed")
        receipt = current_build()
    if not receipt or not receipt["source_current"]:
        raise LocalError("local_build_stale")
    return receipt


def open_app(force: bool = False) -> None:
    receipt = ensure_build(force)
    sdk, env = start_device()
    verify_device(sdk, env)
    installed_path = OUT / "installed.json"
    installed = (
        json.loads(installed_path.read_text(encoding="utf-8")) if installed_path.exists() else {}
    )
    exists = adb(sdk, env, "shell", "pm", "path", PACKAGE).stdout.startswith("package:")
    if installed.get("sha256") != receipt["sha256"] or not exists:
        result = adb(sdk, env, "install", "-r", "-t", str(ROOT / receipt["apk"]), timeout=150)
        if result.returncode or "Success" not in result.stdout:
            raise LocalError("local_install_failed")
        write_json(
            installed_path,
            {"sha256": receipt["sha256"], "avd": NAME, "serial": SERIAL, "preserve_data": True},
        )
    result = adb(
        sdk, env, "shell", "am", "start", "-W", "-n", PACKAGE + "/.MainActivity", timeout=60
    )
    if result.returncode or "Error:" in result.stdout + result.stderr:
        raise LocalError("local_app_launch_failed")
    write_json(
        OUT / "last-open.json",
        {
            "sha256": receipt["sha256"],
            "serial": SERIAL,
            "avd": NAME,
            "opened_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "visible": True,
        },
    )
    print("Android local acceptance opened.", flush=True)


@contextlib.contextmanager
def launch_lock():
    import msvcrt

    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "launcher.lock").open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as failure:
            raise LocalError("local_launcher_busy") from failure
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=["fingerprint", "record-build", "finalize-build", "status", "open", "update"],
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--apk", type=Path)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    try:
        if args.action == "fingerprint":
            value = source_fingerprint()
            if args.output:
                write_json(args.output, value)
            else:
                print(value["fingerprint"])
        elif args.action == "record-build":
            record_build(args.apk)
        elif args.action == "finalize-build":
            finalize_build()
        elif args.action == "status":
            value = current_build()
            print(
                json.dumps(
                    {
                        key: value[key]
                        for key in ["apk", "sha256", "version", "built_at", "source_current"]
                    }
                    if value
                    else {"built": False}
                )
            )
        else:
            with launch_lock():
                open_app(force=args.action == "update")
    except Exception as failure:
        code = str(failure) if isinstance(failure, LocalError) else type(failure).__name__
        write_json(
            OUT / "launcher-error.json",
            {"code": code, "time": time.strftime("%Y-%m-%dT%H:%M:%S%z")},
        )
        if args.quiet:
            message = (
                "安卓验收入口正在启动或更新，请稍候。"
                if code == "local_launcher_busy"
                else "安卓验收暂未打开，工程诊断已保存在本机，请将此情况告诉工程端。\n错误码："
                + code
            )
            ctypes.windll.user32.MessageBoxW(None, message, "dreamtalk 安卓本机验收", 0x40)
        elif sys.stderr:
            print("Local acceptance failed: " + code, file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
