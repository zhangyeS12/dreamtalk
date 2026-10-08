"""Atomically persist imported content and an independent accepted world snapshot."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from livingworld.application.content import ContentConflictError
from livingworld.application.errors import EntityNotFoundError
from livingworld.application.imports import ImportPreview
from livingworld.application.world_content import (
    AcceptedWorldContent,
    CommonLoreEntry,
    unchanged_lore_entry_pairs,
)
from livingworld.domain.content.models import CanonicalContent, LoreCollection, LoreEntry
from livingworld.domain.content.serialization import (
    deserialize_content,
    parse_json,
    serialize_content,
    stable_json,
)
from livingworld.domain.identifiers import WorldId
from livingworld.infrastructure.persistence.content_repository import save_content_draft
from livingworld.infrastructure.persistence.models import (
    ChatParticipantRecord,
    ChatReplyExecutionRecord,
    ChatTurnRecord,
    WorldCommonLoreRecord,
    WorldContentImportRecord,
    WorldRecord,
)


def _load(row: WorldContentImportRecord) -> AcceptedWorldContent:
    return AcceptedWorldContent(
        row.import_id,
        WorldId(row.world_id),
        row.reviewed_hash,
        row.kind,
        tuple(deserialize_content(value) for value in parse_json(row.snapshot_json)),
        row.replaces_import_id,
    )


class SqlAlchemyWorldContentStore:
    def __init__(self, sessions) -> None:
        self._sessions = sessions

    async def require_world(self, world_id: WorldId) -> None:
        async with self._sessions() as session:
            if await session.get(WorldRecord, world_id.value) is None:
                raise EntityNotFoundError("world_not_found")

    async def list_imports(
        self, world_id: WorldId, *, include_removed: bool = False
    ) -> tuple[AcceptedWorldContent, ...]:
        await self.require_world(world_id)
        async with self._sessions() as session:
            statement = (
                select(WorldContentImportRecord)
                .where(
                    WorldContentImportRecord.world_id == world_id.value,
                    ~WorldContentImportRecord.import_id.in_(
                        select(WorldContentImportRecord.replaces_import_id).where(
                            WorldContentImportRecord.replaces_import_id.is_not(None)
                        )
                    ),
                )
                .order_by(WorldContentImportRecord.accepted_at, WorldContentImportRecord.import_id)
            )
            if not include_removed:
                statement = statement.where(WorldContentImportRecord.removed_at.is_(None))
            rows = await session.scalars(statement)
            return tuple(_load(row) for row in rows)

    async def find(self, import_id: UUID) -> AcceptedWorldContent | None:
        async with self._sessions() as session:
            row = await session.get(WorldContentImportRecord, import_id)
            return _load(row) if row is not None else None

    async def is_current(self, import_id: UUID) -> bool:
        async with self._sessions() as session:
            imported = await session.get(WorldContentImportRecord, import_id)
            if imported is None or imported.removed_at is not None:
                return False
            successor = await session.scalar(
                select(WorldContentImportRecord.import_id).where(
                    WorldContentImportRecord.replaces_import_id == import_id
                )
            )
            return successor is None

    async def remove_character(self, world_id: WorldId, import_id: UUID) -> None:
        from livingworld.infrastructure.persistence.faction_models import (
            CharacterAvatarRecord,
            FactionMemberRecord,
        )

        async with self._sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            imported = await session.get(WorldContentImportRecord, import_id)
            if (
                imported is None
                or imported.world_id != world_id.value
                or imported.kind != "character"
            ):
                raise EntityNotFoundError("character_card_not_found")
            if imported.removed_at is not None:
                return  # Repeated removal never resurrects an older revision.
            successor = await session.scalar(
                select(WorldContentImportRecord.import_id).where(
                    WorldContentImportRecord.replaces_import_id == import_id,
                )
            )
            if successor is not None:
                raise ContentConflictError("character_card_changed")
            root, seen = imported, set()
            while root.replaces_import_id is not None:
                if root.import_id in seen:
                    raise ContentConflictError("character_card_changed")
                seen.add(root.import_id)
                root = await session.get(WorldContentImportRecord, root.replaces_import_id)
                if root is None or root.world_id != world_id.value or root.kind != "character":
                    raise ContentConflictError("character_card_changed")
            conversations = select(ChatParticipantRecord.conversation_id).where(
                ChatParticipantRecord.world_id == world_id.value,
                ChatParticipantRecord.root_import_id == root.import_id,
            )
            running = await session.scalar(
                select(ChatReplyExecutionRecord.turn_id)
                .join(
                    ChatTurnRecord,
                    (ChatTurnRecord.world_id == ChatReplyExecutionRecord.world_id)
                    & (ChatTurnRecord.turn_id == ChatReplyExecutionRecord.turn_id),
                )
                .where(
                    ChatTurnRecord.world_id == world_id.value,
                    ChatTurnRecord.conversation_id.in_(conversations),
                    ChatReplyExecutionRecord.state == "running",
                )
                .limit(1)
            )
            if running is not None:
                raise ContentConflictError("character_card_reply_running")
            imported.removed_at = datetime.now(UTC)
            for record in (FactionMemberRecord, CharacterAvatarRecord):
                await session.execute(
                    delete(record).where(
                        record.world_id == world_id.value,
                        record.root_import_id == root.import_id,
                    )
                )
            # Keep canonical Character/State, messages, memories, observations,
            # acquaintances and immutable imports; no physical departure is forged.

    async def list_common_lore(self, world_id: WorldId) -> tuple[CommonLoreEntry, ...]:
        """Only explicitly exposed entries from current imports in this world."""
        async with self._sessions() as session:
            rows = (
                await session.execute(
                    select(WorldCommonLoreRecord, WorldContentImportRecord)
                    .join(
                        WorldContentImportRecord,
                        WorldCommonLoreRecord.import_id == WorldContentImportRecord.import_id,
                    )
                    .where(
                        WorldCommonLoreRecord.world_id == world_id.value,
                        WorldContentImportRecord.world_id == world_id.value,
                        WorldContentImportRecord.removed_at.is_(None),
                        ~WorldContentImportRecord.import_id.in_(
                            select(WorldContentImportRecord.replaces_import_id).where(
                                WorldContentImportRecord.replaces_import_id.is_not(None)
                            )
                        ),
                    )
                    .order_by(WorldCommonLoreRecord.import_id, WorldCommonLoreRecord.entry_id)
                )
            ).all()
            decoded: dict[UUID, dict[UUID, CanonicalContent]] = {}
            results = []
            for exposure, imported in rows:
                if imported.import_id not in decoded:
                    decoded[imported.import_id] = {
                        item.content_id.value: item for item in _load(imported).contents
                    }
                entries = decoded[imported.import_id]
                if isinstance(entry := entries.get(exposure.entry_id), LoreEntry):
                    collection = (
                        entries.get(entry.collection_id.value) if entry.collection_id else None
                    )
                    results.append(
                        CommonLoreEntry(
                            imported.import_id,
                            entry,
                            collection if isinstance(collection, LoreCollection) else None,
                        )
                    )
            return tuple(results)

    async def set_common_lore(
        self, world_id: WorldId, import_id: UUID, entry_id: UUID, common: bool
    ) -> None:
        async with self._sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            imported = await session.get(WorldContentImportRecord, import_id)
            successor = await session.scalar(
                select(WorldContentImportRecord.import_id).where(
                    WorldContentImportRecord.replaces_import_id == import_id
                )
            )
            entry = (
                next(
                    (
                        item
                        for item in _load(imported).contents
                        if isinstance(item, LoreEntry) and item.content_id.value == entry_id
                    ),
                    None,
                )
                if imported is not None
                and imported.world_id == world_id.value
                and imported.kind == "lorebook"
                else None
            )
            if (
                imported is None
                or imported.world_id != world_id.value
                or imported.kind != "lorebook"
                or successor is not None
                or imported.removed_at is not None
                or entry is None
                or (common and not entry.enabled)
            ):
                raise EntityNotFoundError("current_lore_entry_not_found")
            key = (world_id.value, import_id, entry_id)
            if common:
                if await session.get(WorldCommonLoreRecord, key) is None:
                    session.add(
                        WorldCommonLoreRecord(
                            world_id=world_id.value, import_id=import_id, entry_id=entry_id
                        )
                    )
            else:
                await session.execute(
                    delete(WorldCommonLoreRecord).where(
                        WorldCommonLoreRecord.world_id == world_id.value,
                        WorldCommonLoreRecord.import_id == import_id,
                        WorldCommonLoreRecord.entry_id == entry_id,
                    )
                )

    async def accept(
        self, item: AcceptedWorldContent, preview: ImportPreview
    ) -> AcceptedWorldContent:
        if (
            item.reviewed_hash != preview.content.preview_hash
            or item.contents != preview.content.draft.contents
        ):
            raise ContentConflictError("Import preview mismatch")
        try:
            async with self._sessions() as session, session.begin():
                await session.connection(execution_options={"livingworld_write_intent": True})
                existing = await session.get(WorldContentImportRecord, item.import_id)
                if existing is not None:
                    if (
                        existing.world_id != item.world_id.value
                        or existing.reviewed_hash != item.reviewed_hash
                    ):
                        raise ContentConflictError("Import confirmation mismatch")
                    return _load(existing)
                if await session.get(WorldRecord, item.world_id.value) is None:
                    raise EntityNotFoundError("world_not_found")
                previous = None
                if item.replaces_import_id is not None:
                    previous = await session.get(WorldContentImportRecord, item.replaces_import_id)
                    successor = await session.scalar(
                        select(WorldContentImportRecord.import_id).where(
                            WorldContentImportRecord.replaces_import_id == item.replaces_import_id
                        )
                    )
                    if (
                        previous is None
                        or previous.world_id != item.world_id.value
                        or previous.kind != item.kind
                        or successor is not None
                        or previous.removed_at is not None
                    ):
                        raise ContentConflictError("Content replacement target is stale")
                await save_content_draft(
                    session,
                    preview.content.draft,
                    {root.content_id: None for root in item.contents},
                )
                session.add(
                    WorldContentImportRecord(
                        import_id=item.import_id,
                        replaces_import_id=item.replaces_import_id,
                        world_id=item.world_id.value,
                        reviewed_hash=item.reviewed_hash,
                        kind=item.kind,
                        snapshot_json=stable_json(
                            [serialize_content(root) for root in item.contents]
                        ),
                        accepted_at=datetime.now(UTC),
                    )
                )
                if previous is not None and item.kind == "lorebook":
                    # Read the last confirmed grants in the same serialized write
                    # transaction. Hiding during an open preview cannot be undone.
                    public_ids = set(
                        await session.scalars(
                            select(WorldCommonLoreRecord.entry_id).where(
                                WorldCommonLoreRecord.world_id == item.world_id.value,
                                WorldCommonLoreRecord.import_id == previous.import_id,
                            )
                        )
                    )
                    await session.flush()
                    for old_id, new_id in unchanged_lore_entry_pairs(_load(previous), item):
                        if old_id in public_ids:
                            session.add(
                                WorldCommonLoreRecord(
                                    world_id=item.world_id.value,
                                    import_id=item.import_id,
                                    entry_id=new_id,
                                )
                            )
        except IntegrityError:
            raise ContentConflictError("Import persistence conflict") from None
        return item
