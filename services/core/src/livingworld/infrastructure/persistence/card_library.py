"""Atomic reviewed templates and image namespaces; world instances keep their own graphs."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from livingworld.application.card_library import LibraryCard
from livingworld.application.content import ContentConflictError, ContentDraft
from livingworld.application.errors import EntityNotFoundError
from livingworld.domain.content.identifiers import ContentAssetId, RawImportId
from livingworld.domain.content.serialization import deserialize_content, serialize_content
from livingworld.infrastructure.persistence.card_library_models import (
    CardLibraryImageRecord as Image,
)
from livingworld.infrastructure.persistence.card_library_models import CardLibraryRecord as Card
from livingworld.infrastructure.persistence.card_library_models import (
    CardLibraryWorldRecord as Link,
)
from livingworld.infrastructure.persistence.card_library_models import (
    CardPackMemberRecord as Member,
)
from livingworld.infrastructure.persistence.card_library_models import CardPackRecord as Pack
from livingworld.infrastructure.persistence.card_packs import CardPackStore
from livingworld.infrastructure.persistence.content_repository import (
    SqlAlchemyContentRepository,
    save_content_draft,
)
from livingworld.infrastructure.persistence.models import WorldContentImportRecord as Imported


class CardLibraryStore:
    def __init__(self, sessions):
        self._sessions = sessions
        self._contents = SqlAlchemyContentRepository(sessions)

    async def find(self, card_id):
        async with self._sessions() as session:
            row = await session.get(Card, card_id)
        if row is None:
            return None
        draft = row.draft_json
        assets = [
            await self._contents.load_asset(ContentAssetId(UUID(value)))
            for value in draft["assets"]
        ]
        raws = [
            await self._contents.load_raw_import(RawImportId(UUID(value)))
            for value in draft["raw_imports"]
        ]
        if any(value is None for value in assets + raws):
            raise EntityNotFoundError("card_library_source_missing")
        return LibraryCard(
            row.card_id,
            row.revision,
            row.reviewed_hash,
            ContentDraft(
                contents=tuple(deserialize_content(value) for value in draft["contents"]),
                assets=tuple(value for value in assets if value is not None),
                raw_imports=tuple(value for value in raws if value is not None),
            ),
            row.design,
        )

    async def load(self, card_id):
        result = await self.find(card_id)
        if result is None:
            raise EntityNotFoundError("card_library_not_found")
        return result

    async def remove(self, card_id, revision):
        async with self._sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            row = await session.get(Card, card_id)
            removed = row is not None
            if row is not None:
                if row.revision != revision:
                    raise ContentConflictError("card_library_changed")
                pack_ids = list(
                    await session.scalars(select(Member.pack_id).where(Member.card_id == card_id))
                )
                await session.delete(row)
                await session.flush()  # FK cascades remove only template links and image metadata.
                for pack_id in pack_ids:
                    pack = await session.get(Pack, pack_id)
                    if pack is not None:
                        pack.revision += 1
                    members = await session.scalars(
                        select(Member).where(Member.pack_id == pack_id).order_by(Member.position)
                    )
                    for index, member in enumerate(members):
                        member.position = index
        # World copies and immutable content/assets have independent ownership.
        return {"removed": removed, "packs": await CardPackStore(self._sessions).list()}

    async def save(self, card, revision, images=()):
        try:
            async with self._sessions() as session, session.begin():
                await session.connection(execution_options={"livingworld_write_intent": True})
                row = await session.get(Card, card.card_id)
                if row is not None and row.reviewed_hash == card.reviewed_hash:
                    return
                if (row.revision if row else 0) != revision:
                    raise ContentConflictError("card_library_changed")
                await save_content_draft(
                    session, card.draft, {root.content_id: None for root in card.contents}
                )
                if row is None:
                    row = Card(card_id=card.card_id, created_at=datetime.now(UTC))
                    session.add(row)
                row.name, row.revision, row.reviewed_hash, row.design = (
                    card.name,
                    card.revision,
                    card.reviewed_hash,
                    card.design,
                )
                row.draft_json = {
                    "contents": [serialize_content(root) for root in card.contents],
                    "assets": [str(x.asset_id.value) for x in card.draft.assets],
                    "raw_imports": [str(x.import_id.value) for x in card.draft.raw_imports],
                }
                await session.flush()
                for value in images:
                    if await session.get(Image, (card.card_id, value["digest"])) is None:
                        session.add(Image(card_id=card.card_id, **value))
        except IntegrityError:
            raise ContentConflictError("card_library_changed") from None

    async def list(self):
        async with self._sessions() as session:
            rows = (
                await session.scalars(select(Card).order_by(Card.created_at, Card.card_id))
            ).all()
            links = (
                await session.execute(
                    select(Link.card_id, Link.world_id)
                    .join(Imported, Link.import_id == Imported.import_id)
                    .where(Imported.removed_at.is_(None))
                )
            ).all()
            return [
                {
                    "card_id": str(row.card_id),
                    "name": row.name,
                    "revision": row.revision,
                    "design": row.design,
                    "world_ids": [str(world) for card, world in links if card == row.card_id],
                }
                for row in rows
            ]

    async def summary(self, card_id):
        return next(row for row in await self.list() if row["card_id"] == str(card_id))

    async def world_link(self, card_id, world_id):
        async with self._sessions() as session:
            link = await session.get(Link, (card_id, world_id.value))
            if link is None:
                return None
            imported = await session.get(Imported, link.import_id)
            return {
                "import_id": link.import_id,
                "active": imported is not None and imported.removed_at is None,
            }

    async def image(self, card_id, digest):
        async with self._sessions() as session:
            row = await session.get(Image, (card_id, digest))
            if row is None or await session.get(Card, card_id) is None:
                raise EntityNotFoundError("card_library_image_not_found")
            return {
                key: getattr(row, key)
                for key in ("digest", "size", "media_type", "width", "height")
            }

    async def add_image(self, card_id, value):
        async with self._sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            if await session.get(Card, card_id) is None:
                raise EntityNotFoundError("card_library_not_found")
            if await session.get(Image, (card_id, value["digest"])) is None:
                session.add(Image(card_id=card_id, **value))

    async def save_design(self, card_id, revision, design):
        async with self._sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            row = await session.get(Card, card_id)
            if row is None:
                raise EntityNotFoundError("card_library_not_found")
            if row.revision != revision:
                if row.design == design and row.revision == revision + 1:
                    return await self.summary(card_id)
                raise ContentConflictError("card_library_changed")
            row.design, row.revision = design, revision + 1
        return await self.summary(card_id)
