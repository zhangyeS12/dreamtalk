"""Whole-save restoration must work with the real current schema and preserve history."""

import asyncio
import shutil
import sqlite3
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from livingworld.application.command_handler import CommandHandler
from livingworld.application.commands import CreateWorld
from livingworld.application.player_event_feed import PlayerEventFeedService
from livingworld.application.player_onboarding import LocalPlayerOnboardingService
from livingworld.application.simulation_clock import EffectiveWorldTimeSource, SystemMonotonicClock
from livingworld.domain.contracts import RequestId
from livingworld.domain.identifiers import WorldId
from livingworld.infrastructure import save_safety as saves
from livingworld.infrastructure.clock import SystemWallClock
from livingworld.infrastructure.persistence import Database
from livingworld.infrastructure.persistence.story_models import (
    WorldNewsBatchRecord,
    WorldNewsSettingsRecord,
)


@pytest.mark.parametrize("with_jobs", [False, True])
def test_full_snapshot_restores_and_quarantines_jobs_without_changing_history(
    tmp_path, monkeypatch, with_jobs
):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    app = tmp_path / "app"
    world = WorldId(uuid4())
    ids = [uuid4(), uuid4()]

    async def seed():
        db = Database(app / "data")
        try:
            await db.initialize()
            clock = SystemWallClock()
            commands = CommandHandler(
                db.unit_of_work,
                clock,
                world_time_source=EffectiveWorldTimeSource(clock, SystemMonotonicClock()),
            )
            await commands.execute(
                CreateWorld(request_id=RequestId(uuid4()), world_id=world, name="恢复测试世界")
            )
            players = PlayerEventFeedService(db.player_event_feed_store())
            player = await LocalPlayerOnboardingService(commands, players).start_at_home(world)
            if with_jobs:
                async with db._sessions() as session, session.begin():
                    session.add(
                        WorldNewsSettingsRecord(
                            world_id=world.value,
                            player_id=player.value,
                            enabled=True,
                            consented_at=datetime.now(UTC),
                            revision=1,
                            state="generating",
                            error=None,
                        )
                    )
                    for identity, state in zip(ids, ("queued", "ready"), strict=True):
                        session.add(
                            WorldNewsBatchRecord(
                                world_id=world.value,
                                batch_id=identity,
                                player_id=player.value,
                                invocation_id=uuid4(),
                                state=state,
                                input_json="{}",
                                created_at=datetime.now(UTC),
                                replenished=False,
                                total=0,
                            )
                        )
        finally:
            await db.close()

    asyncio.run(seed())
    before = saves.metadata(app / "data", integrity=True)
    snapshot = saves.create_snapshot(app, "manual", "0.1.80")
    folder = saves.locate(snapshot["id"])
    sealed = saves.inventory(folder / "payload")
    target = tmp_path / "restore-app"
    shutil.copytree(folder / "payload", target)
    result = saves.restore(target, snapshot["id"], "0.1.80")
    assert result["restored"]
    assert saves.metadata(target / "data", integrity=True)["ids_digest"] == before["ids_digest"]
    assert saves.metadata(app / "data", integrity=True) == before
    assert saves.inventory(folder / "payload") == sealed
    assert saves.guard(target)["problem"] == "save_restored_review_required"
    with sqlite3.connect(target / "data/runtime.sqlite3") as con:
        assert con.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        if with_jobs:
            assert dict(con.execute("SELECT batch_id,state FROM world_news_batches")) == {
                ids[0].hex: "interrupted",
                ids[1].hex: "ready",
            }
            assert con.execute(
                "SELECT enabled,state,revision FROM world_news_settings"
            ).fetchone() == (0, "off", 2)
