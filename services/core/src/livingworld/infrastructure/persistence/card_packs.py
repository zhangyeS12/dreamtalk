"""Atomic foil-packet presentation and ordered memberships; no world mutation."""

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from livingworld.application.content import ContentConflictError
from livingworld.application.errors import EntityNotFoundError
from livingworld.infrastructure.persistence.card_library_models import (
    CardLibraryRecord as Card,
)
from livingworld.infrastructure.persistence.card_library_models import (
    CardPackImageRecord as Image,
)
from livingworld.infrastructure.persistence.card_library_models import (
    CardPackMemberRecord as Member,
)
from livingworld.infrastructure.persistence.card_library_models import (
    CardPackRecord as Pack,
)


class CardPackStore:
    def __init__(self, sessions):
        self._sessions = sessions

    async def list(self):
        async with self._sessions() as session:
            rows = (
                await session.scalars(select(Pack).order_by(Pack.created_at, Pack.pack_id))
            ).all()
            members = (await session.scalars(select(Member).order_by(Member.position))).all()
            return [
                {
                    "id": str(row.pack_id),
                    "name": row.name,
                    "subtitle": row.subtitle,
                    "revision": row.revision,
                    "design": row.design,
                    "cardIds": [
                        str(item.card_id) for item in members if item.pack_id == row.pack_id
                    ],
                }
                for row in rows
            ]

    async def find(self, pack_id):
        return next((item for item in await self.list() if item["id"] == str(pack_id)), None)

    async def load(self, pack_id):
        item = await self.find(pack_id)
        if item is None:
            raise EntityNotFoundError("card_pack_not_found")
        return item

    async def save(self, pack_id, revision, name, subtitle, card_ids, design, images=()):
        if len(set(card_ids)) != len(card_ids):
            raise ContentConflictError("card_pack_members_invalid")
        try:
            async with self._sessions() as session, session.begin():
                await session.connection(execution_options={"livingworld_write_intent": True})
                row = await session.get(Pack, pack_id)
                current_ids = list(
                    await session.scalars(
                        select(Member.card_id)
                        .where(Member.pack_id == pack_id)
                        .order_by(Member.position)
                    )
                )
                if (
                    row is not None
                    and row.revision == revision + 1
                    and (row.name, row.subtitle, row.design, current_ids)
                    == (name, subtitle, design, list(card_ids))
                ):
                    return await self.load(pack_id)
                if (row.revision if row else 0) != revision:
                    raise ContentConflictError("card_pack_changed")
                found = set(
                    await session.scalars(select(Card.card_id).where(Card.card_id.in_(card_ids)))
                )
                if found != set(card_ids):
                    raise EntityNotFoundError("card_pack_card_not_found")
                if row is None:
                    row = Pack(pack_id=pack_id, created_at=datetime.now(UTC))
                    session.add(row)
                row.name, row.subtitle, row.design, row.revision = (
                    name,
                    subtitle,
                    design,
                    revision + 1,
                )
                await session.flush()
                await session.execute(delete(Member).where(Member.pack_id == pack_id))
                session.add_all(
                    Member(pack_id=pack_id, card_id=card_id, position=index)
                    for index, card_id in enumerate(card_ids)
                )
                for info in images:
                    if await session.get(Image, (pack_id, info["digest"])) is None:
                        session.add(Image(pack_id=pack_id, **info))
        except IntegrityError:
            raise ContentConflictError("card_pack_changed") from None
        return await self.load(pack_id)

    async def include(self, pack_id, card_id, revision):
        try:
            async with self._sessions() as session, session.begin():
                await session.connection(execution_options={"livingworld_write_intent": True})
                row = await session.get(Pack, pack_id)
                if row is None or await session.get(Card, card_id) is None:
                    raise EntityNotFoundError("card_pack_card_not_found")
                if await session.get(Member, (pack_id, card_id)) is None:
                    if row.revision != revision:
                        raise ContentConflictError("card_pack_changed")
                    count = len(
                        list(
                            await session.scalars(
                                select(Member.card_id).where(Member.pack_id == pack_id)
                            )
                        )
                    )
                    if count >= 1024:
                        raise ContentConflictError("card_pack_members_limit")
                    session.add(Member(pack_id=pack_id, card_id=card_id, position=count))
                    row.revision += 1
        except IntegrityError:
            raise ContentConflictError("card_pack_changed") from None
        return await self.load(pack_id)

    async def image(self, pack_id, digest):
        async with self._sessions() as session:
            row = await session.get(Image, (pack_id, digest))
            return (
                {
                    key: getattr(row, key)
                    for key in ("digest", "size", "media_type", "width", "height")
                }
                if row
                else None
            )

    async def add_image(self, pack_id, info):
        async with self._sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            if await session.get(Pack, pack_id) is None:
                raise EntityNotFoundError("card_pack_not_found")
            if await session.get(Image, (pack_id, info["digest"])) is None:
                session.add(Image(pack_id=pack_id, **info))
