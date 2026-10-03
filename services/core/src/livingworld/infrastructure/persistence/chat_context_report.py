"""Player-owned diagnostic references; private character state never crosses this API."""

import json

from sqlalchemy import select

from livingworld.application.errors import EntityNotFoundError
from livingworld.infrastructure.persistence.models import (
    ChatParticipantRecord,
    ChatReplyExecutionRecord,
    ChatTurnRecord,
)


class ChatContextReportMixin:
    async def save_context_report(self, source, speaker, report):
        sent = source.message if hasattr(source, "message") else source.player_message
        encoded = json.dumps(report, ensure_ascii=False, separators=(",", ":"))
        if len(encoded.encode()) > 32768:
            raise ValueError("chat_context_report_invalid")
        async with self._sessions() as session:
            await session.connection(execution_options={"livingworld_write_intent": True})
            if (
                source.turn_id.world_id != sent.conversation_id.world_id
                or speaker.world_id != sent.conversation_id.world_id
            ):
                raise EntityNotFoundError("chat_turn_not_found")
            await self._conversation(session, sent.conversation_id, sent.sender_id)
            participant = await session.get(
                ChatParticipantRecord,
                (sent.conversation_id.world_id.value, sent.conversation_id.value, speaker.value),
            )
            row = await session.get(
                ChatReplyExecutionRecord, (source.turn_id.world_id.value, source.turn_id.value)
            )
            turn = await session.get(
                ChatTurnRecord, (source.turn_id.world_id.value, source.turn_id.value)
            )
            if (
                participant is None
                or row is None
                or row.state != "running"
                or turn is None
                or turn.conversation_id != sent.conversation_id.value
            ):
                raise EntityNotFoundError("chat_turn_not_found")
            values = json.loads(row.context_reports or "[]")
            values.append({"speaker_id": str(speaker.value), **report})
            if len(values) > 32:
                raise ValueError("chat_context_report_limit")
            row.context_reports = json.dumps(values, ensure_ascii=False, separators=(",", ":"))
            await session.commit()

    async def context_reports(self, conversation, turn_id, player):
        async with self._sessions() as session:
            if turn_id.world_id != conversation.world_id:
                raise EntityNotFoundError("chat_turn_not_found")
            await self._conversation(session, conversation, player)
            turn = await session.get(ChatTurnRecord, (turn_id.world_id.value, turn_id.value))
            if turn is None or turn.conversation_id != conversation.value:
                raise EntityNotFoundError("chat_turn_not_found")
            row = await session.get(
                ChatReplyExecutionRecord, (turn_id.world_id.value, turn_id.value)
            )
            values = json.loads(row.context_reports or "[]") if row is not None else []
            members = set(
                await session.scalars(
                    select(ChatParticipantRecord.character_id).where(
                        ChatParticipantRecord.world_id == conversation.world_id.value,
                        ChatParticipantRecord.conversation_id == conversation.value,
                    )
                )
            )
            return {
                "turn_id": str(turn_id.value),
                "reports": [
                    value
                    for value in values
                    if any(str(member) == value["speaker_id"] for member in members)
                ],
            }
