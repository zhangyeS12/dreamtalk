"""Current accepted sources and reviewed identity metadata; no canonical world writes."""

from uuid import UUID

from sqlalchemy import LargeBinary, case, cast, func, select, true, tuple_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import aliased

from livingworld.application.input_budget import bounded_text
from livingworld.application.player_persona import (
    PersonaReference,
    PersonaSourceChoice,
    PersonaSourcePage,
    PlayerPersonaDraft,
    PlayerPersonaError,
    PlayerPersonaSnapshot,
    identity_context,
)
from livingworld.domain.identifiers import CharacterId, PlayerId, WorldId
from livingworld.infrastructure.persistence.character_lineage import latest_character_import
from livingworld.infrastructure.persistence.models import (
    ChatParticipantRecord,
    WorldRecord,
)
from livingworld.infrastructure.persistence.models import (
    LocalPlayerBindingRecord as Binding,
)
from livingworld.infrastructure.persistence.models import (
    WorldContentImportRecord as Imported,
)
from livingworld.infrastructure.persistence.player_persona_models import PlayerPersonaRecord


def _sources_query(world: WorldId):
    parts = func.json_each(Imported.snapshot_json).table_valued("value")
    envelope = parts.c.value
    kind = func.json_extract(envelope, "$.kind")
    identity = func.json_extract(envelope, "$.data.content_id")
    title = case(
        (kind == "character_definition", func.json_extract(envelope, "$.data.display_name")),
        else_=func.json_extract(envelope, "$.data.title"),
    )
    content = case(
        (
            kind == "character_definition",
            func.coalesce(func.json_extract(envelope, "$.data.description"), "")
            + "\n"
            + func.coalesce(func.json_extract(envelope, "$.data.background"), ""),
        ),
        else_=func.json_extract(envelope, "$.data.content"),
    )
    successor = aliased(Imported)
    query = (
        select(
            Imported.import_id,
            Imported.reviewed_hash,
            Imported.kind,
            identity.label("content_id"),
            title.label("title"),
            func.substr(cast(content, LargeBinary), 1, 8192).label("content"),
            func.length(cast(content, LargeBinary)).label("content_bytes"),
        )
        .select_from(Imported)
        .join(parts, true())
        .where(
            Imported.world_id == world.value,
            Imported.removed_at.is_(None),
            ~select(successor.import_id)
            .where(
                successor.world_id == world.value,
                successor.replaces_import_id == Imported.import_id,
            )
            .exists(),
            ((kind == "character_definition") & (Imported.kind == "character"))
            | (
                (kind == "lore_entry")
                & (Imported.kind == "lorebook")
                & (func.json_extract(envelope, "$.data.enabled") == 1)
            ),
        )
    )
    return query, identity, title


async def _root(session: AsyncSession, world: WorldId, imported: UUID) -> UUID:
    seen: set[UUID] = set()
    current = await session.get(Imported, imported)
    while current is not None and current.world_id == world.value and current.kind == "character":
        if current.import_id in seen:
            break
        seen.add(current.import_id)
        if current.replaces_import_id is None:
            return current.import_id
        current = await session.get(Imported, current.replaces_import_id)
    raise PlayerPersonaError("persona_character_changed")


async def _choice(session, world: WorldId, row) -> PersonaSourceChoice:
    content = bytes(row.content or b"").decode("utf-8", errors="ignore")
    return PersonaSourceChoice(
        reference=PersonaReference(
            import_id=row.import_id,
            content_id=UUID(row.content_id),
            reviewed_hash=row.reviewed_hash,
        ),
        kind=row.kind,
        title=bounded_text(row.title or "未命名资料", 768),
        text=content,
        excerpt=row.content_bytes > 8192,
        root_import_id=await _root(session, world, row.import_id)
        if row.kind == "character"
        else None,
    )


async def _source(
    session: AsyncSession, world: WorldId, reference: PersonaReference
) -> PersonaSourceChoice:
    query, content_id, _ = _sources_query(world)
    row = (
        await session.execute(
            query.where(
                Imported.import_id == reference.import_id,
                content_id == reference.content_id.hex,
                Imported.reviewed_hash == reference.reviewed_hash,
            )
        )
    ).first()
    if row is None:
        raise PlayerPersonaError("persona_source_changed")
    return await _choice(session, world, row)


async def _player(session: AsyncSession, world: WorldId) -> UUID | None:
    if await session.get(WorldRecord, world.value) is None:
        raise PlayerPersonaError("world_not_found")
    binding = await session.get(Binding, world.value)
    return binding.player_id if binding else None


async def _validate(session: AsyncSession, world: WorldId, draft: PlayerPersonaDraft) -> str | None:
    source = await _source(session, world, draft.source) if draft.source else None
    for item in draft.recognitions:
        root = await _root(session, world, item.character_import_id)
        if root != item.character_import_id:
            raise PlayerPersonaError("persona_character_changed")
        current = await session.get(
            Imported, await latest_character_import(session, world.value, root)
        )
        if current is None or current.removed_at is not None:
            raise PlayerPersonaError("persona_character_changed")
        query, _, _ = _sources_query(world)
        row = (await session.execute(query.where(Imported.import_id == current.import_id))).first()
        if row is None:
            raise PlayerPersonaError("persona_character_changed")
        item.character_name = (row.title or "未命名角色")[:120]
    return source.title if source else None


