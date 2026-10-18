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

from livingworld.adapters.http.app import create_product_app
from livingworld.adapters.http.services import HttpServices
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
    if config.retry_update_verification and not desktop:
        raise ValueError("save_update_retry_unavailable")
    # This guard runs before migrations, recall initialization, or background providers.
    from livingworld.infrastructure.save_safety import (
        create_snapshot,
        guard,
        metadata,
        observe_world_change,
    )

    if desktop:
        from livingworld.infrastructure.save_slots import recover as recover_save_slot

        await asyncio.to_thread(recover_save_slot, config.data_dir.parent)
        if config.retry_update_verification:
            # Only the private desktop bootstrap may request this explicit retry.
            # Keep the failure marker until the host verifies the actual store.
            handoff_path = config.data_dir.parent / "updates/handoff.json"
            from livingworld.infrastructure.save_safety import IDENTITY, read_json

            handoff = read_json(handoff_path)
            if handoff.get("identity") != IDENTITY:
                raise ValueError("save_update_retry_unavailable")
        storage = await asyncio.to_thread(
            guard,
            config.data_dir.parent,
            retry_update_verification=config.retry_update_verification,
            include_snapshots=False,
        )
        if storage["recovery_required"]:
            raise ValueError("save_recovery_required")
        if storage["current"]:
            from livingworld.infrastructure.persistence.migration import HEAD_REVISION

            if storage["current"]["revisions"] != [HEAD_REVISION]:
                await asyncio.to_thread(
                    create_snapshot,
                    config.data_dir.parent,
                    "pre_migration",
                    version("dreamtalk-core"),
                )
    generation = str(uuid4())
    session = derive_session(
        config.bootstrap_secret.get_secret_value(), config.instance_nonce, generation
    )
    config.bootstrap_secret = type(config.bootstrap_secret)("")
    config.log_dir.mkdir(parents=True, exist_ok=True)
    logger = StructuredLogger(logfile=config.log_dir / f"core-{generation}.jsonl")
    # Native DLL imports must precede the blocking host-control stdin reader
    # and database/executor threads. Load no model and touch no user cache here.
    from livingworld.infrastructure.semantic_chat_retrieval import prepare_native_recall

    logger.emit("chat_retrieval", "native_runtime_initializing")
    native_ready = prepare_native_recall()
    logger.emit(
        "chat_retrieval",
        "native_runtime_ready" if native_ready else "native_runtime_unavailable",
        level="INFO" if native_ready else "WARNING",
    )
    from livingworld.application.update_maintenance import UpdateMaintenance

    maintenance = UpdateMaintenance()
    if desktop and (config.data_dir.parent / "updates/handoff.json").exists():
        handoff = json.loads(
            (config.data_dir.parent / "updates/handoff.json").read_text(encoding="utf-8")
        )
        verified_path = config.data_dir.parent / "updates/verified.json"
        verified = (
            json.loads(verified_path.read_text(encoding="utf-8")) if verified_path.exists() else {}
        )
        if config.retry_update_verification or verified.get("recovery") != handoff.get("recovery"):
            maintenance.startup_hold = True
            maintenance.prepare()
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
    proactive_contact = None
    world_story = None
    speech = None
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
        await chat_messages.recover_reply_executions()
        lexical_recall = Fts5ChatRecallRanker()
        earlier_chat_recall = EarlierChatRecall(chat_messages, lexical_recall)

        def observed_event_reader(owner):
            return database.character_observed_event_reader(owner, ranker=lexical_recall)

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
        from livingworld.application.chat_media import ChatMediaService
        from livingworld.infrastructure.media_providers import ChatMediaProviders

        chat_media = ChatMediaService(
            database.chat_media_store(), ChatMediaProviders(llm_session.credentials), logger
        )
        chat_messages.media = chat_media
        chat_media.maintenance = maintenance
        await chat_media.store.recover(clean_orphans=not maintenance.startup_hold)
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
            credentials_ready=lambda: (
                not maintenance.preparing and (not desktop or llm_session.credentials.sync_complete)
            ),
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
            credentials_ready=lambda: (
                not maintenance.preparing and (not desktop or llm_session.credentials.sync_complete)
            ),
            json_output=news_json,
        )

        director.maintenance = world_story.maintenance = maintenance

        async def world_work(world, now):
            with maintenance.operation() as admitted:
                if not admitted:
                    return None
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
            credentials_ready=lambda: (
                not maintenance.preparing and (not desktop or llm_session.credentials.sync_complete)
            ),
        )
        offline_contact.maintenance = maintenance
        await offline_contact.start()
        from livingworld.application.proactive_contact import ProactiveContactService
        from livingworld.bootstrap.llm_runtime import configure_proactive_dialogue

        proactive_configured, proactive_json = configure_proactive_dialogue(llm_session)

        proactive_contact = ProactiveContactService(
            database.proactive_contact_store(),
            database.chat_unread_store(),
            player_event_feed,
            proactive_configured,
            credentials_ready=lambda: (
                not maintenance.preparing and (not desktop or llm_session.credentials.sync_complete)
            ),
            json_output=proactive_json,
        )
        proactive_contact.maintenance = maintenance
        await proactive_contact.start()

        # A world-work deadline may have been suppressed by the update barrier.
        # Cancellation/lease expiry must wake the existing schedulers again;
        # their durable claim rules still prohibit replaying failed provider jobs.
        def resume_after_update():
            if not shutdown.requested:
                director.credentials_changed()
                world_story.credentials_changed()
                offline_contact.credentials_changed()
                proactive_contact.credentials_changed()

        maintenance.on_resume = resume_after_update

        from livingworld.application.long_chat_memory import LongChatMemoryService

        long_memory_store = database.long_chat_memory_store()
        long_memory = LongChatMemoryService(long_memory_store, player_event_feed)
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
                observed_event_reader,
                lambda owner: database.character_activity_context_reader(owner, time_source),
                long_memory_store,
                social_reader=database.faction_store().context_for_character,
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
                observed_event_reader,
                lambda owner: database.character_activity_context_reader(owner, time_source),
                long_memory_store,
                social_reader=database.faction_store().context_for_character,
            ),
            journal=story_store,
            logger=logger,
        )
        from livingworld.application.content_builder import ContentBuilder
        from livingworld.infrastructure.content_research import DDGSContentResearch

        content_builder = ContentBuilder(
            world_content,
            database.content_builder_store(),
            DDGSContentResearch(),
            configure_content_builder(llm_session),
        )
        status = RuntimeStatus(
            version("dreamtalk-core"),
            generation,
            llm_health=llm_session.health,
            world_llm_health=llm_session.health,
        )
        if desktop:
            # Read from the unbuffered OS pipe so interpreter shutdown cannot race
            # a BufferedReader lock held by the control thread.
            control_loop = asyncio.get_running_loop()
            control_listener = HostControlListener(
                getattr(sys.stdin.buffer, "raw", sys.stdin.buffer),
                llm_session.credentials,
                logger,
                on_credentials_changed=lambda: control_loop.call_soon_threadsafe(
                    lambda: (
                        director.credentials_changed(),
                        offline_contact.credentials_changed(),
                        proactive_contact.credentials_changed(),
                        world_story.credentials_changed(),
                    )
                ),
            )
            control_listener.start()
        from livingworld.application.character_activity_setup import CharacterActivitySetupService
        from livingworld.application.chat_export import ChatExportService
        from livingworld.application.speech import SpeechService
        from livingworld.application.world_content_export import WorldContentExportService
        from livingworld.application.world_covers import WorldCoverService
        from livingworld.application.world_deletion import WorldDeletionService
        from livingworld.infrastructure.exports.json_content import JsonContentExporter
        from livingworld.infrastructure.speech_cards import inspect_audio
        from livingworld.infrastructure.speech_providers import IndexSpeechProviders
        from livingworld.infrastructure.world_cover_images import PillowCoverImageProcessor

        speech_store = database.speech_store()
        await speech_store.recover()
        speech = SpeechService(
            speech_store,
            chat_messages,
            IndexSpeechProviders(llm_session.credentials, speech_store),
            inspect_audio,
            maintenance,
            logger=logger,
        )
        await speech.start()

        from livingworld.application.example_worlds import ExampleWorldService
        from livingworld.infrastructure.example_templates import campus_template

        onboarding = LocalPlayerOnboardingService(command_handler, player_event_feed)
        activity_setup = CharacterActivitySetupService(
            database.character_activity_directory(),
            chat_conversations,
            player_event_feed,
            command_handler,
        )
        example_worlds = ExampleWorldService(
            campus_template(),
            database.example_world_store(),
            world_settings,
            world_content,
            onboarding,
            WorldLocationsService(database.local_location_directory(), command_handler),
            activity_setup,
        )

        app = create_product_app(
            status=status,
            shutdown=shutdown,
            session_token=session,
            initialize=None,
            logger=logger,
            allowed_origins=config.allowed_origins,
            services=HttpServices(
                developer_inspector=developer_inspector,
                world_settings=world_settings,
                player_event_feed=player_event_feed,
                local_profiles=database.local_profile_store(),
                world_content=world_content,
                player_onboarding=onboarding,
                chat_conversations=chat_conversations,
                chat_messages=chat_messages,
                chat_reply=chat_reply,
                group_chat_reply=group_chat_reply,
                content_builder=content_builder,
                content_repository=database.content_repository(),
                chat_recall=earlier_chat_recall,
                conversation_memory=conversation_memory,
                long_chat_memory=long_memory,
                director=director,
                world_story=world_story,
                offline_contact=offline_contact,
                proactive_contact=proactive_contact,
                world_locations=WorldLocationsService(
                    database.local_location_directory(), command_handler
                ),
                character_activity_setup=activity_setup,
                world_covers=WorldCoverService(
                    database.world_cover_repository(),
                    database.content_asset_store(),
                    PillowCoverImageProcessor(),
                ),
                factions=database.faction_store(),
                maintenance=maintenance,
                world_deletion=WorldDeletionService(
                    database.world_deletion_store(),
                    simulation_runtime,
                    maintenance,
                    world_content,
                    database.content_asset_store(),
                    long_memory.store.ranker,
                ),
                content_exports=WorldContentExportService(
                    world_content.store, database.content_repository(), JsonContentExporter()
                ),
                chat_exports=ChatExportService(
                    database.chat_export_store(), player_event_feed, wall_clock
                ),
                speech=speech,
                chat_media=chat_media,
                storage_metadata=(lambda: metadata(config.data_dir)) if desktop else None,
                storage_observer=(lambda: observe_world_change(config.data_dir.parent))
                if desktop
                else None,
                example_worlds=example_worlds,
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
            logger.emit("core", "core_http_stopped")
            ready_path.unlink(missing_ok=True)
            sock.close()
            session = ""
    finally:
        shutdown_error = None
        try:
            logger.emit("core", "core_background_stop_started")
            if speech is not None:
                await speech.aclose()
            logger.emit("core", "core_speech_stopped")
            if world_story is not None:
                await world_story.aclose()
            if proactive_contact is not None:
                await proactive_contact.aclose()
            if offline_contact is not None:
                await offline_contact.aclose()
            if director is not None:
                await director.aclose()
            if simulation_runtime is not None:
                await simulation_runtime.aclose()
            elif scheduler_runtime is not None:
                await scheduler_runtime.aclose()
            logger.emit("core", "core_background_stopped")
        except BaseException as error:
            shutdown_error = error
            logger.emit("simulation_runtime", "clock_checkpoint_failed", level="ERROR")
        finally:
            logger.emit("core", "core_resources_stop_started")
            if control_listener is not None and not control_listener.join(1.0):
                logger.emit("host_control", "host_control_close_timeout", level="ERROR")
            logger.emit("core", "core_host_control_joined")
            if llm_session is not None:
                await llm_session.aclose()
            logger.emit("core", "core_llm_connections_closed")
            await database.close()
            logger.emit("core", "core_database_closed")
        if shutdown_error is not None:
            raise shutdown_error
        logger.emit("core", "core_shutdown_completed")


def main() -> None:
    parser = argparse.ArgumentParser(description="dreamtalk system runtime")
    parser.add_argument("--desktop", action="store_true")
    parser.add_argument("--bootstrap-path", type=Path)
    parser.add_argument("--storage-request", type=Path)
    parser.add_argument("--parent-pid", type=int)
    parser.add_argument("--developer-tools", action="store_true")
    args = parser.parse_args()
    if args.storage_request:
        if args.desktop or args.bootstrap_path or args.developer_tools:
            parser.error("storage_tool_arguments_invalid")
        from livingworld.infrastructure.save_safety import run_request

        run_request(args.storage_request)
        return
    if args.bootstrap_path is None:
        parser.error("bootstrap_path_required")
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
