import asyncio
from dataclasses import replace
from uuid import uuid4

import pytest
from livingworld.domain.identifiers import (
    CharacterId,
    EventId,
    KnowledgeAssertionId,
    LocationId,
    PlayerId,
    WorldId,
)
from livingworld.domain.participants import Character, Player
from livingworld.domain.relationships import Relationship
from livingworld.infrastructure.persistence import Database
from livingworld.infrastructure.persistence.mapping import to_record
from livingworld.infrastructure.persistence.models import (
    KnowledgeAssertionRecord,
)
from livingworld.infrastructure.persistence.store import PersistenceStore
from sqlalchemy import and_, insert, text
from sqlalchemy.exc import IntegrityError


def record_update(record):
    return record.__table__.update().where(
        and_(
            *(
                column == getattr(record, column.name)
                for column in record.__table__.primary_key.columns
            )
        )
    )


def values(record):
    return {column.name: getattr(record, column.name) for column in record.__table__.columns}


@pytest.mark.parametrize(
    ("name", "changes"),
    [
        ("truth", {"owner_character_id": "alice"}),
        ("truth", {"owner_player_id": "player"}),
        ("belief", {"owner_character_id": None}),
        ("belief", {"owner_player_id": "player"}),
        ("player_knowledge", {"owner_player_id": None}),
        ("player_knowledge", {"owner_character_id": "alice"}),
        ("player_knowledge", {"scope": "unknown"}),
    ],
)
def test_knowledge_ownership_check_constraints(tmp_path, objects, populate, name, changes):
    async def run():
        database = Database(tmp_path)
        try:
            await database.initialize()
            await populate(database)
            record = to_record(objects[name])
            data = values(record)
            data["assertion_id"] = uuid4()
            for key, value in changes.items():
                if value == "alice":
                    value = objects["alice"].character_id.value
                elif value == "player":
                    value = objects["player"].player_id.value
                data[key] = value
            with pytest.raises(IntegrityError, match="ck_knowledge_owner"):
                async with database.engine.begin() as connection:
                    await connection.execute(insert(KnowledgeAssertionRecord).values(**data))
        finally:
            await database.close()

    asyncio.run(run())


@pytest.mark.parametrize(
    ("name", "field"),
    [
        ("relationship", "source_character_id"),
        ("observation", "principal_player_id"),
        ("observation", "target_event_id"),
        ("receipt", "result_event_id"),
    ],
)
def test_polymorphic_reference_cannot_bypass_fk_with_null(tmp_path, objects, populate, name, field):
    async def run():
        database = Database(tmp_path)
        try:
            await database.initialize()
            await populate(database)
            record = to_record(objects[name])
            data = values(record)
            data[field] = None
            # UPDATE isolates the CHECK failure from duplicate primary keys.
            with pytest.raises(IntegrityError):
                async with database.engine.begin() as connection:
                    await connection.execute(record_update(record).values(**{field: None}))
        finally:
            await database.close()

    asyncio.run(run())


