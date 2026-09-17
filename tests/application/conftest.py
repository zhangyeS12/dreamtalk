"""Real isolated SQLite environment, populated only through canonical commands."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from livingworld.application.command_handler import CommandHandler
from livingworld.application.commands import (
    CreateCharacter,
    CreateLocation,
    CreatePlayer,
    CreateWorld,
)
from livingworld.domain.contracts import RequestId
from livingworld.domain.identifiers import CharacterId, LocationId, PlayerId, WorldId
from livingworld.domain.participants import PlayerActivity, PlayerAvailability
from livingworld.domain.values import WorldTime
from livingworld.infrastructure.persistence import Database
from sqlalchemy import text


class FixedClock:
    value = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)

    def __init__(self):
        self.calls = 0

    def now_utc(self):
        self.calls += 1
        return self.value


class Environment:
    def __init__(self, path):
        self.path = path
        self.world = WorldId(uuid4())
        self.home = LocationId(self.world, uuid4())
        self.cafe = LocationId(self.world, uuid4())
        self.park = LocationId(self.world, uuid4())
        self.player = PlayerId(self.world, uuid4())
        self.alice = CharacterId(self.world, uuid4())
        self.bob = CharacterId(self.world, uuid4())
        self.clock = FixedClock()
        self.database = Database(path)
        self.handler = CommandHandler(self.database.unit_of_work, self.clock)

    def command(self, command_type, **values):
        return command_type(request_id=RequestId(uuid4()), world_id=self.world, **values)

    async def initialize(self, seed=True):
        await self.database.initialize()
        if not seed:
            return
        await self.handler.execute(
            self.command(CreateWorld, name="World", initial_time=WorldTime(123))
        )
        for identity, name in ((self.home, "Home"), (self.cafe, "Cafe"), (self.park, "Park")):
            await self.handler.execute(
                self.command(CreateLocation, location_id=identity, name=name)
            )
        await self.handler.execute(
            self.command(
                CreatePlayer,
                player_id=self.player,
                name="Player",
                initial_location_id=self.home,
                activity_state=PlayerActivity.INACTIVE,
                availability_state=PlayerAvailability.BUSY,
            )
        )
        for identity, name in ((self.alice, "Alice"), (self.bob, "Bob")):
            await self.handler.execute(
                self.command(CreateCharacter, character_id=identity, name=name)
            )

    async def restart(self):
        await self.database.close()
        self.database = Database(self.path)
        await self.database.initialize()
        self.handler = CommandHandler(self.database.unit_of_work, self.clock)

    async def rows(self, table):
        # Table names come exclusively from test code; this is not an application port.
        async with self.database.engine.connect() as connection:
            return (await connection.execute(text(f"SELECT * FROM {table}"))).all()

    async def snapshot(self):
        return {
            table: await self.rows(table)
            for table in (
                "worlds",
                "world_clocks",
                "locations",
                "players",
                "player_presences",
                "characters",
                "character_states",
                "relationships",
                "world_events",
                "world_ledger_cursors",
                "command_receipts",
                "knowledge_assertions",
                "observations",
            )
        }


@pytest.fixture
def environment(tmp_path):
    return Environment(tmp_path)
