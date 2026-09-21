import argparse
import asyncio
import ctypes
import json
import os
import socket
import sys
from importlib.metadata import version
from pathlib import Path
from uuid import uuid4

import uvicorn

from livingworld.adapters.http.app import create_app
from livingworld.application.runtime import RuntimeStatus, ShutdownRequests
from livingworld.application.scheduler import (
    SchedulerWakeSignal,
    SimulationScheduler,
    SimulationSchedulerRuntime,
    TriggerKindRegistry,
)
from livingworld.application.simulation_clock import (
    EffectiveWorldTimeSource,
    SystemMonotonicClock,
)
from livingworld.application.simulation_runtime import (
    WorldClockService,
    WorldSimulationRuntime,
)
from livingworld.bootstrap.llm_control import HostControlListener
from livingworld.bootstrap.llm_runtime import start_production_llm_session
from livingworld.bootstrap.reader import derive_session, read_bootstrap
from livingworld.domain.contracts import API_PROTOCOL, LOOPBACK_HOST
from livingworld.infrastructure.clock import SystemWallClock
from livingworld.infrastructure.database import bootstrap_database
from livingworld.infrastructure.logging import StructuredLogger
from livingworld.infrastructure.persistence.errors import MigrationCompatibilityError
from livingworld.infrastructure.scheduler_runtime import (
    StructuredCatchUpDiagnosticSink,
    StructuredSchedulerDiagnosticSink,
)


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


async def run(
    bootstrap_path: Path,
    parent_pid: int | None = None,
    *,
    desktop: bool = False,
) -> None:
    logger = StructuredLogger()
    config = read_bootstrap(bootstrap_path)
    generation = str(uuid4())
    session = derive_session(
        config.bootstrap_secret.get_secret_value(), config.instance_nonce, generation
    )
    config.bootstrap_secret = type(config.bootstrap_secret)("")
    config.log_dir.mkdir(parents=True, exist_ok=True)
    logger = StructuredLogger(logfile=config.log_dir / f"core-{generation}.jsonl")
    shutdown = ShutdownRequests()
    ready_path = bootstrap_path.parent / "ready.json"
    ready_path.unlink(missing_ok=True)
    try:
        database = await bootstrap_database(config.data_dir)
    except MigrationCompatibilityError as error:
        logger.emit("migration", error.code.value, level="ERROR")
        raise
    llm_session = None
    control_listener = None
    scheduler_runtime = None
    simulation_runtime = None
    try:
        trigger_registry = TriggerKindRegistry()
        wake_signal = SchedulerWakeSignal()
        wall_clock = SystemWallClock()
        monotonic_clock = SystemMonotonicClock()
        time_source = EffectiveWorldTimeSource(wall_clock, monotonic_clock)
        scheduler = SimulationScheduler(
            database.simulation_scheduler_store(trigger_registry),
            wall_clock,
            wake_signal,
        )
        scheduler_runtime = SimulationSchedulerRuntime(
            scheduler,
            time_source,
            wake_signal,
            diagnostics=StructuredSchedulerDiagnosticSink(logger),
        )
        clock_service = WorldClockService(
            database.world_clock_store(),
            wall_clock,
            time_source,
            on_clock_changed=scheduler_runtime.clock_reanchored,
        )
        simulation_runtime = WorldSimulationRuntime(
            clock_service,
            scheduler,
            scheduler_runtime,
            time_source,
            monotonic_clock,
            diagnostics=StructuredCatchUpDiagnosticSink(logger),
        )
        await simulation_runtime.start_all()
        llm_session = await start_production_llm_session(config.llm_config_path, database, logger)
        status = RuntimeStatus(
            version("livingworld-core"), generation, llm_health=llm_session.health
        )
        if desktop:
            # Read from the unbuffered OS pipe so interpreter shutdown cannot race
            # a BufferedReader lock held by the control thread.
            control_listener = HostControlListener(
                sys.stdin.buffer.raw, llm_session.credentials, logger
            )
            control_listener.start()
        app = create_app(status, shutdown, session, lambda: None, logger, config.allowed_origins)
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
        finally:
            server.should_exit = True
            if not task.done():
                await task
            ready_path.unlink(missing_ok=True)
            sock.close()
            session = ""
    finally:
        shutdown_error = None
        try:
            if simulation_runtime is not None:
                await simulation_runtime.aclose()
            elif scheduler_runtime is not None:
                await scheduler_runtime.aclose()
        except BaseException as error:
            shutdown_error = error
            logger.emit("simulation_runtime", "clock_checkpoint_failed", level="ERROR")
        finally:
            if control_listener is not None and not control_listener.join(1.0):
                logger.emit("host_control", "host_control_close_timeout", level="ERROR")
            if llm_session is not None:
                await llm_session.aclose()
            await database.close()
        if shutdown_error is not None:
            raise shutdown_error
        logger.emit("core", "core_shutdown_completed")


def main() -> None:
    parser = argparse.ArgumentParser(description="LivingWorld system runtime")
    parser.add_argument("--desktop", action="store_true")
    parser.add_argument("--bootstrap-path", type=Path, required=True)
    parser.add_argument("--parent-pid", type=int)
    args = parser.parse_args()
    if args.desktop and (args.parent_pid is None or args.parent_pid <= 0):
        parser.error("desktop_parent_pid_required")
    try:
        asyncio.run(
            run(
                args.bootstrap_path,
                args.parent_pid if args.desktop else None,
                desktop=args.desktop,
            )
        )
    except KeyboardInterrupt:
        pass
    except Exception:
        StructuredLogger().emit("core", "startup_or_runtime_failed", level="ERROR")
        raise SystemExit(1) from None
