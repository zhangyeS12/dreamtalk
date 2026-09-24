"""Durable player sends; model dispatch and character replies are separate steps."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from livingworld.application.errors import EntityNotFoundError
from livingworld.application.player_event_feed import PlayerEventFeedService
from livingworld.domain.contracts import RequestId
from livingworld.domain.identifiers import (
    CharacterId,
    ChatTurnId,
    ConversationId,
    MessageId,
    PlayerId,
)


@dataclass(frozen=True, slots=True)
class ChatMessage:
    message_id: MessageId
    conversation_id: ConversationId
    turn_id: ChatTurnId
    position: int
    sender_id: PlayerId | CharacterId
    text: str
    created_at_utc: datetime


@dataclass(frozen=True, slots=True)
class PlayerSend:
    turn_id: ChatTurnId
    message: ChatMessage
    token_ceiling: int
    status: str


class ChatMessageStore(Protocol):
    async def send_player(
        self,
        request_id: RequestId,
        conversation_id: ConversationId,
        player_id: PlayerId,
        text: str,
        token_ceiling: int,
        fingerprint: str,
    ) -> PlayerSend: ...

    async def list_for_player(
        self, conversation_id: ConversationId, player_id: PlayerId
    ) -> tuple[ChatMessage, ...]: ...


class ChatMessageService:
    def __init__(self, store: ChatMessageStore, players: PlayerEventFeedService) -> None:
        self._store = store
        self._players = players

    async def _player(self, conversation_id: ConversationId) -> PlayerId:
        player = await self._players.selected_player(conversation_id.world_id)
        if player is None:
            raise EntityNotFoundError("selected_player_required")
        return player

    async def send_player(
        self,
        request_id: RequestId,
        conversation_id: ConversationId,
        text: str,
        token_ceiling: int,
    ) -> PlayerSend:
        if not isinstance(text, str) or not text.strip() or len(text.encode("utf-8")) > 65536:
            raise ValueError("chat_message_invalid")
        if (
            isinstance(token_ceiling, bool)
            or not isinstance(token_ceiling, int)
            or token_ceiling <= 0
        ):
            raise ValueError("chat_token_ceiling_invalid")
        player = await self._player(conversation_id)
        semantics = {
            "world_id": str(conversation_id.world_id.value),
            "conversation_id": str(conversation_id.value),
            "player_id": str(player.value),
            "text": text,
            "token_ceiling": token_ceiling,
        }
        fingerprint = hashlib.sha256(
            json.dumps(semantics, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()
        return await self._store.send_player(
            request_id, conversation_id, player, text, token_ceiling, fingerprint
        )

    async def list_messages(self, conversation_id: ConversationId) -> tuple[ChatMessage, ...]:
        return await self._store.list_for_player(
            conversation_id, await self._player(conversation_id)
        )
