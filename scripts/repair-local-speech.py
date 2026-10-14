"""User-requested Windows service repair; no model imports or speech submission."""

import argparse
import ctypes
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from ctypes import wintypes
from pathlib import Path

REVISION = 7


class RepairError(ValueError):
    pass


def check(condition, code="speech_local_repair_unverified"):
    if not condition:
        raise RepairError(code)


def path_key(path):
    value = str(Path(path).resolve())
    if value.startswith("\\\\?\\UNC\\"):
        value = "\\\\" + value[8:]
    elif value.startswith("\\\\?\\"):
        value = value[4:]
    return os.path.normcase(value)


def health(secret):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(
        "http://127.0.0.1:7861/health", headers={"Authorization": "Bearer " + secret}
    )
    try:
        with opener.open(request, timeout=5) as response:
            data = response.read(4097)
    except urllib.error.HTTPError:
        raise RepairError("speech_local_repair_unverified") from None
    except urllib.error.URLError as error:
        if getattr(error.reason, "winerror", None) == 10061:
            return None
        raise RepairError("speech_local_probe_failed") from None
    check(len(data) <= 4096)
    value = json.loads(data)
    check(value.get("engine") == "indextts-2.5" and value.get("protocol") == 2)
    check(isinstance(value.get("busy"), bool))
    return value


def inventory():
    # Query only the owner of the fixed listener. Never print command lines.
    command = """
$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$owners = @(Get-NetTCPConnection -LocalPort 7861 -State Listen -ErrorAction SilentlyContinue)
if ($owners.Count -ne 1 -or $owners[0].LocalAddress -ne '127.0.0.1') { exit 2 }
$ownerId = [uint32]$owners[0].OwningProcess
$p = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + $ownerId)
if (-not $p) { exit 2 }
[pscustomobject]@{ pid=$ownerId; command=$p.CommandLine } | ConvertTo-Json -Compress
"""
    result = subprocess.run(
        [
            str(Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"),
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            command,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
        creationflags=subprocess.CREATE_NO_WINDOW,
        check=False,
    )
    check(result.returncode == 0 and len(result.stdout) <= 32768)
    value = json.loads(result.stdout)
    check(isinstance(value.get("pid"), int) and value["pid"] > 0)
    check(isinstance(value.get("command"), str) and len(value["command"]) <= 16384)
    return value


def arguments(command):
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    shell.CommandLineToArgvW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
    shell.CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)
    kernel.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel.LocalFree.restype = wintypes.HLOCAL
    count = ctypes.c_int()
    pointer = shell.CommandLineToArgvW(command, ctypes.byref(count))
    check(bool(pointer))
    try:
        check(2 <= count.value <= 10)
        return [pointer[index] for index in range(count.value)]
    finally:
        kernel.LocalFree(pointer)


def verify_command(command, root, project):
    args = arguments(command)
    if len(args) > 2 and args[1] == "-u":
        args = [args[0], *args[2:]]
    check(
        path_key(args[0])
        in {path_key(root / ".venv/Scripts/python.exe"), path_key(sys._base_executable)}
    )
    script = Path(args[1]).resolve(strict=True)
    check(script.name == "serve-indextts.py" and script.parent.name == "scripts")
    check(script.is_file() and script.stat().st_size <= 1024 * 1024)
    if path_key(script) != path_key(project / "scripts/serve-indextts.py"):
        marker = script.parent.parent / ".dreamtalk-package.json"
        check(marker.is_file() and marker.stat().st_size <= 1024 * 1024)
        package = json.loads(marker.read_text(encoding="utf-8"))
        check(package.get("identity") == "app.livingworld.desktop")
        check(
            package.get("files", {}).get("scripts/serve-indextts.py")
            == hashlib.sha256(script.read_bytes()).hexdigest()
        )
    check((len(args) - 2) % 2 == 0)
    options = {}
    for key, value in zip(args[2::2], args[3::2], strict=True):
        check(key in {"--model-dir", "--token-file", "--port"} and key not in options)
        options[key] = value
    check(path_key(options.get("--model-dir", "")) == path_key(root / "checkpoints"))
    check(path_key(options.get("--token-file", "")) == path_key(root / "dreamtalk-voice-token.txt"))
    check(options.get("--port", "7861") == "7861")


def stop_verified(owner, root, project, secret, revision):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    # Retain this handle across rechecks/stopping to prevent PID reuse from
    # redirecting termination. Never kill a parent process or process tree.
    handle = kernel.OpenProcess(0x1000 | 0x0001 | 0x00100000, False, owner["pid"])
    check(bool(handle))
    try:
        image = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(image))
        check(bool(kernel.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(size))))
        trusted_images = {path_key(sys.executable), path_key(sys._base_executable)}
        check(path_key(image.value) in trusted_images)
        repeated = inventory()
        check(repeated == owner)
        verify_command(repeated["command"], root, project)
        info = health(secret)
        check(info is not None)
        check(info.get("inference_revision") == revision, "speech_local_repair_changed")
        check(not info["busy"], "speech_local_repair_busy")
        if info.get("maintenance_protocol") == 1 and info.get("pid") == owner["pid"]:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            request = urllib.request.Request(
                "http://127.0.0.1:7861/maintenance/shutdown",
                data=b"",
                headers={"Authorization": "Bearer " + secret},
                method="POST",
            )
            try:
                with opener.open(request, timeout=5) as response:
                    check(response.status == 200)
            except urllib.error.HTTPError as error:
                raise RepairError(
                    "speech_local_repair_busy"
                    if error.code == 409
                    else "speech_local_repair_failed"
                ) from None
        else:
            # Compatibility with older bridges is limited to authenticated idle
            # bridges in the selected environment and a verified package/source.
            check(bool(kernel.TerminateProcess(handle, 0)), "speech_local_repair_failed")
        check(kernel.WaitForSingleObject(handle, 5000) == 0, "speech_local_repair_failed")
    finally:
        kernel.CloseHandle(handle)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    options = parser.parse_args()
    check(os.name == "nt", "speech_local_repair_unsupported")
    root = options.model_root.resolve(strict=True)
    project = options.project_root.resolve(strict=True)
    path = root / "dreamtalk-voice-token.txt"
    check(path.is_file() and 32 <= path.stat().st_size <= 4098)
    secret = path.read_text(encoding="utf-8").strip()
    check(32 <= len(secret) <= 4096 and "\n" not in secret and "\r" not in secret)
    info = health(secret)
    if info is None:
        return "stopped"
    check(not info["busy"], "speech_local_repair_busy")
    if info.get("inference_revision") == REVISION:
        return "ready"
    revision = info.get("inference_revision")
    check(type(revision) is int and 1 <= revision < REVISION)
    owner = inventory()
    verify_command(owner["command"], root, project)
    stop_verified(owner, root, project, secret, revision)
    for _attempt in range(10):
        if health(secret) is None:
            return "updated"
        time.sleep(0.1)
    raise RepairError("speech_local_repair_failed")


if __name__ == "__main__":
    try:
        print(json.dumps({"state": main()}))
    except RepairError as error:
        print(json.dumps({"error": str(error)}))
        sys.exit(1)
    except Exception:
        print(json.dumps({"error": "speech_local_repair_failed"}))
        sys.exit(1)
