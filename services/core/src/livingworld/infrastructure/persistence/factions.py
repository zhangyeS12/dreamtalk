"""Author-edited, world-local factions; direct co-membership means acquaintance."""

import json
from collections import defaultdict
from unicodedata import normalize
from uuid import UUID, uuid4, uuid5

from sqlalchemy import LargeBinary, case, cast, delete, func, or_, select, true

from livingworld.infrastructure.persistence.character_card_bindings import (
    CharacterCardBindingRecord,
)
from livingworld.infrastructure.persistence.encounter_models import (
    EncounterCandidateRecord as Meeting,
)
from livingworld.infrastructure.persistence.faction_models import (
    AcquaintanceFactionSourceRecord as Source,
)
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
    ChatParticipantRecord,
)
from livingworld.infrastructure.persistence.models import (
    WorldContentImportRecord as Import,
)
from livingworld.infrastructure.persistence.models import (
    WorldRecord as World,
)
from livingworld.infrastructure.persistence.world_cover_models import WorldCoverImageRecord as Image


class FactionError(ValueError):
    pass


def _character_metadata_statement(world, roots=None):
    columns = (Import.import_id, Import.replaces_import_id, Import.removed_at)
    statement = select(*columns).where(Import.world_id == world, Import.kind == "character")
    if roots is None:
        return statement
    lineage = statement.where(Import.import_id.in_(roots), Import.replaces_import_id.is_(None)).cte(
        "social_character_lineage", recursive=True
    )
    lineage = lineage.union_all(
        select(*columns)
        .join(lineage, Import.replaces_import_id == lineage.c.import_id)
        .where(Import.world_id == world, Import.kind == "character")
    )
    return select(lineage)


def _character_names_statement(world, identities):
    safe_snapshot = case((func.json_valid(Import.snapshot_json), Import.snapshot_json), else_="[]")
    parts = func.json_each(safe_snapshot).table_valued("key", "value")
    safe_part = case((func.json_valid(parts.c.value), parts.c.value), else_="{}")
    name = func.json_extract(safe_part, "$.data.display_name")
    bounded_name = case((func.length(cast(name, LargeBinary)) <= 4096, name), else_=None)
    return (
        select(Import.import_id, func.count(), func.max(bounded_name))
        .select_from(Import)
        .join(parts, true())
        .where(
            Import.world_id == world,
            Import.kind == "character",
            Import.import_id.in_(identities),
            Import.removed_at.is_(None),
            func.json_extract(safe_part, "$.kind") == "character_definition",
        )
        .group_by(Import.import_id)
    )


async def _characters(session, world, roots=None):
    """Project current names, never deserialize card bodies or historic snapshots."""
    if roots is None:
        imports = (await session.execute(_character_metadata_statement(world))).all()
    else:
        imports = []
        root_ids = sorted(roots)
        # Follow only the requested stable roots through their replacement chains.
        # Bound SQL bind counts as the acquaintance graph grows.
        for offset in range(0, len(root_ids), 256):
            statement = _character_metadata_statement(world, root_ids[offset : offset + 256])
            imports.extend((await session.execute(statement)).all())
    by_id = {row.import_id: row for row in imports}
    current = {row.replaces_import_id for row in imports if row.replaces_import_id}
    selected = {}
    for row in imports:
        if row.import_id in current or row.removed_at is not None:
            continue
        origin, seen = row, set()
        while origin.replaces_import_id is not None:
            if origin.import_id in seen or origin.replaces_import_id not in by_id:
                raise FactionError("faction_character_lineage_invalid")
            seen.add(origin.import_id)
            origin = by_id[origin.replaces_import_id]
        if origin.removed_at is None:
            selected[row.import_id] = origin.import_id
    result = {}
    identities = list(selected)
    for offset in range(0, len(identities), 256):
        names = await session.execute(
            _character_names_statement(world, identities[offset : offset + 256])
        )
        for identity, count, display_name in names:
            if count != 1 or not isinstance(display_name, str) or not display_name.strip():
                continue
            root = selected[identity]
            result[root] = {
                "root_import_id": str(root),
                "current_import_id": str(identity),
                "character_id": str(uuid5(root, "livingworld:chat-character:v1")),
                "name": display_name,
            }
    return result