async def _snapshot(session: AsyncSession, world: WorldId) -> PlayerPersonaSnapshot:
    player = await _player(session, world)
    row = await session.get(PlayerPersonaRecord, (world.value, player)) if player else None
    draft = PlayerPersonaDraft.model_validate_json(row.draft_json) if row else PlayerPersonaDraft()
    state = "original"
    if draft.source:
        try:
            await _source(session, world, draft.source)
            state = "current"
        except PlayerPersonaError:
            state = "changed"
    return PlayerPersonaSnapshot(
        player_id=player, revision=row.revision if row else 0, draft=draft, source_state=state
    )


async def read_player_persona(
    session: AsyncSession, world: WorldId, player: UUID, root: UUID
) -> dict[str, object] | None:
    """One recipient only; stale source authorization never enters a model input."""
    if await _player(session, world) != player:
        return None
    row = await session.get(PlayerPersonaRecord, (world.value, player))
    if row is None:
        return None
    draft = PlayerPersonaDraft.model_validate_json(row.draft_json)
    if not (draft.identity_name.strip() or draft.public_identity.strip() or draft.recognitions):
        return None
    if draft.source:
        try:
            await _source(session, world, draft.source)
        except PlayerPersonaError:
            return None
    return identity_context(draft, root, row.revision)


async def player_persona_stamp(session: AsyncSession, world: WorldId, player: UUID) -> str | None:
    """Small revocation marker; snapshots never copy every recipient's private facts."""
    snapshot = await _snapshot(session, world)
    if snapshot.player_id != player or snapshot.revision == 0:
        return None
    return f"{snapshot.revision}:{snapshot.source_state}"


class SqlAlchemyPlayerPersonaStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def snapshot(self, world: WorldId) -> PlayerPersonaSnapshot:
        async with self.sessions() as session:
            return await _snapshot(session, world)

    async def sources(
        self, world: WorldId, query: str, after: str | None, *, characters: bool = False
    ) -> PersonaSourcePage:
        async with self.sessions() as session:
            await _player(session, world)
            statement, content_id, title = _sources_query(world)
            if query.strip():
                # Literal substring, not SQL wildcard or automatic identity inference.
                statement = statement.where(
                    func.instr(func.lower(title), query.strip().lower()) > 0
                )
            if characters:
                statement = statement.where(Imported.kind == "character")
            if after:
                try:
                    imported, content = (UUID(part).hex for part in after.split(":"))
                except ValueError:
                    raise PlayerPersonaError("persona_cursor_invalid") from None
                statement = statement.where(
                    tuple_(Imported.import_id, content_id) > (UUID(imported), content)
                )
            rows = (
                await session.execute(statement.order_by(Imported.import_id, content_id).limit(33))
            ).all()
            selected = rows[:32]
            return PersonaSourcePage(
                items=[await _choice(session, world, row) for row in selected],
                next_after=f"{selected[-1].import_id.hex}:{selected[-1].content_id}"
                if len(rows) > 32
                else None,
            )

    async def validate(self, world: WorldId, draft: PlayerPersonaDraft) -> str | None:
        async with self.sessions() as session:
            return await _validate(session, world, draft)

    async def commit(
        self,
        world: WorldId,
        player: UUID,
        revision: int,
        draft: PlayerPersonaDraft,
        confirmation: UUID,
    ) -> PlayerPersonaSnapshot:
        async with self.sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            if await _player(session, world) != player:
                raise PlayerPersonaError("persona_player_changed")
            row = await session.get(PlayerPersonaRecord, (world.value, player))
            if row and row.confirmation_id == confirmation:
                return await _snapshot(session, world)
            if (row.revision if row else 0) != revision:
                raise PlayerPersonaError("persona_edit_conflict")
            await _validate(session, world, draft)
            if row is None:
                row = PlayerPersonaRecord(
                    world_id=world.value,
                    player_id=player,
                    revision=1,
                    draft_json=draft.model_dump_json(),
                    confirmation_id=confirmation,
                )
                session.add(row)
            else:
                row.revision += 1
                row.draft_json, row.confirmation_id = draft.model_dump_json(), confirmation
            await session.flush()
            return await _snapshot(session, world)

    async def confirmation(self, world: WorldId, confirmation: UUID) -> bool:
        async with self.sessions() as session:
            player = await _player(session, world)
            row = await session.get(PlayerPersonaRecord, (world.value, player)) if player else None
            return bool(row and row.confirmation_id == confirmation)

    async def context_for_character(
        self, world: WorldId, player: PlayerId, owner: CharacterId
    ) -> dict[str, object] | None:
        if owner.world_id != world:
            return None
        async with self.sessions() as session:
            roots = (
                await session.scalars(
                    select(ChatParticipantRecord.root_import_id)
                    .where(
                        ChatParticipantRecord.world_id == world.value,
                        ChatParticipantRecord.character_id == owner.value,
                    )
                    .distinct()
                    .limit(2)
                )
            ).all()
            if len(roots) != 1:
                return None
            root = roots[0]
            return await read_player_persona(session, world, player.value, root)