@pytest.mark.parametrize(
    ("name", "field"),
    [
        ("presence", "location_id"),
        ("relationship", "source_character_id"),
        ("character_state", "location_id"),
        ("connection", "target_id"),
        ("belief", "owner_character_id"),
        ("truth", "provenance_event_id"),
        ("belief", "source_assertion_id"),
        ("observation", "target_event_id"),
        ("receipt", "result_event_id"),
    ],
)
def test_cross_world_foreign_reference_rejected(tmp_path, objects, populate, name, field):
    async def run():
        database = Database(tmp_path)
        try:
            await database.initialize()
            await populate(database)
            foreign_world = WorldId(uuid4())
            # The referenced UUID really exists, but exclusively in a different world.
            other_world = replace(
                objects["world"],
                world_id=foreign_world,
                clock=replace(objects["world"].clock, world_id=foreign_world),
            )
            other_location = replace(
                objects["location"],
                world_id=foreign_world,
                location_id=LocationId(foreign_world, uuid4()),
            )
            other_character = replace(
                objects["alice"],
                world_id=foreign_world,
                character_id=CharacterId(foreign_world, uuid4()),
            )
            other_event = replace(
                objects["event"],
                world_id=foreign_world,
                event_id=EventId(foreign_world, uuid4()),
                causation_id=None,
            )
            other_assertion = replace(
                objects["truth"],
                world_id=foreign_world,
                assertion_id=KnowledgeAssertionId(foreign_world, uuid4()),
                provenance_event_id=other_event.event_id,
            )
            for entity in (
                other_world,
                other_location,
                other_character,
                other_event,
                other_assertion,
            ):
                await database.store().add(entity)
            record = to_record(objects[name])
            if field in {"location_id", "target_id"}:
                replacement = other_location.location_id.value
            elif field in {"owner_character_id", "source_character_id"}:
                replacement = other_character.character_id.value
            elif field == "source_assertion_id":
                replacement = other_assertion.assertion_id.value
            else:
                replacement = other_event.event_id.value
            updates = {field: replacement}
            if field == "target_event_id":
                updates["target_id"] = replacement
            if field == "result_event_id":
                updates["result_id"] = replacement
            if field == "source_character_id":
                updates["source_id"] = replacement
            with pytest.raises(IntegrityError, match="FOREIGN KEY"):
                async with database.engine.begin() as connection:
                    assert (await connection.execute(text("PRAGMA foreign_keys"))).scalar_one() == 1
                    await connection.execute(record_update(record).values(**updates))
        finally:
            await database.close()

    asyncio.run(run())


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE world_events SET event_type='changed'",
        "DELETE FROM world_events",
    ],
)
def test_world_event_database_append_only(tmp_path, objects, populate, sql):
    async def run():
        database = Database(tmp_path)
        try:
            await database.initialize()
            store = await populate(database)
            with pytest.raises(IntegrityError, match="world_event_immutable"):
                async with database.engine.begin() as connection:
                    await connection.execute(text(sql))
            assert await store.reload(objects["event"]) == objects["event"]
        finally:
            await database.close()

    asyncio.run(run())


def test_world_event_adapter_has_no_update_or_delete():
    assert {name for name in vars(PersistenceStore) if not name.startswith("_")} == {
        "add",
        "reload",
    }


def test_same_uuid_principal_types_remain_distinct(tmp_path, objects):
    async def run():
        database = Database(tmp_path)
        try:
            await database.initialize()
            store = database.store()
            await store.add(objects["world"])
            world = objects["world"].world_id
            shared = uuid4()
            character = Character(world, CharacterId(world, shared), "Character")
            player = Player(world, PlayerId(world, shared), "Player")
            await store.add(character)
            await store.add(player)
            edges = (
                Relationship(world, character.character_id, player.player_id),
                Relationship(world, player.player_id, character.character_id),
            )
            for edge in edges:
                await store.add(edge)
                assert await store.reload(edge) == edge
        finally:
            await database.close()

    asyncio.run(run())


def test_presence_not_nullable_and_world_time_not_float(tmp_path, objects, populate):
    async def run():
        database = Database(tmp_path)
        try:
            await database.initialize()
            await populate(database)
            for sql in (
                "UPDATE player_presences SET location_id=NULL",
                "UPDATE world_clocks SET logical_time=1.5",
                "UPDATE knowledge_assertions SET valid_from=1.5",
                "UPDATE observations SET observed_at=1.5",
            ):
                with pytest.raises(IntegrityError):
                    async with database.engine.begin() as connection:
                        await connection.execute(text(sql))
        finally:
            await database.close()

    asyncio.run(run())


def test_idempotency_and_request_scope_are_per_world(tmp_path, objects, populate):
    async def run():
        database = Database(tmp_path)
        try:
            await database.initialize()
            store = await populate(database)
            foreign_world = WorldId(uuid4())
            await store.add(
                replace(
                    objects["world"],
                    world_id=foreign_world,
                    clock=replace(objects["world"].clock, world_id=foreign_world),
                )
            )
            event = replace(
                objects["event"],
                world_id=foreign_world,
                event_id=EventId(foreign_world, objects["event"].event_id.value),
            )
            receipt = replace(
                objects["receipt"], world_id=foreign_world, result_reference=event.event_id
            )
            await store.add(event)
            await store.add(receipt)
            assert await store.reload(event) == event
            assert await store.reload(receipt) == receipt
        finally:
            await database.close()

    asyncio.run(run())
