"""Owner-scoped metadata only; acknowledging loaded positions does not answer outreach."""

from datetime import UTC, datetime

from sqlalchemy import Integer, func, select

from livingworld.application.errors import EntityNotFoundError
from livingworld.infrastructure.persistence.contact_gate import waiting_conversation
from livingworld.infrastructure.persistence.deletion_models import GroupDissolutionRecord
from livingworld.infrastructure.persistence.models import ChatConversationRecord as Conversation
from livingworld.infrastructure.persistence.models import ChatMessageRecord as Message
from livingworld.infrastructure.persistence.models import LocalPlayerBindingRecord as Binding
from livingworld.infrastructure.persistence.offline_contact import _write
from livingworld.infrastructure.persistence.offline_contact_models import (
    OfflineContactEpisodeRecord as Offline,
)
from livingworld.infrastructure.persistence.proactive_models import ChatReadPositionRecord as Read


class SqlAlchemyChatUnreadStore:
    def __init__(self, sessions):
        self.sessions = sessions

    async def _owner(self, session, world, player):
        binding = await session.get(Binding, world.value)
        if player is None or binding is None or binding.player_id != player.value:
            raise EntityNotFoundError("player_not_found")

    async def snapshot(self, world, player, *, after=None, page=False):
        async with self.sessions() as session:
            await self._owner(session, world, player)
            incoming = func.sum(
                (
                    (Message.sender_character_id.is_not(None))
                    & (Message.position > func.coalesce(Read.position, 0))
                ).cast(Integer)
            )
            statement = (
                select(
                    Conversation.conversation_id,
                    func.coalesce(func.max(Message.position), 0),
                    func.coalesce(incoming, 0).label("unread_count"),
                )
                .outerjoin(
                    Message,
                    (Message.world_id == Conversation.world_id)
                    & (Message.conversation_id == Conversation.conversation_id),
                )
                .outerjoin(
                    Read,
                    (Read.world_id == Conversation.world_id)
                    & (Read.conversation_id == Conversation.conversation_id)
                    & (Read.player_id == Conversation.player_id),
                )
                .where(
                    Conversation.world_id == world.value,
                    Conversation.player_id == player.value,
                    Conversation.conversation_id.not_in(
                        select(GroupDissolutionRecord.conversation_id).where(
                            GroupDissolutionRecord.world_id == world.value
                        )
                    ),
                )
                .group_by(Conversation.conversation_id)
            )
            has_unread = None
            if not page or after is None:
                summary = statement.subquery()
                has_unread = bool(
                    await session.scalar(
                        select(summary.c.conversation_id).where(summary.c.unread_count > 0).limit(1)
                    )
                )
            if page and after is not None:
                statement = statement.where(Conversation.conversation_id > after)
            statement = statement.order_by(Conversation.conversation_id)
            rows = (await session.execute(statement.limit(129) if page else statement)).all()
            more = page and len(rows) > 128
            if page:
                rows = rows[:128]
            waiting = await waiting_conversation(session, world.value, player.value)
            return {
                "player_id": str(player.value),
                "items": [
                    {"conversation_id": str(c), "latest_position": latest, "unread": count}
                    for c, latest, count in rows
                ],
                "waiting_conversation_id": str(waiting) if waiting else None,
                **({"has_unread": has_unread} if has_unread is not None else {}),
                "next_after": str(rows[-1][0]) if more else None,
            }

    async def mark_read(self, world, player, conversation, position):
        async with self.sessions() as session:
            await _write(session)
            await self._owner(session, world, player)
            row = await session.get(Conversation, (world.value, conversation))
            if row is None or row.player_id != player.value:
                raise EntityNotFoundError("conversation_not_found")
            message = await session.scalar(
                select(Message.message_id).where(
                    Message.world_id == world.value,
                    Message.conversation_id == conversation,
                    Message.position == position,
                )
            )
            if message is None:
                raise EntityNotFoundError("message_not_found")
            read = await session.get(Read, (world.value, conversation))
            if read is None:
                session.add(
                    Read(
                        world_id=world.value,
                        conversation_id=conversation,
                        player_id=player.value,
                        position=position,
                    )
                )
            else:
                read.position = max(read.position, position)
            # Compatibility for the old offline status panel. Its flag never releases the gate.
            episodes = (
                await session.scalars(
                    select(Offline)
                    .join(
                        Message,
                        (Message.world_id == Offline.world_id)
                        & (Message.message_id == Offline.message_id),
                    )
                    .where(
                        Offline.world_id == world.value,
                        Offline.player_id == player.value,
                        Offline.conversation_id == conversation,
                        Offline.state == "delivered",
                        Offline.read_at_utc.is_(None),
                        Message.position <= position,
                    )
                )
            ).all()
            for episode in episodes:
                episode.read_at_utc = datetime.now(UTC)
            await session.commit()