async def _runtime_roots(session, world, identities):
    """Resolve existing stable mappings without loading character definitions."""
    identities = set(identities)
    result, mapped = {}, defaultdict(set)
    ordered = sorted(identities)
    for offset in range(0, len(ordered), 256):
        batch = ordered[offset : offset + 256]
        bindings = select(
            CharacterCardBindingRecord.character_id, CharacterCardBindingRecord.root_import_id
        ).where(
            CharacterCardBindingRecord.world_id == world,
            CharacterCardBindingRecord.character_id.in_(batch),
        )
        participants = select(
            ChatParticipantRecord.character_id, ChatParticipantRecord.root_import_id
        ).where(
            ChatParticipantRecord.world_id == world, ChatParticipantRecord.character_id.in_(batch)
        )
        for identity, root in await session.execute(bindings.union(participants)):
            mapped[identity].add(root)
    for identity, roots in mapped.items():
        if len(roots) == 1:
            root = next(iter(roots))
            if uuid5(root, "livingworld:chat-character:v1") == identity:
                result[identity] = root
    missing = identities - mapped.keys()
    if missing:
        # Compatibility for authored identities predating the binding table.
        roots = await session.scalars(
            select(Import.import_id).where(
                Import.world_id == world,
                Import.kind == "character",
                Import.replaces_import_id.is_(None),
            )
        )
        for root in roots:
            identity = uuid5(root, "livingworld:chat-character:v1")
            if identity in missing:
                result[identity] = root
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
    """Retained faction bases or a completed encounter; never mere co-location."""
    if first == second:
        return False
    roots = await _roots(session, world, {first, second})
    if len(roots) != 2:
        return False
    left, right = sorted(roots.values())
    if await session.get(Known, (world, left, right)) is not None:
        return True
    first, second = sorted((first, second))
    return (
        await session.scalar(
            _meeting_query(world, {first, second})
            .where(Meeting.first_character_id == first, Meeting.second_character_id == second)
            .limit(1)
        )
        is not None
    )


def _meeting_query(world, allowed, owner=None):
    # "finished" is committed in the Kernel UoW together with CharactersMet v1.
    # Read only participant IDs, never proposals, observations or private history text.
    query = (
        select(Meeting.first_character_id, Meeting.second_character_id)
        .where(
            Meeting.world_id == world,
            Meeting.state == "finished",
            Meeting.first_character_id.in_(allowed),
            Meeting.second_character_id.in_(allowed),
        )
        .distinct()
        .order_by(Meeting.first_character_id, Meeting.second_character_id)
    )
    if owner is not None:
        query = query.where(
            or_(Meeting.first_character_id == owner, Meeting.second_character_id == owner)
        )
    return query


async def known_pairs(session, world: UUID, allowed: set[UUID], limit: int = 64):
    """Bounded acquaintance IDs for an already authorized Director batch."""
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
    meetings = (await session.execute(_meeting_query(world, roots).limit(limit))).all()
    pairs = dict.fromkeys(tuple(pair) for pair in meetings)
    for row in rows:
        pair = tuple(
            sorted(
                (
                    uuid5(row.first_root_import_id, "livingworld:chat-character:v1"),
                    uuid5(row.second_root_import_id, "livingworld:chat-character:v1"),
                )
            )
        )
        if len(pairs) < limit:
            pairs.setdefault(pair, None)
    return [
        {"first_character_id": str(first), "second_character_id": str(second)}
        for first, second in pairs
    ]


