import asyncio
from uuid import uuid4

import pytest
from livingworld.application.commands import CreateLocation, CreatePlayer, MovePlayer
from livingworld.application.player_event_feed import PlayerEventFeedService
from livingworld.domain.identifiers import LocationId, PlayerId
from livingworld.domain.values import Revision


def test_event_feed_is_bound_to_one_player_and_never_reads_unobserved_events(environment):
    async def run():
        env = environment
        try:
            await env.initialize()
            service = PlayerEventFeedService(env.database.player_event_feed_store())
            assert await service.selected_player(env.world) is None
            assert await service.known_events(env.world) == ()

            elsewhere = LocationId(env.world, uuid4())
            other = PlayerId(env.world, uuid4())
            await env.handler.execute(
                env.command(CreateLocation, location_id=elsewhere, name="别处")
            )
            await env.handler.execute(
                env.command(
                    CreatePlayer,
                    player_id=other,
                    name="另一个玩家",
                    initial_location_id=env.cafe,
                )
            )
            other_move = env.command(
                MovePlayer,
                player_id=other,
                destination_id=elsewhere,
                expected_presence_revision=Revision(),
            )
            await env.handler.execute(other_move)

            with pytest.raises(ValueError, match="player_not_found_in_world"):
                await service.bind_player(PlayerId(env.world, uuid4()))
            await service.bind_player(env.player)
            assert await service.selected_player(env.world) == env.player
            assert await service.known_events(env.world) == ()

            own_move = env.command(
                MovePlayer,
                player_id=env.player,
                destination_id=env.cafe,
                expected_presence_revision=Revision(),
            )
            await env.handler.execute(own_move)
            await env.handler.execute(own_move)
            known = await service.known_events(env.world)
            assert len(known) == 1
            assert known[0].event_type == "PlayerMoved"
            assert known[0].observed_at == known[0].occurred_at
            assert known[0].ledger_position > 0

            await service.bind_player(other)
            assert await service.selected_player(env.world) == other
            other_known = await service.known_events(env.world)
            assert len(other_known) == 1
            assert other_known[0].event_id != known[0].event_id
        finally:
            await env.database.close()

    asyncio.run(run())
