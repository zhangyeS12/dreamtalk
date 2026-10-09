"""Selected-Player authorization precedes every bounded transcript page."""

from sqlalchemy import func, select

from livingworld.application.chat_export import ChatExportSnapshot
from livingworld.application.errors import EntityNotFoundError
from livingworld.infrastructure.persistence.chat_messages import _message
from livingworld.infrastructure.persistence.models import (
    CharacterRecord,
    ChatConversationRecord,
    ChatMessageRecord,
    ChatParticipantRecord,
    LocalPlayerBindingRecord,
    PlayerRecord,
    WorldRecord,
)


class SqlAlchemyChatExportStore:
    def __init__(self, sessions):
        self._sessions = sessions

    async def _authorize(self, session, conversation, player):
        row = await session.scalar(
            select(ChatConversationRecord)
            .join(
                LocalPlayerBindingRecord,
                (LocalPlayerBindingRecord.world_id == ChatConversationRecord.world_id)
                & (LocalPlayerBindingRecord.player_id == ChatConversationRecord.player_id),
            )
            .where(
                ChatConversationRecord.world_id == conversation.world_id.value,
                ChatConversationRecord.conversation_id == conversation.value,
                ChatConversationRecord.player_id == player.value,
            )
        )
        if row is None or player.world_id != conversation.world_id:
            raise EntityNotFoundError("export_conversation_unavailable")
        return row

    async def snapshot(self, conversation, player, through_position):
        async with self._sessions() as session, session.begin():
            row = await self._authorize(session, conversation, player)
            scope = (
                ChatMessageRecord.world_id == conversation.world_id.value,
                ChatMessageRecord.conversation_id == conversation.value,
            )
            latest = (
                await session.scalar(select(func.max(ChatMessageRecord.position)).where(*scope))
                or 0
            )
            through = latest if through_position is None else through_position
            if through > latest:
                raise EntityNotFoundError("export_transcript_changed")
            count = await session.scalar(
                select(func.count())
                .select_from(ChatMessageRecord)
                .where(*scope, ChatMessageRecord.position <= through)
            )
            if (
                through
                and await session.scalar(
                    select(ChatMessageRecord.message_id).where(
                        *scope, ChatMessageRecord.position == through
                    )
                )
                is None
            ):
                raise EntityNotFoundError("export_transcript_changed")
            world_name = await session.scalar(
                select(WorldRecord.name).where(WorldRecord.world_id == conversation.world_id.value)
            )
            player_name = await session.scalar(
                select(PlayerRecord.name).where(
                    PlayerRecord.world_id == conversation.world_id.value,
                    PlayerRecord.player_id == player.value,
                )
            )
            participants = (
                await session.execute(
                    select(CharacterRecord.character_id, CharacterRecord.name)
                    .join(
                        ChatParticipantRecord,
                        (ChatParticipantRecord.world_id == CharacterRecord.world_id)
                        & (ChatParticipantRecord.character_id == CharacterRecord.character_id),
                    )
                    .where(
                        ChatParticipantRecord.world_id == conversation.world_id.value,
                        ChatParticipantRecord.conversation_id == conversation.value,
                    )
                    .order_by(CharacterRecord.character_id)
                )
            ).all()
            if world_name is None or player_name is None or not participants:
                raise EntityNotFoundError("export_conversation_unavailable")
            return ChatExportSnapshot(
                conversation,
                player,
                world_name,
                row.kind,
                player_name,
                tuple((str(identity), name) for identity, name in participants),
                through,
                count,
            )

    async def page(self, snapshot, after):
        async with self._sessions() as session, session.begin():
            await self._authorize(session, snapshot.conversation_id, snapshot.player_id)
            rows = (
                await session.scalars(
                    select(ChatMessageRecord)
                    .where(
                        ChatMessageRecord.world_id == snapshot.conversation_id.world_id.value,
                        ChatMessageRecord.conversation_id == snapshot.conversation_id.value,
                        ChatMessageRecord.position > after,
                        ChatMessageRecord.position <= snapshot.through_position,
                    )
                    .order_by(ChatMessageRecord.position)
                    .limit(128)
                )
            ).all()
            return tuple(_message(row) for row in rows)
