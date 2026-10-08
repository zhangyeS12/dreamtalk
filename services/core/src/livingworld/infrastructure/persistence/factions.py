"""Author-edited, world-local factions; direct co-membership means acquaintance."""

import json
from collections import defaultdict
from uuid import UUID, uuid4, uuid5

from sqlalchemy import delete, or_, select

from livingworld.domain.content.models import CharacterDefinition
from livingworld.infrastructure.persistence.faction_models import AcquaintanceRecord as Known
from livingworld.infrastructure.persistence.faction_models import (
    CharacterAvatarRecord as Avatar,
)
from livingworld.infrastructure.persistence.faction_models import (
    FactionMemberRecord as Member,
)
from livingworld.infrastructure.persistence.faction_models import (
    FactionRecord as Faction,
)
from livingworld.infrastructure.persistence.models import (
    WorldContentImportRecord as Import,
)
from livingworld.infrastructure.persistence.models import (
    WorldRecord as World,
)
from livingworld.infrastructure.persistence.world_content import _load
from livingworld.infrastructure.persistence.world_cover_models import WorldCoverImageRecord as Image


class FactionError(ValueError):
    pass


async def _characters(session, world):
    imports = (
        await session.scalars(
            select(Import).where(Import.world_id == world, Import.kind == "character")
        )
    ).all()
    by_id = {row.import_id: row for row in imports}
    current = {row.replaces_import_id for row in imports if row.replaces_import_id}
    result = {}
    for row in imports:
        if row.import_id in current or row.removed_at is not None:
            continue
        origin, seen = row, set()
        while origin.replaces_import_id is not None:
            if origin.import_id in seen or origin.replaces_import_id not in by_id:
                raise FactionError("faction_character_lineage_invalid")
            seen.add(origin.import_id)
            origin = by_id[origin.replaces_import_id]
        cards = [item for item in _load(row).contents if isinstance(item, CharacterDefinition)]
        if len(cards) == 1:
            result[origin.import_id] = {
                "root_import_id": str(origin.import_id),
                "current_import_id": str(row.import_id),
                "character_id": str(uuid5(origin.import_id, "livingworld:chat-character:v1")),
                "name": cards[0].display_name,
            }
    return result


async def _roots(session, world, allowed):
    roots = (
        await session.scalars(
            select(Import.import_id).where(
                Import.world_id == world,
                Import.kind == "character",
                Import.replaces_import_id.is_(None),
            )
        )
    ).all()
    from livingworld.infrastructure.persistence.authored_lifecycle import removed_character_roots

    removed = await removed_character_roots(session, world)
    return {
        uuid5(root, "livingworld:chat-character:v1"): root
        for root in roots
        if root not in removed and uuid5(root, "livingworld:chat-character:v1") in allowed
    }


async def known_pair(session, world: UUID, first: UUID, second: UUID) -> bool:
    """An authored acquaintance survives leaving; parent membership never implies it."""
    if first == second:
        return False
    roots = await _roots(session, world, {first, second})
    if len(roots) != 2:
        return False
    left, right = sorted(roots.values())
    return await session.get(Known, (world, left, right)) is not None


async def known_pairs(session, world: UUID, allowed: set[UUID], limit: int = 64):
    """Bounded authored acquaintance IDs for an already authorized Director batch."""
    roots = await _roots(session, world, allowed)
    if not roots:
        return []
    rows = (
        await session.scalars(
            select(Known)
            .where(
                Known.world_id == world,
                Known.first_root_import_id.in_(roots.values()),
                Known.second_root_import_id.in_(roots.values()),
            )
            .order_by(Known.first_root_import_id, Known.second_root_import_id)
            .limit(limit)
        )
    ).all()
    pairs = [
        sorted(
            (
                uuid5(row.first_root_import_id, "livingworld:chat-character:v1"),
                uuid5(row.second_root_import_id, "livingworld:chat-character:v1"),
            )
        )
        for row in rows
    ]
    return [
        {"first_character_id": str(first), "second_character_id": str(second)}
        for first, second in pairs
    ]


