"""One policy evaluator for authoring, planning and authoritative execution."""

from uuid import UUID

from sqlalchemy import func, select

from livingworld.infrastructure.persistence.location_policy_models import (
    CharacterLocationPolicyRecord,
    LocationAccessRecord,
    LocationPolicyRecord,
)
from livingworld.infrastructure.persistence.models import LocationRecord, WorldEventRecord


class LocationRules:
    def __init__(self, locations, parents, hidden, grants, scopes):
        self.locations, self.parents = locations, parents
        self.hidden, self.grants, self.scopes = hidden, grants, scopes

    @classmethod
    async def load(cls, session, world):
        locations = set(
            await session.scalars(
                select(LocationRecord.location_id).where(LocationRecord.world_id == world)
            )
        )
        policies = (
            await session.scalars(
                select(LocationPolicyRecord).where(LocationPolicyRecord.world_id == world)
            )
        ).all()
        grants = (
            await session.execute(
                select(LocationAccessRecord.location_id, LocationAccessRecord.character_id).where(
                    LocationAccessRecord.world_id == world
                )
            )
        ).all()
        scopes = (
            await session.scalars(
                select(CharacterLocationPolicyRecord).where(
                    CharacterLocationPolicyRecord.world_id == world
                )
            )
        ).all()
        return cls(
            locations,
            {p.location_id: p.parent_id for p in policies},
            {p.location_id for p in policies if p.hidden},
            {(location, character) for location, character in grants},
            {p.character_id: (p.initial_location_id, p.locked, p.revision) for p in scopes},
        )

    def ancestors(self, location):
        path, seen = [], set()
        while location is not None:
            if location in seen or location not in self.locations:
                return ()  # fail closed for corrupted or cyclic authoring data
            seen.add(location)
            path.append(location)
            location = self.parents.get(location)
        return tuple(path)

    def visible(self, character, location):
        path = self.ancestors(location)
        return bool(path) and all(
            node not in self.hidden or (node, character) in self.grants for node in path
        )

    async def scope(self, session, world, character):
        if character not in self.scopes:
            # Original placement is authoritative; never relabel today's position
            # as the original starting place after years of movement.
            original = await session.scalar(
                select(WorldEventRecord.payload)
                .where(
                    WorldEventRecord.world_id == world,
                    WorldEventRecord.event_type == "CharacterPlaced",
                    func.json_extract(WorldEventRecord.payload, "$.character_id") == str(character),
                    func.json_extract(WorldEventRecord.payload, "$.before_location_id").is_(None),
                )
                .order_by(WorldEventRecord.ledger_position)
                .limit(1)
            )
            self.scopes[character] = (
                (UUID(original["location_id"]), False, 0) if original else (None, False, 0)
            )
        return self.scopes[character]

    async def allowed(self, session, world, character, destination):
        initial, locked, _ = await self.scope(session, world, character)
        return (
            initial is not None
            and initial in self.ancestors(destination)
            and (not locked or destination == initial)
            and self.visible(character, destination)
        )


async def character_can_enter(session, world, character, destination):
    return await (await LocationRules.load(session, world)).allowed(
        session, world, character, destination
    )
