import argparse
import asyncio
import ctypes
import json
import os
import socket
from importlib.metadata import version
from pathlib import Path
from uuid import uuid4

import uvicorn

from livingworld.adapters.http.app import create_app
from livingworld.application.runtime import RuntimeStatus, ShutdownRequests
from livingworld.bootstrap.reader import derive_session, read_bootstrap
from livingworld.domain.contracts import API_PROTOCOL, LOOPBACK_HOST
from livingworld.infrastructure.database import bootstrap_database
from livingworld.infrastructure.logging import StructuredLogger


def parent_alive(pid: int) -> bool:
    """Windows development parent watcher; no POSIX-specific lifecycle implementation."""
    if os.name != "nt":
        raise RuntimeError("desktop_parent_watch_requires_windows")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.OpenProcess(0x00100000, False, pid)
    if not handle:
        return False
    try:
        return kernel.WaitForSingleObject(handle, 0) == 0x00000102
    finally:
        kernel.CloseHandle(handle)


async def run(bootstrap_path: Path, parent_pid: int | None = None) -> None:
    logger = StructuredLogger()
    config = read_bootstrap(bootstrap_path)
    generation = str(uuid4())
    session = derive_session(
        config.bootstrap_secret.get_secret_value(), config.instance_nonce, generation
    )
    config.bootstrap_secret = type(config.bootstrap_secret)("")
    config.log_dir.mkdir(parents=True, exist_ok=True)
    logger = StructuredLogger(logfile=config.log_dir / f"core-{generation}.jsonl")
    status = RuntimeStatus(version("livingworld-core"), generation)
    shutdown = ShutdownRequests()
    app = create_app(
        status,
        shutdown,
        session,
        lambda: bootstrap_database(config.data_dir),
        logger,
        config.allowed_origins,
    )
    ready_path = bootstrap_path.parent / "ready.json"
    ready_path.unlink(missing_ok=True)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((LOOPBACK_HOST, 0))
    sock.listen(128)
    sock.setblocking(False)
    port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=LOOPBACK_HOST,
            port=port,
            access_log=False,
            log_config=None,
            log_level="critical",
            timeout_graceful_shutdown=5,
        )
    )
    task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        while not server.started:
            if task.done():
                await task
                raise RuntimeError("server_start_failed")
            await asyncio.sleep(0.02)
        ready = {
            "endpoint": f"http://{LOOPBACK_HOST}:{port}",
            "api_protocol": API_PROTOCOL,
            "core_version": status.core_version,
            "generation": generation,
            "instance_nonce": config.instance_nonce,
            "pid": os.getpid(),
            "launcher_pid": os.getppid(),
        }
        temporary = ready_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(ready), encoding="utf-8")
        temporary.replace(ready_path)
        logger.emit("core", "core_ready")
        while not task.done() and not shutdown.event.is_set():
            if parent_pid is not None and not parent_alive(parent_pid):
                logger.emit("core", "parent_exited")
                break
            await asyncio.sleep(0.05)
        status.ready = False
        server.should_exit = True
        logger.emit("core", "core_shutdown_started")
        await task
        logger.emit("core", "core_shutdown_completed")
    finally:
        server.should_exit = True
        if not task.done():
            await task
        ready_path.unlink(missing_ok=True)
        sock.close()
        session = ""


def main() -> None:
    parser = argparse.ArgumentParser(description="LivingWorld system runtime")
    parser.add_argument("--desktop", action="store_true")
    parser.add_argument("--bootstrap-path", type=Path, required=True)
    parser.add_argument("--parent-pid", type=int)
    args = parser.parse_args()
    if args.desktop and (args.parent_pid is None or args.parent_pid <= 0):
        parser.error("desktop_parent_pid_required")
    try:
        asyncio.run(run(args.bootstrap_path, args.parent_pid if args.desktop else None))
    except KeyboardInterrupt:
        pass
    except Exception:
        StructuredLogger().emit("core", "startup_or_runtime_failed", level="ERROR")
        raise SystemExit(1) from None