class SqlAlchemyFactionStore:
    def __init__(self, sessions):
        self.sessions = sessions

    async def context_for_character(self, owner):
        """Only this speaker's authored affiliations and acquaintances, bounded to 4 KiB."""
        world = owner.world_id.value
        async with self.sessions() as session:
            characters = await _characters(session, world)
            root = next(
                (
                    key
                    for key in characters
                    if uuid5(key, "livingworld:chat-character:v1") == owner.value
                ),
                None,
            )
            if root is None:
                return {"factions": [], "known_people": []}
            rows = (
                await session.execute(
                    select(Member.faction_id, Member.root_import_id).where(Member.world_id == world)
                )
            ).all()
            owned = {faction for faction, member in rows if member == root}
            result = {"factions": [], "known_people": []}

            def fits():
                return len(json.dumps(result, ensure_ascii=False).encode("utf-8")) <= 4096

            for faction_id in sorted(owned):
                faction = await session.get(Faction, (world, faction_id))
                if faction is None:
                    continue
                peers = sorted(
                    {
                        characters[member]["name"]
                        for candidate, member in rows
                        if candidate == faction_id and member in characters and member != root
                    }
                )[:16]
                result["factions"].append({"faction": faction.name, "known_members": peers})
                if not fits():
                    result["factions"].pop()
                    break
                if len(result["factions"]) == 8:
                    break
            pairs = (
                await session.scalars(
                    select(Known)
                    .where(
                        Known.world_id == world,
                        or_(
                            Known.first_root_import_id == root, Known.second_root_import_id == root
                        ),
                    )
                    .order_by(Known.first_root_import_id, Known.second_root_import_id)
                )
            ).all()
            peer_ids = {
                pair.second_root_import_id
                if pair.first_root_import_id == root
                else pair.first_root_import_id
                for pair in pairs
            }
            for peer in sorted(peer_ids):
                if peer not in characters:
                    continue
                result["known_people"].append(
                    {
                        "character_id": characters[peer]["character_id"],
                        "name": characters[peer]["name"],
                    }
                )
                if not fits():
                    result["known_people"].pop()
                    break
                if len(result["known_people"]) == 24:
                    break
            return result

    async def snapshot(self, world):
        async with self.sessions() as session:
            if await session.get(World, world) is None:
                raise FactionError("world_not_found")
            characters = await _characters(session, world)
            factions = (
                await session.scalars(
                    select(Faction)
                    .where(Faction.world_id == world)
                    .order_by(Faction.name, Faction.faction_id)
                )
            ).all()
            members = (await session.scalars(select(Member).where(Member.world_id == world))).all()
            avatars = (await session.scalars(select(Avatar).where(Avatar.world_id == world))).all()
            for avatar in avatars:
                if avatar.root_import_id in characters:
                    characters[avatar.root_import_id]["avatar_digest"] = avatar.digest
            for character in characters.values():
                character.setdefault("avatar_digest", None)
            memberships = [
                {"faction_id": str(row.faction_id), "root_import_id": str(row.root_import_id)}
                for row in members
                if row.root_import_id in characters
            ]
            grouped = defaultdict(set)
            for membership in memberships:
                grouped[membership["faction_id"]].add(membership["root_import_id"])
            acquaintances = (
                await session.scalars(select(Known).where(Known.world_id == world))
            ).all()
            edges = {}
            for pair in acquaintances:
                if (
                    pair.first_root_import_id not in characters
                    or pair.second_root_import_id not in characters
                ):
                    continue
                first, second = str(pair.first_root_import_id), str(pair.second_root_import_id)
                edges[(first, second)] = [
                    faction
                    for faction, roots in grouped.items()
                    if first in roots and second in roots
                ]
            return {
                "factions": [
                    {
                        "faction_id": str(row.faction_id),
                        "parent_id": str(row.parent_id) if row.parent_id else None,
                        "name": row.name,
                    }
                    for row in factions
                ],
                "characters": list(characters.values()),
                "memberships": memberships,
                "connections": [
                    {
                        "first_root_import_id": pair[0],
                        "second_root_import_id": pair[1],
                        "faction_ids": origins,
                    }
                    for pair, origins in sorted(edges.items())
                ],
            }

    async def _write(self, session):
        await session.begin()
        await session.connection(execution_options={"livingworld_write_intent": True})

    async def _require_root(self, session, world, root):
        if root not in await _characters(session, world):
            raise FactionError("faction_character_not_found")

    async def create(self, world, name, parent):
        label = name.strip()
        if not label or len(label) > 120:
            raise FactionError("faction_name_invalid")
        async with self.sessions() as session:
            await self._write(session)
            if await session.get(World, world) is None:
                raise FactionError("world_not_found")
            if parent and await session.get(Faction, (world, parent)) is None:
                raise FactionError("faction_parent_not_found")
            if await self._name_exists(session, world, parent, label):
                raise FactionError("faction_name_taken")
            identity = uuid4()
            session.add(Faction(world_id=world, faction_id=identity, parent_id=parent, name=label))
            await session.commit()
            return identity

    async def _name_exists(self, session, world, parent, name, exclude=None):
        siblings = (
            await session.scalars(
                select(Faction).where(Faction.world_id == world, Faction.parent_id == parent)
            )
        ).all()
        return any(
            row.faction_id != exclude and row.name.casefold() == name.casefold() for row in siblings
        )

    async def edit(self, world, identity, name, parent):
        label = name.strip()
        if not label or len(label) > 120:
            raise FactionError("faction_name_invalid")
        async with self.sessions() as session:
            await self._write(session)
            row = await session.get(Faction, (world, identity))
            if row is None:
                raise FactionError("faction_not_found")
            seen = {identity}
            cursor = parent
            while cursor is not None:
                if cursor in seen:
                    raise FactionError("faction_cycle")
                seen.add(cursor)
                ancestor = await session.get(Faction, (world, cursor))
                if ancestor is None:
                    raise FactionError("faction_parent_not_found")
                cursor = ancestor.parent_id
            if await self._name_exists(session, world, parent, label, identity):
                raise FactionError("faction_name_taken")
            row.name, row.parent_id = label, parent
            await session.commit()

    async def remove(self, world, identity):
        async with self.sessions() as session:
            await self._write(session)
            if await session.get(Faction, (world, identity)) is None:
                raise FactionError("faction_not_found")
            child = await session.scalar(
                select(Faction.faction_id)
                .where(Faction.world_id == world, Faction.parent_id == identity)
                .limit(1)
            )
            member = await session.scalar(
                select(Member.root_import_id)
                .where(Member.world_id == world, Member.faction_id == identity)
                .limit(1)
            )
            if child or member:
                raise FactionError("faction_not_empty")
            await session.execute(
                delete(Faction).where(Faction.world_id == world, Faction.faction_id == identity)
            )
            await session.commit()

    async def membership(self, world, identity, root, enabled):
        async with self.sessions() as session:
            await self._write(session)
            if await session.get(Faction, (world, identity)) is None:
                raise FactionError("faction_not_found")
            await self._require_root(session, world, root)
            row = await session.get(Member, (world, identity, root))
            if enabled:
                peers = (
                    await session.scalars(
                        select(Member.root_import_id).where(
                            Member.world_id == world,
                            Member.faction_id == identity,
                            Member.root_import_id != root,
                        )
                    )
                ).all()
                for peer in peers:
                    first, second = sorted((root, peer))
                    if await session.get(Known, (world, first, second)) is None:
                        session.add(
                            Known(
                                world_id=world,
                                first_root_import_id=first,
                                second_root_import_id=second,
                                source_faction_id=identity,
                            )
                        )
                if row is None:
                    session.add(Member(world_id=world, faction_id=identity, root_import_id=root))
            elif row is not None:
                await session.delete(row)
            await session.commit()

    async def avatar(self, world, root, digest):
        async with self.sessions() as session:
            await self._write(session)
            await self._require_root(session, world, root)
            if digest and await session.get(Image, (world, digest)) is None:
                raise FactionError("faction_avatar_not_found")
            row = await session.get(Avatar, (world, root))
            if digest is None and row:
                await session.delete(row)
            elif digest and row:
                row.digest = digest
            elif digest:
                session.add(Avatar(world_id=world, root_import_id=root, digest=digest))
            await session.commit()
