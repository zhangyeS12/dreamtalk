"""Offline Android synchronization checks; no APK build, installed app or provider calls."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import time

ROOT = Path(__file__).resolve().parents[1]
NPM = "npm.cmd" if os.name == "nt" else "npm"
NPX = "npx.cmd" if os.name == "nt" else "npx"
WORK = ROOT / "artifacts/windows-sync-20261108"
PYTHON = ROOT / ".venv-check/Scripts/python.exe"
TOOLS_PYTHON = Path("D:/LivingWorld/.venv/Scripts/python.exe")
MODULES = (
    "advanced_lore chat_context chat_conversations chat_diagnostics chat_messages chat_paths "
    "chat_privacy chat_prompt_composition chat_provider_feedback chat_reply_claim "
    "chat_reply_formats chat_reply chat_speaker_labels chat_turn_budget common_lore "
    "episodic_memory group_chat_conversations group_chat_reply private_reply_protocol "
    "recent_dialogue scheduler_model"
).split()
CORE_MODULES = (
    "llm_accounting llm_budget llm_chat_turn_execution llm_execution llm_production "
    "llm_routing llm_streaming"
).split()
GUARD = """import ipaddress
import socket
import pytest

@pytest.fixture(autouse=True)
def offline_network_only(monkeypatch):
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_getaddrinfo = socket.getaddrinfo
    def allowed(host):
        if host in ('localhost', b'localhost'):
            return True
        if isinstance(host, bytes):
            host = host.decode("ascii")
        try:
            return ipaddress.ip_address(host).is_loopback
        except ValueError:
            return False
    def connect(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6) and not allowed(address[0]):
            raise AssertionError('offline_check_external_network_blocked')
        return original_connect(sock, address)
    def connect_ex(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6) and not allowed(address[0]):
            raise AssertionError('offline_check_external_network_blocked')
        return original_connect_ex(sock, address)
    def getaddrinfo(host, *args, **kwargs):
        if host is not None and not allowed(host):
            raise AssertionError('offline_check_external_dns_blocked')
        return original_getaddrinfo(host, *args, **kwargs)
    monkeypatch.setattr(socket.socket, 'connect', connect)
    monkeypatch.setattr(socket.socket, 'connect_ex', connect_ex)
    monkeypatch.setattr(socket, 'getaddrinfo', getaddrinfo)
"""


def check(group):
    parent = Path(tempfile.gettempdir()).resolve()
    isolation = Path(tempfile.mkdtemp(prefix=f"dreamtalk-sync-{group}-", dir=parent)).resolve()
    if not isolation.is_relative_to(parent) or isolation.is_relative_to(ROOT):
        raise RuntimeError("invalid_check_isolation")
    env = os.environ.copy()
    for name in ("LOCALAPPDATA", "APPDATA", "XDG_CACHE_HOME", "XDG_CONFIG_HOME", "TEMP", "TMP"):
        path = isolation / name.lower()
        path.mkdir()
        env[name] = str(path)
    env.update(
        PYTHONUTF8="1",
        PYTHONDONTWRITEBYTECODE="1",
        DREAMTALK_CHECK_PYTHON=str(PYTHON),
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        PYTHONPATH=str(ROOT / "services/core/src") + os.pathsep + str(isolation),
        NO_PROXY="127.0.0.1,localhost,::1",
        no_proxy="127.0.0.1,localhost,::1",
        RUFF_CACHE_DIR=str(isolation / "ruff-cache"),
    )
    if group == "core":
        (isolation / "offline_guard.py").write_text(GUARD, encoding="utf-8")
        modules = [f"tests/application/test_{name}.py" for name in MODULES]
        modules += [f"tests/core/test_{name}.py" for name in CORE_MODULES]
        modules += ["tests/persistence/test_upgrade_paths.py", "tests_mobile"]
        commands = [
            [
                str(PYTHON),
                "-m",
                "pytest",
                "-p",
                "offline_guard",
                "-q",
                "--maxfail=3",
                "--basetemp",
                str(isolation / "pytest"),
                *modules,
            ]
        ]
    elif group == "web":
        commands = [
            [NPM, "run", "typecheck"],
            [NPM, "test", "--", "--maxWorkers=2"],
            [NPM, "run", "build:web"],
        ]
    else:
        record = json.loads((WORK / "source-state.json").read_text(encoding="utf-8"))
        sources = [item["path"] for item in record["transfers"] if item["path"].endswith(".py")]
        sources += [
            "tests_mobile/test_mobile_chat_sync.py",
            "scripts/check-windows-sync.py",
            "scripts/check-mobile-private-browser.py",
        ]
        commands = [
            [str(PYTHON), "scripts/generate-api-contracts.py", "--check"],
            [str(TOOLS_PYTHON), "-m", "ruff", "check", *sources],
            [str(TOOLS_PYTHON), "-m", "ruff", "format", "--check", *sources],
            [NPX, "--no-install", "pyright", "--project", "pyrightconfig.json"],
        ]
    log = WORK / f"{group}-checks.log"
    results = []
    with log.open("w", encoding="utf-8") as stream:
        for command in commands:
            stream.write("COMMAND " + json.dumps(command) + "\n")
            stream.flush()
            started = time()
            result = subprocess.run(
                command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=1200
            )
            results.append(
                {
                    "command": command,
                    "exit_code": result.returncode,
                    "seconds": round(time() - started, 2),
                }
            )
            if result.returncode:
                break
    report = {
        "group": group,
        "results": results,
        "passed": all(item["exit_code"] == 0 for item in results),
        "isolation": isolation.name,
    }
    (WORK / f"{group}-checks.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"group": group, "passed": report["passed"], "log": str(log)}), flush=True)
    return report["passed"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", choices=["all", "core", "web", "static"], default="all")
    args = parser.parse_args()
    groups = ["core", "web", "static"] if args.group == "all" else [args.group]
    with ThreadPoolExecutor(max_workers=len(groups)) as pool:
        results = list(pool.map(check, groups))
    sys.exit(0 if all(results) else 1)
