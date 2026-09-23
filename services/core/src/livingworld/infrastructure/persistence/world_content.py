"""Atomically persist imported content and an independent accepted world snapshot."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from livingworld.application.content import ContentConflictError
from livingworld.application.errors import EntityNotFoundError
from livingworld.application.imports import ImportPreview
from livingworld.application.world_content import AcceptedWorldContent
from livingworld.domain.content.serialization import (
    deserialize_content,
    parse_json,
    serialize_content,
    stable_json,
)
from livingworld.domain.identifiers import WorldId
from livingworld.infrastructure.persistence.content_repository import save_content_draft
from livingworld.infrastructure.persistence.models import WorldContentImportRecord, WorldRecord


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

    async def list_imports(self, world_id: WorldId) -> tuple[AcceptedWorldContent, ...]:
        await self.require_world(world_id)
        async with self._sessions() as session:
            rows = await session.scalars(
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
            return tuple(_load(row) for row in rows)

    async def find(self, import_id: UUID) -> AcceptedWorldContent | None:
        async with self._sessions() as session:
            row = await session.get(WorldContentImportRecord, import_id)
            return _load(row) if row is not None else None

    async def is_current(self, import_id: UUID) -> bool:
        async with self._sessions() as session:
            successor = await session.scalar(
                select(WorldContentImportRecord.import_id).where(
                    WorldContentImportRecord.replaces_import_id == import_id
                )
            )
            return successor is None

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
                if item.replaces_import_id is not None:
                    previous = await session.get(
                        WorldContentImportRecord, item.replaces_import_id
                    )
                    successor = await session.scalar(
                        select(WorldContentImportRecord.import_id).where(
                            WorldContentImportRecord.replaces_import_id
                            == item.replaces_import_id
                        )
                    )
                    if (
                        previous is None
                        or previous.world_id != item.world_id.value
                        or previous.kind != item.kind
                        or successor is not None
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
        except IntegrityError:
            raise ContentConflictError("Import persistence conflict") from None
        return item
