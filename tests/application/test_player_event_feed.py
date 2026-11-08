import asyncio
from uuid import uuid4

import pytest
from livingworld.application.commands import CreateLocation, CreatePlayer, MovePlayer
from livingworld.application.player_event_feed import PlayerEventFeedService
from livingworld.domain.identifiers import LocationId, PlayerId
from livingworld.domain.participants import PlayerAvailability
from livingworld.domain.values import Revision
from livingworld.infrastructure.persistence.models import LocalUserProfileRecord, PlayerRecord
from sqlalchemy import event
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession


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
            status = await service.selected_presence(env.world)
            assert status.player_id == env.player
            assert status.availability is PlayerAvailability.BUSY
            assert status.revision == Revision()
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


def test_player_binding_waits_for_an_existing_writer_without_a_stale_snapshot(
    environment, monkeypatch
):
    async def run():
        env = environment
        await env.initialize()
        service = PlayerEventFeedService(env.database.player_event_feed_store())
        binding_started, read_finished, release_read = (
            asyncio.Event(),
            asyncio.Event(),
            asyncio.Event(),
        )
        scalar = AsyncSession.scalar

        async def hold_player_read(session, statement, *args, **kwargs):
            result = await scalar(session, statement, *args, **kwargs)
            if getattr(statement, "column_descriptions", [{}])[0].get("entity") is PlayerRecord:
                read_finished.set()
                await release_read.wait()
            return result

        def observe_begin(connection, cursor, statement, parameters, context, many):
            if statement.startswith("BEGIN"):
                binding_started.set()

        monkeypatch.setattr(AsyncSession, "scalar", hold_player_read)
        task, listening = None, False
        try:
            async with env.database.engine.connect() as connection:
                writer = await connection.execution_options(livingworld_write_intent=True)
                async with writer.begin():
                    await writer.execute(
                        sqlite_insert(LocalUserProfileRecord).values(
                            singleton=1,
                            name="Synthetic concurrent writer",
                            description="",
                            revision=1,
                        )
                    )
                    event.listen(
                        env.database.engine.sync_engine, "before_cursor_execute", observe_begin
                    )
                    listening = True
                    task = asyncio.create_task(service.bind_player(env.player))
                    await asyncio.wait_for(binding_started.wait(), 3)
                    # A deferred reader can finish here; a writer must wait for the
                    # transaction above. Release either case after the same commit.
                    try:
                        await asyncio.wait_for(read_finished.wait(), 1)
                    except TimeoutError:
                        pass
            release_read.set()
            await asyncio.wait_for(task, 5)
            assert await service.selected_player(env.world) == env.player
        finally:
            release_read.set()
            if task is not None and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            if listening:
                event.remove(
                    env.database.engine.sync_engine, "before_cursor_execute", observe_begin
                )
            await env.database.close()

    asyncio.run(run())