class SqlAlchemyFactionStore:
    def __init__(self, sessions):
        self.sessions = sessions

    async def context_for_character(
        self, owner, *, preferred_character_ids=(), recent_character_ids=(), query_texts=()
    ):
        """Permission-first identity projection, ranked for this authorized dialogue."""
        world = owner.world_id.value
        result = {"factions": [], "known_people": []}
        async with self.sessions() as session:
            owner_roots = await _runtime_roots(session, world, {owner.value})
            root = owner_roots.get(owner.value)
            if root is None:
                return result
            pairs = (
                await session.execute(
                    select(Known.first_root_import_id, Known.second_root_import_id).where(
                        Known.world_id == world,
                        or_(
                            Known.first_root_import_id == root, Known.second_root_import_id == root
                        ),
                    )
                )
            ).all()
            peer_ids = {second if first == root else first for first, second in pairs}
            # Finished encounters are a canonical independent acquaintance basis.
            # The owner predicate precedes reading IDs; no private event text is read.
            meetings = await session.execute(
                select(Meeting.first_character_id, Meeting.second_character_id)
                .where(
                    Meeting.world_id == world,
                    Meeting.state == "finished",
                    or_(
                        Meeting.first_character_id == owner.value,
                        Meeting.second_character_id == owner.value,
                    ),
                )
                .distinct()
            )
            met_ids = {second if first == owner.value else first for first, second in meetings}
            peer_ids.update((await _runtime_roots(session, world, met_ids)).values())
            characters = await _characters(session, world, peer_ids | {root})
            if root not in characters:
                return result
            peer_ids.intersection_update(characters)
            peer_ids.discard(root)

            def positions(identities):
                return {
                    item.value: index
                    for index, item in reversed(list(enumerate(identities)))
                    if item.world_id == owner.world_id
                }

            preferred = positions(preferred_character_ids)
            recent = positions(recent_character_ids)
            # Builders supply only their already authorized, byte-bounded
            # transcript; preserve complete recent messages when matching names.
            queries = [normalize("NFKC", text).casefold() for text in query_texts[:8]]
            priorities = {}

            def rank(peer):
                if peer in priorities:
                    return priorities[peer]
                person = characters[peer]
                identity = UUID(person["character_id"])
                name = normalize("NFKC", person["name"]).casefold()
                mention = next((index for index, text in enumerate(queries) if name in text), None)
                if identity in preferred:
                    priority = (
                        0,
                        mention if mention is not None else len(queries),
                        recent.get(identity, len(recent)),
                        preferred[identity],
                    )
                elif mention is not None:
                    priority = (1, mention, 0, 0)
                elif identity in recent:
                    priority = (2, recent[identity], 0, 0)
                else:
                    priority = (3, 0, 0, 0)
                priorities[peer] = (*priority, name, str(peer))
                return priorities[peer]

            def fits():
                return len(json.dumps(result, ensure_ascii=False).encode("utf-8")) <= 4096

            for peer in sorted(peer_ids, key=rank):
                person = characters[peer]
                result["known_people"].append(
                    {"character_id": person["character_id"], "name": person["name"]}
                )
                if not fits():
                    result["known_people"].pop()
                    continue
                if len(result["known_people"]) == 24:
                    break

            owned = select(Member.faction_id).where(
                Member.world_id == world, Member.root_import_id == root
            )
            factions = (
                await session.execute(
                    select(Faction.faction_id, Faction.name).where(
                        Faction.world_id == world, Faction.faction_id.in_(owned)
                    )
                )
            ).all()
            members = (
                await session.execute(
                    select(Member.faction_id, Member.root_import_id).where(
                        Member.world_id == world,
                        Member.faction_id.in_(owned),
                        Member.root_import_id != root,
                    )
                )
            ).all()
            grouped = defaultdict(set)
            for faction, member in members:
                if member in peer_ids:
                    grouped[faction].add(member)

            def faction_rank(faction):
                priorities = [rank(peer)[:2] for peer in grouped[faction.faction_id]]
                return (
                    min(priorities, default=(3, 0)),
                    faction.name.casefold(),
                    str(faction.faction_id),
                )

            for faction in sorted(factions, key=faction_rank):
                entry = {"faction": faction.name, "known_members": []}
                result["factions"].append(entry)
                if not fits():
                    result["factions"].pop()
                    continue
                for peer in sorted(grouped[faction.faction_id], key=rank):
                    name = characters[peer]["name"]
                    if name in entry["known_members"]:
                        continue
                    entry["known_members"].append(name)
                    if not fits():
                        entry["known_members"].pop()
                        continue
                    if len(entry["known_members"]) == 16:
                        break
                if len(result["factions"]) == 8:
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
            runtime_roots = {
                UUID(person["character_id"]): key for key, person in characters.items()
            }
            meetings = await session.execute(_meeting_query(world, runtime_roots))
            for first_id, second_id in meetings:
                first, second = sorted(
                    (str(runtime_roots[first_id]), str(runtime_roots[second_id]))
                )
                edges.setdefault(
                    (first, second),
                    [
                        faction
                        for faction, roots in grouped.items()
                        if first in roots and second in roots
                    ],
                )
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

    async def membership(self, world, identity, root, enabled, *, cut_contacts=False):
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
                    if await session.get(Source, (world, first, second, identity)) is None:
                        session.add(
                            Source(
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
                if cut_contacts:
                    await self._cut_faction_contacts(session, world, identity, root)
            await session.commit()

    async def _cut_faction_contacts(self, session, world, identity, root):
        """Revoke just this faction's bases, atomically with leaving its membership."""
        actor_pairs = or_(Source.first_root_import_id == root, Source.second_root_import_id == root)
        revoked = (
            await session.execute(
                select(Source.first_root_import_id, Source.second_root_import_id).where(
                    Source.world_id == world, Source.source_faction_id == identity, actor_pairs
                )
            )
        ).all()
        await session.execute(
            delete(Source).where(
                Source.world_id == world, Source.source_faction_id == identity, actor_pairs
            )
        )
        remaining = (
            await session.scalars(
                select(Source)
                .where(Source.world_id == world, actor_pairs)
                .order_by(Source.source_faction_id)
            )
        ).all()
        origins = {
            (source.first_root_import_id, source.second_root_import_id): source.source_faction_id
            for source in remaining
        }
        for first, second in revoked:
            pair = await session.get(Known, (world, first, second))
            if pair is None:
                continue
            origin = origins.get((first, second))
            if origin is None:
                await session.delete(pair)
            else:
                pair.source_faction_id = origin
        # Canonical encounters are read independently and never revoked here.

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
