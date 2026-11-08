import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest
from livingworld.application.character_activity_setup import CharacterActivitySetupService
from livingworld.application.chat_conversations import ChatConversationService
from livingworld.application.command_handler import CommandHandler
from livingworld.application.errors import IdempotencyConflictError
from livingworld.application.example_worlds import ExampleWorldService
from livingworld.application.player_event_feed import PlayerEventFeedService
from livingworld.application.player_onboarding import LocalPlayerOnboardingService
from livingworld.application.scheduler import (
    SchedulerWakeSignal,
    SimulationScheduler,
    SimulationSchedulerRuntime,
    TriggerKindRegistry,
)
from livingworld.application.simulation_clock import EffectiveWorldTimeSource, SystemMonotonicClock
from livingworld.application.simulation_runtime import WorldClockService, WorldSimulationRuntime
from livingworld.application.world_locations import WorldLocationsService
from livingworld.application.world_settings import WorldSettingsService
from livingworld.domain.contracts import RequestId
from livingworld.infrastructure.clock import SystemWallClock
from livingworld.infrastructure.example_templates import campus_template
from livingworld.infrastructure.persistence import Database
from livingworld.infrastructure.persistence.models import ChatMessageRecord
from sqlalchemy import func, select


@asynccontextmanager
async def example_environment(path):
    db = Database(path)
    await db.initialize()
    wall, monotonic, wake = SystemWallClock(), SystemMonotonicClock(), SchedulerWakeSignal()
    source = EffectiveWorldTimeSource(wall, monotonic)
    scheduler = SimulationScheduler(
        db.simulation_scheduler_store(TriggerKindRegistry()), wall, wake
    )
    scheduler_runtime = SimulationSchedulerRuntime(scheduler, source, wake)
    clocks = WorldClockService(
        db.world_clock_store(), wall, source, on_clock_changed=scheduler_runtime.clock_reanchored
    )
    runtime = WorldSimulationRuntime(clocks, scheduler, scheduler_runtime, source, monotonic)
    await runtime.start_all()
    commands = CommandHandler(
        db.unit_of_work,
        wall,
        world_time_source=source,
        mutation_barrier=runtime,
        wake_signal=wake,
        world_runtime_registrar=runtime,
    )
    worlds = WorldSettingsService(db.world_directory(), commands, clocks, runtime)
    players = PlayerEventFeedService(db.player_event_feed_store())
    content = db.world_content_service()
    chats = ChatConversationService(db.chat_conversation_store(), content, players, commands)
    activities = CharacterActivitySetupService(
        db.character_activity_directory(), chats, players, commands
    )
    service = ExampleWorldService(
        campus_template(),
        db.example_world_store(),
        worlds,
        content,
        LocalPlayerOnboardingService(commands, players),
        WorldLocationsService(db.local_location_directory(), commands),
        activities,
    )
    try:
        yield SimpleNamespace(
            db=db,
            service=service,
            worlds=worlds,
            content=content,
            players=players,
            chats=chats,
            activities=activities,
        )
    finally:
        await runtime.aclose()
        await db.close()


def test_example_is_explicit_idempotent_and_uses_normal_world_content(tmp_path):
    async def run():
        async with example_environment(tmp_path) as env:
            catalog = await env.service.catalog()
            assert not await env.worlds.list_worlds()  # Preview has no side effects.
            request = RequestId(uuid4())
            world = await env.service.create(
                catalog["id"], request, catalog["reviewed_hash"], ["school", "classmates"]
            )
            assert (
                await env.service.create(
                    catalog["id"], request, catalog["reviewed_hash"], ["classmates", "school"]
                )
                == world
            )
            assert len(await env.worlds.list_worlds()) == 1
            imported = await env.content.store.list_imports(world)
            assert [item.kind for item in imported].count("character") == 3
            assert [item.kind for item in imported].count("lorebook") == 1
            assert len(await env.content.list_common_lore(world)) == 2
            player, characters = await env.activities.list_characters(world)
            assert player == await env.players.selected_player(world)
            assert len(characters) == 3 and all(item.initialized for item in characters)
            assert len({item.initial_location_id for item in characters}) == 1
            contacts = await env.chats.activity_contacts(world)
            assert {item.character_name for item in contacts} == {"沈清禾", "夏小满", "周明远"}
            presence = await env.players.selected_presence(world)
            assert presence is not None
            async with env.db._sessions() as session:
                assert (
                    await session.scalar(select(func.count()).select_from(ChatMessageRecord)) == 0
                )
            # A repeated confirmation cannot restore a grant the user later revoked.
            entry = (await env.content.list_common_lore(world))[0]
            await env.content.set_common_lore(
                world, entry.import_id, entry.entry.content_id.value, False
            )
            await env.service.create(
                catalog["id"], request, catalog["reviewed_hash"], ["school", "classmates"]
            )
            assert len(await env.content.list_common_lore(world)) == 1
            with pytest.raises(IdempotencyConflictError):
                await env.service.create(catalog["id"], request, catalog["reviewed_hash"], [])

    asyncio.run(run())


def test_example_can_resume_after_process_restart_without_duplicate_cards(tmp_path, monkeypatch):
    async def run():
        request = RequestId(uuid4())
        async with example_environment(tmp_path) as env:
            catalog = await env.service.catalog()

            async def interrupted(*args):
                raise OSError("simulated_local_interruption")

            monkeypatch.setattr(env.activities, "initialize_card", interrupted)
            with pytest.raises(OSError):
                await env.service.create(
                    catalog["id"], request, catalog["reviewed_hash"], ["school"]
                )
            assert not await env.worlds.list_worlds()  # Incomplete books stay hidden.
            assert (await env.service.catalog())["pending"][0]["request_id"] == str(request.value)
        async with example_environment(tmp_path) as env:
            world = await env.service.create(
                catalog["id"], request, catalog["reviewed_hash"], ["school"]
            )
            assert len(await env.worlds.list_worlds()) == 1
            assert len(await env.content.store.list_imports(world)) == 4
            assert not (await env.service.catalog())["pending"]
            assert len((await env.activities.list_characters(world))[1]) == 3

    asyncio.run(run())


def test_changed_preview_or_unknown_public_entry_cannot_create_world(tmp_path):
    async def run():
        async with example_environment(tmp_path) as env:
            for template_id, digest, entries in (
                ("unknown", env.service.reviewed_hash, []),
                ("campus-v1", "0" * 64, []),
                ("campus-v1", env.service.reviewed_hash, ["private-secret"]),
            ):
                with pytest.raises(ValueError):
                    await env.service.create(template_id, RequestId(uuid4()), digest, entries)
            assert not await env.worlds.list_worlds()
            assert not (await env.service.catalog())["pending"]

    asyncio.run(run())
