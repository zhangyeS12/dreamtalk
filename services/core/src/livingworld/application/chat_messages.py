"""Durable player sends; model dispatch and character replies are separate steps."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
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
    text: str = field(repr=False)
    created_at_utc: datetime


@dataclass(frozen=True, slots=True)
class ChatMessagePage:
    messages: tuple[ChatMessage, ...]
    next_before_position: int | None


@dataclass(frozen=True, slots=True)
class PlayerSend:
    turn_id: ChatTurnId
    message: ChatMessage
    token_ceiling: int
    status: str


@dataclass(frozen=True, slots=True)
class DirectTurnView:
    """Owner-scoped durable outcome; claimed work is never implicitly retried."""

    sent: PlayerSend
    state: str
    reply: ChatMessage | None = field(repr=False)


@dataclass(frozen=True, slots=True)
class GroupTurnView:
    sent: PlayerSend
    state: str
    replies: tuple[ChatMessage, ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class ClaimedDirectTurn:
    """A durable, one-time claim; an interrupted claim is never auto-replayed."""

    turn_id: ChatTurnId
    conversation_id: ConversationId
    player_id: PlayerId
    character_id: CharacterId
    player_message: ChatMessage = field(repr=False)
    token_ceiling: int


@dataclass(frozen=True, slots=True)
class ClaimedGroupTurn:
    """One durable group dispatch with its fixed participant set."""

    turn_id: ChatTurnId
    conversation_id: ConversationId
    player_id: PlayerId
    character_ids: tuple[CharacterId, ...]
    player_message: ChatMessage = field(repr=False)
    token_ceiling: int


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

    async def send_group_player(
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

    async def page_for_player(
        self,
        conversation_id: ConversationId,
        player_id: PlayerId,
        limit: int,
        before_position: int | None,
    ) -> ChatMessagePage: ...

    async def direct_turn(
        self, conversation_id: ConversationId, turn_id: ChatTurnId, player_id: PlayerId
    ) -> DirectTurnView: ...

    async def group_turn(
        self, conversation_id: ConversationId, turn_id: ChatTurnId, player_id: PlayerId
    ) -> GroupTurnView: ...

    async def claim_direct(
        self, conversation_id: ConversationId, turn_id: ChatTurnId, player_id: PlayerId
    ) -> ClaimedDirectTurn: ...

    async def complete_direct(self, claim: ClaimedDirectTurn, text: str) -> ChatMessage: ...

    async def claim_group(
        self, conversation_id: ConversationId, turn_id: ChatTurnId, player_id: PlayerId
    ) -> ClaimedGroupTurn: ...

    async def complete_group_reply(
        self, claim: ClaimedGroupTurn, character_id: CharacterId, ordinal: int, text: str
    ) -> ChatMessage: ...

    async def finish_group(self, claim: ClaimedGroupTurn) -> GroupTurnView: ...


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
        return await self._send_player(
            request_id, conversation_id, text, token_ceiling, group=False
        )

    async def send_group_player(
        self,
        request_id: RequestId,
        conversation_id: ConversationId,
        text: str,
        token_ceiling: int,
    ) -> PlayerSend:
        """Internal group runner entry; the public send path remains direct-only."""
        return await self._send_player(request_id, conversation_id, text, token_ceiling, group=True)

    async def _send_player(
        self,
        request_id: RequestId,
        conversation_id: ConversationId,
        text: str,
        token_ceiling: int,
        *,
        group: bool,
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
        send = self._store.send_group_player if group else self._store.send_player
        return await send(request_id, conversation_id, player, text, token_ceiling, fingerprint)

    async def list_messages(self, conversation_id: ConversationId) -> tuple[ChatMessage, ...]:
        return await self._store.list_for_player(
            conversation_id, await self._player(conversation_id)
        )

    async def page_messages(
        self, conversation_id: ConversationId, limit: int, before_position: int | None = None
    ) -> ChatMessagePage:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("chat_page_limit_invalid")
        if before_position is not None and (
            type(before_position) is not int or before_position < 1
        ):
            raise ValueError("chat_page_cursor_invalid")
        return await self._store.page_for_player(
            conversation_id, await self._player(conversation_id), limit, before_position
        )

    async def direct_turn(
        self, conversation_id: ConversationId, turn_id: ChatTurnId
    ) -> DirectTurnView:
        return await self._store.direct_turn(
            conversation_id, turn_id, await self._player(conversation_id)
        )

    async def group_turn(
        self, conversation_id: ConversationId, turn_id: ChatTurnId
    ) -> GroupTurnView:
        return await self._store.group_turn(
            conversation_id, turn_id, await self._player(conversation_id)
        )

    async def claim_direct(
        self, conversation_id: ConversationId, turn_id: ChatTurnId
    ) -> ClaimedDirectTurn:
        return await self._store.claim_direct(
            conversation_id, turn_id, await self._player(conversation_id)
        )

    async def complete_direct(self, claim: ClaimedDirectTurn, text: str) -> ChatMessage:
        self._validate_reply(text)
        return await self._store.complete_direct(claim, text)

    async def claim_group(
        self, conversation_id: ConversationId, turn_id: ChatTurnId
    ) -> ClaimedGroupTurn:
        return await self._store.claim_group(
            conversation_id, turn_id, await self._player(conversation_id)
        )

    async def complete_group_reply(
        self, claim: ClaimedGroupTurn, character_id: CharacterId, ordinal: int, text: str
    ) -> ChatMessage:
        self._validate_reply(text)
        if type(ordinal) is not int or ordinal < 0:
            raise ValueError("chat_reply_ordinal_invalid")
        return await self._store.complete_group_reply(claim, character_id, ordinal, text)

    async def finish_group(self, claim: ClaimedGroupTurn) -> GroupTurnView:
        return await self._store.finish_group(claim)

    @staticmethod
    def _validate_reply(text: str) -> None:
        if not isinstance(text, str) or not text.strip() or len(text.encode("utf-8")) > 65536:
            raise ValueError("chat_reply_invalid")
