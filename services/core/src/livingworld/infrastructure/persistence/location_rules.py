"""One policy evaluator for authoring, planning and authoritative execution."""

import hashlib
import json
from uuid import UUID, uuid5

from sqlalchemy import func, select

from livingworld.infrastructure.persistence.location_policy_models import (
    CharacterLocationPolicyRecord,
    LocationAccessRecord,
    LocationPolicyRecord,
)
from livingworld.infrastructure.persistence.models import (
    LocalLocationCatalogRecord,
    LocationRecord,
    WorldEventRecord,
)


class LocationRules:
    def __init__(
        self,
        locations,
        parents,
        hidden,
        grants,
        scopes,
        regions=(),
        residencies=None,
        catalogued=None,
    ):
        self.locations, self.parents = locations, parents
        self.hidden, self.grants, self.scopes = hidden, grants, scopes
        self.regions = set(regions)
        self.residencies = residencies or {}
        self.catalogued = set(locations if catalogued is None else catalogued)

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
            {p.location_id for p in policies if p.is_region},
            {p.character_id: p.residency for p in scopes},
            set(
                await session.scalars(
                    select(LocalLocationCatalogRecord.location_id).where(
                        LocalLocationCatalogRecord.world_id == world,
                        LocalLocationCatalogRecord.removed_at.is_(None),
                    )
                )
            )
            | {uuid5(world, "livingworld:local-home:v1")},
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
            and initial in self.locations
            and (destination in self.catalogued or destination == initial)
            and (not locked or destination == initial)
            and self.visible(character, destination)
        )

    def region(self, location):
        path = self.ancestors(location)
        # Explicit regional boundaries take precedence; unmarked trees use their
        # real root. A virtual world connector never becomes a real location.
        return next((node for node in path if node in self.regions), path[-1] if path else None)

    def distance(self, first, second):
        left, right = self.ancestors(first), self.ancestors(second)
        if not left or not right:
            return 1_000
        shared = next((node for node in left if node in right), None)
        steps = left.index(shared) + right.index(shared) if shared else len(left) + len(right)
        return steps + (6 if self.region(first) != self.region(second) else 0)

    async def movement_signature(self, session, world, character):
        initial, locked, _ = await self.scope(session, world, character)
        allowed = sorted(
            [
                node
                for node in self.locations
                if await self.allowed(session, world, character, node)
            ],
            key=str,
        )
        value = [
            str(initial),
            locked,
            # A tendency change affects the next batch, not admission of an
            # already legal route. Authoring CAS still uses the policy revision.
            [[str(node), str(self.parents.get(node)), node in self.regions] for node in allowed],
        ]
        return hashlib.sha256(json.dumps(value, separators=(",", ":")).encode()).hexdigest()


async def character_can_enter(session, world, character, destination):
    from livingworld.infrastructure.persistence.authored_lifecycle import removed_character_ids

    if character in await removed_character_ids(session, world):
        return False
    return await (await LocationRules.load(session, world)).allowed(
        session, world, character, destination
    )
