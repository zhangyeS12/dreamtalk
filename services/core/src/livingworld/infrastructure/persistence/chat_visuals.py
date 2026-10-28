"""Persistence for world-scoped chat visual bindings."""

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from livingworld.application.chat_visuals import ChatCharacterExpression, ChatVisuals
from livingworld.application.errors import EntityNotFoundError
from livingworld.domain.identifiers import WorldId
from livingworld.infrastructure.persistence.chat_visual_models import (
    ChatCharacterBackgroundRecord,
    ChatCharacterExpressionRecord,
    ChatVisualBackgroundRecord,
)
from livingworld.infrastructure.persistence.models import WorldContentImportRecord, WorldRecord
from livingworld.infrastructure.persistence.world_cover_models import WorldCoverImageRecord


class SqlAlchemyChatVisualStore:
    def __init__(self, sessions):
        self._sessions = sessions

    async def _require_digest(self, session, world, digest):
        if digest is None:
            return
        exists = await session.scalar(
            select(WorldCoverImageRecord.digest).where(
                WorldCoverImageRecord.world_id == world.value,
                WorldCoverImageRecord.digest == digest,
            )
        )
        if exists is None:
            raise EntityNotFoundError("chat_visual_image_not_found")

    async def _require_world(self, session, world):
        exists = await session.scalar(
            select(WorldRecord.world_id).where(WorldRecord.world_id == world.value)
        )
        if exists is None:
            raise EntityNotFoundError("world_not_found")

    async def _require_root(self, session, world, root):
        exists = await session.scalar(
            select(WorldContentImportRecord.import_id).where(
                WorldContentImportRecord.world_id == world.value,
                WorldContentImportRecord.import_id == root,
                WorldContentImportRecord.kind == "character",
                WorldContentImportRecord.replaces_import_id.is_(None),
                WorldContentImportRecord.removed_at.is_(None),
            )
        )
        if exists is None:
            raise EntityNotFoundError("chat_visual_character_not_found")

    async def _load(self, session, world) -> ChatVisuals:
        common = await session.get(ChatVisualBackgroundRecord, world.value)
        backgrounds = await session.scalars(
            select(ChatCharacterBackgroundRecord).where(
                ChatCharacterBackgroundRecord.world_id == world.value
            )
        )
        expressions = await session.scalars(
            select(ChatCharacterExpressionRecord)
            .where(ChatCharacterExpressionRecord.world_id == world.value)
            .order_by(
                ChatCharacterExpressionRecord.root_import_id,
                ChatCharacterExpressionRecord.expression,
            )
        )
        return ChatVisuals(
            common_background_digest=common.common_digest if common else None,
            character_backgrounds={row.root_import_id: row.digest for row in backgrounds},
            expressions=tuple(
                ChatCharacterExpression(row.root_import_id, row.expression, row.digest)
                for row in expressions
            ),
        )

    async def load(self, world: WorldId) -> ChatVisuals:
        async with self._sessions() as session:
            if (
                await session.scalar(
                    select(WorldRecord.world_id).where(WorldRecord.world_id == world.value)
                )
                is None
            ):
                raise EntityNotFoundError("world_not_found")
            return await self._load(session, world)

    async def set_common_background(self, world: WorldId, digest: str | None) -> ChatVisuals:
        async with self._sessions() as session, session.begin():
            await self._require_world(session, world)
            await self._require_digest(session, world, digest)
            await session.execute(
                sqlite_insert(ChatVisualBackgroundRecord)
                .values(world_id=world.value, common_digest=digest)
                .on_conflict_do_update(
                    index_elements=[ChatVisualBackgroundRecord.world_id],
                    set_={"common_digest": digest},
                )
            )
            return await self._load(session, world)

    async def set_character_background(
        self, world: WorldId, root_import_id: UUID, digest: str | None
    ):
        async with self._sessions() as session, session.begin():
            await self._require_world(session, world)
            await self._require_root(session, world, root_import_id)
            await self._require_digest(session, world, digest)
            if digest is None:
                await session.execute(
                    delete(ChatCharacterBackgroundRecord).where(
                        ChatCharacterBackgroundRecord.world_id == world.value,
                        ChatCharacterBackgroundRecord.root_import_id == root_import_id,
                    )
                )
            else:
                await session.execute(
                    sqlite_insert(ChatCharacterBackgroundRecord)
                    .values(world_id=world.value, root_import_id=root_import_id, digest=digest)
                    .on_conflict_do_update(
                        index_elements=[
                            ChatCharacterBackgroundRecord.world_id,
                            ChatCharacterBackgroundRecord.root_import_id,
                        ],
                        set_={"digest": digest},
                    )
                )
            return await self._load(session, world)

    async def set_expression(self, world, root_import_id, expression, digest):
        async with self._sessions() as session, session.begin():
            await self._require_world(session, world)
            await self._require_root(session, world, root_import_id)
            await self._require_digest(session, world, digest)
            if digest is None:
                await session.execute(
                    delete(ChatCharacterExpressionRecord).where(
                        ChatCharacterExpressionRecord.world_id == world.value,
                        ChatCharacterExpressionRecord.root_import_id == root_import_id,
                        ChatCharacterExpressionRecord.expression == expression,
                    )
                )
            else:
                await session.execute(
                    sqlite_insert(ChatCharacterExpressionRecord)
                    .values(
                        world_id=world.value,
                        root_import_id=root_import_id,
                        expression=expression,
                        digest=digest,
                    )
                    .on_conflict_do_update(
                        index_elements=[
                            ChatCharacterExpressionRecord.world_id,
                            ChatCharacterExpressionRecord.root_import_id,
                            ChatCharacterExpressionRecord.expression,
                        ],
                        set_={"digest": digest},
                    )
                )
            return await self._load(session, world)
