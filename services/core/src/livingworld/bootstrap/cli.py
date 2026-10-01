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
from livingworld.application.chat_context import DirectChatContextBuilder
from livingworld.application.chat_conversations import ChatConversationService
from livingworld.application.chat_messages import ChatMessageService
from livingworld.application.chat_recall import EarlierChatRecall
from livingworld.application.command_handler import CommandHandler
from livingworld.application.developer_inspector import (
    INSPECTOR_TRIGGER_KIND,
    DeveloperInspectorService,
)
from livingworld.application.group_chat_context import GroupChatContextBuilder
from livingworld.application.memory import EpisodicMemoryService
from livingworld.application.player_event_feed import PlayerEventFeedService
from livingworld.application.player_onboarding import LocalPlayerOnboardingService
from livingworld.application.runtime import RuntimeStatus, ShutdownRequests
from livingworld.application.scenes import SceneService
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
from livingworld.application.world_locations import WorldLocationsService
from livingworld.application.world_settings import WorldSettingsService
from livingworld.bootstrap.llm_control import HostControlListener
from livingworld.bootstrap.llm_runtime import (
    configure_content_builder,
    configure_direct_chat_reply,
    configure_director,
    configure_group_chat_reply,
    configure_offline_dialogue,
    configure_world_news,
    start_production_llm_session,
)
from livingworld.bootstrap.reader import derive_session, read_bootstrap
from livingworld.domain.contracts import API_PROTOCOL, LOOPBACK_HOST
from livingworld.infrastructure.chat_retrieval import Fts5ChatRecallRanker
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
    developer_tools: bool = False,
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
    director = None
    offline_contact = None
    world_story = None
    try:
        trigger_registry = TriggerKindRegistry(
            {(INSPECTOR_TRIGGER_KIND, 1): lambda _payload: None} if developer_tools else None
        )
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
        if desktop:
            await database.offline_contact_store().reset_visibility()
        await simulation_runtime.start_all()
        command_handler = CommandHandler(
            database.unit_of_work,
            wall_clock,
            world_time_source=time_source,
            mutation_barrier=simulation_runtime,
            wake_signal=wake_signal,
            world_runtime_registrar=simulation_runtime,
        )
        world_settings = WorldSettingsService(
            database.world_directory(),
            command_handler,
            clock_service,
            simulation_runtime,
        )
        player_event_feed = PlayerEventFeedService(database.player_event_feed_store())
        world_content = database.world_content_service()
        chat_conversations = ChatConversationService(
            database.chat_conversation_store(), world_content, player_event_feed, command_handler
        )
        chat_messages = ChatMessageService(
            database.chat_message_store(time_source), player_event_feed
        )
        earlier_chat_recall = EarlierChatRecall(chat_messages, Fts5ChatRecallRanker())
        developer_inspector = None
        if developer_tools:
            developer_inspector = DeveloperInspectorService(
                database.developer_inspector_store(),
                command_handler,
                SceneService(database.unit_of_work, wall_clock),
                EpisodicMemoryService(
                    database.unit_of_work,
                    wall_clock,
                    world_time_source=time_source,
                    mutation_barrier=simulation_runtime,
                ),
                scheduler,
                clock_service,
                simulation_runtime,
                database.character_memory_reader,
                database.unit_of_work,
            )
        llm_session = await start_production_llm_session(config.llm_config_path, database, logger)
        from livingworld.application.action_resolution import ActionResolutionService
        from livingworld.application.conversation_memory import ConversationMemoryService
        from livingworld.application.director import DirectorService

        director = DirectorService(
            database.director_store(),
            player_event_feed,
            configure_director(llm_session),
            ActionResolutionService(
                database.unit_of_work,
                wall_clock,
                world_time_source=time_source,
                mutation_barrier=simulation_runtime,
            ),
            wake_signal,
            credentials_ready=lambda: not desktop or llm_session.credentials.sync_complete,
        )
        from livingworld.application.world_story import WorldNewsKernel, WorldStoryService

        story_store = database.world_story_store()
        news_configured, news_json = configure_world_news(llm_session)
        world_story = WorldStoryService(
            story_store,
            player_event_feed,
            news_configured,
            WorldNewsKernel(database.unit_of_work, wall_clock, time_source, simulation_runtime),
            wake_signal,
            credentials_ready=lambda: not desktop or llm_session.credentials.sync_complete,
            json_output=news_json,
        )

        async def world_work(world, now):
            deadlines = [await director.tick(world, now), await world_story.tick(world, now)]
            return min((value for value in deadlines if value is not None), default=None)

        scheduler_runtime.set_world_work(world_work)
        await world_story.start()
        await director.start()
        from livingworld.application.offline_contact import OfflineContactService

        offline_contact = OfflineContactService(
            database.offline_contact_store(),
            player_event_feed,
            configure_director(llm_session),
            configure_offline_dialogue(llm_session),
            credentials_ready=lambda: not desktop or llm_session.credentials.sync_complete,
        )
        await offline_contact.start()
        conversation_memory_store = database.conversation_memory_store()
        conversation_memory = ConversationMemoryService(
            conversation_memory_store, player_event_feed, configure_content_builder(llm_session)
        )
        chat_reply = configure_direct_chat_reply(
            llm_session,
            chat_messages,
            DirectChatContextBuilder(
                chat_conversations,
                chat_messages,
                database.local_profile_store(),
                database.character_memory_reader,
                world_content.list_common_lore,
                earlier_chat_recall,
                conversation_memory_store,
                database.character_observed_event_reader,
                lambda owner: database.character_activity_context_reader(owner, time_source),
            ),
            journal=story_store,
        )
        group_chat_reply = configure_group_chat_reply(
            llm_session,
            chat_messages,
            GroupChatContextBuilder(
                chat_conversations,
                chat_messages,
                database.local_profile_store(),
                database.character_memory_reader,
                world_content.list_common_lore,
                earlier_chat_recall,
                conversation_memory_store,
                database.character_observed_event_reader,
                lambda owner: database.character_activity_context_reader(owner, time_source),
            ),
            journal=story_store,
        )
        from livingworld.application.content_builder import ContentBuilder
        from livingworld.infrastructure.content_research import DDGSContentResearch

        content_builder = ContentBuilder(
            world_content,
            database.content_builder_store(),
            DDGSContentResearch(),
            configure_content_builder(llm_session),
        )
        status = RuntimeStatus(version("dreamtalk-core"), generation, llm_health=llm_session.health)
        if desktop:
            # Read from the unbuffered OS pipe so interpreter shutdown cannot race
            # a BufferedReader lock held by the control thread.
            control_loop = asyncio.get_running_loop()
            control_listener = HostControlListener(
                sys.stdin.buffer.raw,
                llm_session.credentials,
                logger,
                on_credentials_changed=lambda: control_loop.call_soon_threadsafe(
                    lambda: (
                        director.credentials_changed(),
                        offline_contact.credentials_changed(),
                        world_story.credentials_changed(),
                    )
                ),
            )
            control_listener.start()
        from livingworld.application.character_activity_setup import CharacterActivitySetupService

        app = create_app(
            status,
            shutdown,
            session,
            lambda: None,
            logger,
            config.allowed_origins,
            developer_inspector,
            world_settings,
            player_event_feed,
            database.local_profile_store(),
            world_content,
            LocalPlayerOnboardingService(command_handler, player_event_feed),
            chat_conversations,
            chat_messages,
            chat_reply,
            group_chat_reply,
            content_builder,
            database.content_repository(),
            chat_recall=earlier_chat_recall,
            conversation_memory=conversation_memory,
            director=director,
            world_story=world_story,
            offline_contact=offline_contact,
            character_activity_setup=CharacterActivitySetupService(
                database.character_activity_directory(),
                chat_conversations,
                player_event_feed,
                command_handler,
            ),
            world_locations=WorldLocationsService(
                database.local_location_directory(), command_handler
            ),
        )
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
            if world_story is not None:
                await world_story.aclose()
            if offline_contact is not None:
                await offline_contact.aclose()
            if director is not None:
                await director.aclose()
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
    parser = argparse.ArgumentParser(description="dreamtalk system runtime")
    parser.add_argument("--desktop", action="store_true")
    parser.add_argument("--bootstrap-path", type=Path, required=True)
    parser.add_argument("--parent-pid", type=int)
    parser.add_argument("--developer-tools", action="store_true")
    args = parser.parse_args()
    if args.desktop and (args.parent_pid is None or args.parent_pid <= 0):
        parser.error("desktop_parent_pid_required")
    try:
        asyncio.run(
            run(
                args.bootstrap_path,
                args.parent_pid if args.desktop else None,
                desktop=args.desktop,
                developer_tools=args.developer_tools,
            )
        )
    except KeyboardInterrupt:
        pass
    except Exception:
        StructuredLogger().emit("core", "startup_or_runtime_failed", level="ERROR")
        raise SystemExit(1) from None
