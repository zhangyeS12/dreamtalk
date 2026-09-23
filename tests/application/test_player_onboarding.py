import asyncio

import pytest
from livingworld.application.commands import CreateWorld
from livingworld.application.errors import EntityNotFoundError
from livingworld.application.player_event_feed import PlayerEventFeedService
from livingworld.application.player_onboarding import LocalPlayerOnboardingService
from livingworld.domain.identifiers import WorldId
from livingworld.infrastructure.persistence.models import (
    LocationRecord,
    PlayerPresenceRecord,
    PlayerRecord,
    WorldEventRecord,
)
from sqlalchemy import select


def test_local_player_starts_at_home_without_duplicate_canonical_state(environment):
    async def run():
        env = environment
        await env.initialize(seed=False)
        await env.handler.execute(env.command(CreateWorld, name="新世界"))
        players = PlayerEventFeedService(env.database.player_event_feed_store())
        onboarding = LocalPlayerOnboardingService(env.handler, players)
        try:
            player = await onboarding.start_at_home(env.world)
            assert await players.selected_player(env.world) == player
            assert await onboarding.start_at_home(env.world) == player
            async with env.database._sessions() as session:
                locations = (await session.scalars(select(LocationRecord))).all()
                stored_players = (await session.scalars(select(PlayerRecord))).all()
                presences = (await session.scalars(select(PlayerPresenceRecord))).all()
                events = (await session.scalars(select(WorldEventRecord))).all()
            assert [(item.name, item.world_id) for item in locations] == [("家", env.world.value)]
            assert len(stored_players) == len(presences) == 1
            assert stored_players[0].player_id == player.value
            assert presences[0].location_id == locations[0].location_id
            assert [item.event_type for item in events] == [
                "WorldCreated",
                "LocationCreated",
                "PlayerCreated",
                "PlayerPlaced",
            ]
            await env.restart()
            restarted = LocalPlayerOnboardingService(
                env.handler, PlayerEventFeedService(env.database.player_event_feed_store())
            )
            assert await restarted.start_at_home(env.world) == player
            assert len(await env.rows("world_events")) == 4
        finally:
            await env.database.close()

    asyncio.run(run())


def test_unknown_world_does_not_create_home_or_player(environment):
    async def run():
        env = environment
        await env.initialize(seed=False)
        service = LocalPlayerOnboardingService(
            env.handler, PlayerEventFeedService(env.database.player_event_feed_store())
        )
        try:
            with pytest.raises(EntityNotFoundError, match="World does not exist"):
                await service.start_at_home(WorldId(env.world.value))
            assert await env.rows("locations") == []
            assert await env.rows("players") == []
        finally:
            await env.database.close()

    asyncio.run(run())


def test_interrupted_entry_resumes_without_repeating_location_event(environment):
    async def run():
        env = environment
        await env.initialize(seed=False)
        await env.handler.execute(env.command(CreateWorld, name="新世界"))
        players = PlayerEventFeedService(env.database.player_event_feed_store())

        class InterruptAfterHome:
            def __init__(self, handler):
                self.handler = handler
                self.calls = 0

            async def execute(self, command):
                self.calls += 1
                if self.calls == 2:
                    raise RuntimeError("simulated_interruption")
                return await self.handler.execute(command)

        try:
            with pytest.raises(RuntimeError, match="simulated_interruption"):
                await LocalPlayerOnboardingService(
                    InterruptAfterHome(env.handler), players
                ).start_at_home(env.world)
            assert [row.event_type for row in await env.rows("world_events")] == [
                "WorldCreated",
                "LocationCreated",
            ]
            assert await players.selected_player(env.world) is None
            await LocalPlayerOnboardingService(env.handler, players).start_at_home(env.world)
            assert [row.event_type for row in await env.rows("world_events")] == [
                "WorldCreated",
                "LocationCreated",
                "PlayerCreated",
                "PlayerPlaced",
            ]
        finally:
            await env.database.close()

    asyncio.run(run())
