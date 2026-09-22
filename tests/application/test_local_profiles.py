import asyncio
from uuid import uuid4

import pytest
from alembic import command
from livingworld.application.command_handler import CommandHandler
from livingworld.application.commands import CreateWorld
from livingworld.application.errors import EntityNotFoundError
from livingworld.application.local_profile import LocalProfile
from livingworld.application.simulation_clock import EffectiveWorldTimeSource, SystemMonotonicClock
from livingworld.domain.contracts import RequestId
from livingworld.domain.errors import ConcurrencyConflictError
from livingworld.domain.identifiers import WorldId
from livingworld.domain.values import Revision
from livingworld.infrastructure.clock import SystemWallClock
from livingworld.infrastructure.persistence import Database
from livingworld.infrastructure.persistence.migration import BINDING_REVISION, _alembic_config
from livingworld.infrastructure.persistence.models import WorldEventRecord
from sqlalchemy import func, select


def test_profiles_upgrade_isolate_persist_and_reject_stale_edits_without_world_events(tmp_path):
    async def run():
        database = Database(tmp_path)
        # Exercise a real 0015 -> head takeover, including a repeated startup.
        async with database.engine.begin() as connection:
            await connection.run_sync(
                lambda sync: command.upgrade(_alembic_config(sync), BINDING_REVISION)
            )
        await database.initialize()
        first, second = WorldId(uuid4()), WorldId(uuid4())
        wall = SystemWallClock()
        handler = CommandHandler(
            database.unit_of_work,
            wall,
            world_time_source=EffectiveWorldTimeSource(wall, SystemMonotonicClock()),
        )
        for world in (first, second):
            await handler.execute(
                CreateWorld(request_id=RequestId(uuid4()), world_id=world, name="世界")
            )
        store = database.local_profile_store()
        try:
            assert await store.load() == LocalProfile()
            general = await store.save(LocalProfile("通用名字", "通用个人描述"))
            specific = await store.save(LocalProfile("世界身份", "当前世界的独立身份"), first)
            assert general.revision == specific.revision == Revision(1)
            assert await store.load(second) == LocalProfile()
            with pytest.raises(EntityNotFoundError):
                await store.save(LocalProfile(), WorldId(uuid4()))
            with pytest.raises(ConcurrencyConflictError):
                await store.save(LocalProfile("过期编辑", "不可覆盖"))
            assert await store.load() == general
            edits = await asyncio.gather(
                store.save(LocalProfile("修改甲", "甲", Revision(1)), first),
                store.save(LocalProfile("修改乙", "乙", Revision(1)), first),
                return_exceptions=True,
            )
            assert sum(isinstance(item, LocalProfile) for item in edits) == 1
            assert sum(isinstance(item, ConcurrencyConflictError) for item in edits) == 1
            saved = await store.load(first)
            assert saved.revision == Revision(2)
            async with database._sessions() as session:
                assert await session.scalar(select(func.count()).select_from(WorldEventRecord)) == 2
        finally:
            await database.close()
        reopened = Database(tmp_path)
        try:
            await reopened.initialize()
            assert await reopened.local_profile_store().load() == general
            assert await reopened.local_profile_store().load(first) == saved
            assert await reopened.local_profile_store().load(second) == LocalProfile()
        finally:
            await reopened.close()

    asyncio.run(run())


def test_profile_description_is_not_in_repr_and_text_limits_are_enforced():
    assert "private-canary" not in repr(LocalProfile("我", "private-canary"))
    with pytest.raises(ValueError, match="profile_text_limit"):
        LocalProfile(description="x" * 8001)
