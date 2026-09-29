"""Bounded earlier dialogue quotes; never form memories or assert world truth."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from livingworld.application.chat_messages import ChatMessage, ChatMessageService
from livingworld.application.errors import EntityNotFoundError
from livingworld.domain.identifiers import CharacterId, ConversationId, MessageId, PlayerId

_MAX_SCAN_PAGES = 3
_SCAN_PAGE_SIZE = 100
_MAX_SCAN_BYTES = 512 * 1024
_MAX_QUOTE_BYTES = 8 * 1024
_MAX_QUOTES = 4
_MAX_QUERY_CHARS = 1024


class ChatRecallRanker(Protocol):
    async def rank(
        self, query: str, candidates: tuple[ChatMessage, ...], *, limit: int
    ) -> tuple[ChatMessage, ...]: ...


@dataclass(frozen=True, slots=True)
class ChatHistoryMatches:
    messages: tuple[ChatMessage, ...] = field(repr=False)
    scanned_count: int
    skipped_count: int
    next_before_position: int | None


class EarlierChatRecall:
    def __init__(self, messages: ChatMessageService, ranker: ChatRecallRanker) -> None:
        self._messages = messages
        self._ranker = ranker

    async def search_history(
        self,
        conversation: ConversationId,
        query: str,
        before_position: int | None = None,
    ) -> ChatHistoryMatches:
        """Read one bounded, owner-authorized page; never invoke a model or write."""
        if not isinstance(query, str) or not query.strip() or len(query) > 256:
            raise ValueError("chat_history_query_invalid")
        page = await self._messages.page_messages(conversation, _SCAN_PAGE_SIZE, before_position)
        candidates: list[ChatMessage] = []
        used = 0
        scanned = 0
        skipped = 0
        cursor = page.next_before_position
        previous = before_position
        for item in reversed(page.messages):
            if (
                item.conversation_id != conversation
                or item.message_id.world_id != conversation.world_id
                or item.turn_id.world_id != conversation.world_id
                or item.sender_id.world_id != conversation.world_id
                or item.position <= 0
                or (previous is not None and item.position >= previous)
            ):
                raise EntityNotFoundError("chat_recall_scope_invalid")
            size = len(item.text.encode("utf-8"))
            if used + size > _MAX_SCAN_BYTES:
                # Retry from the last consumed position, not the end of the DB page.
                cursor = previous
                break
            used += size
            scanned += 1
            previous = item.position
            if size <= _MAX_QUOTE_BYTES:
                candidates.append(item)
            else:
                skipped += 1
        if cursor is not None and (
            not page.messages
            or cursor < 1
            or (before_position is not None and cursor >= before_position)
        ):
            raise EntityNotFoundError("chat_recall_cursor_invalid")
        ranked = (
            await self._ranker.rank(query.strip(), tuple(candidates), limit=8) if candidates else ()
        )
        known = {item.message_id: item for item in candidates}
        selected: dict[MessageId, ChatMessage] = {}
        quoted_bytes = 0
        for item in ranked:
            if known.get(item.message_id) != item:
                raise EntityNotFoundError("chat_recall_result_invalid")
            size = len(item.text.encode("utf-8"))
            if item.message_id in selected or quoted_bytes + size > 32 * 1024:
                continue
            selected[item.message_id] = item
            quoted_bytes += size
            if len(selected) == 8:
                break
        return ChatHistoryMatches(tuple(selected.values()), scanned, skipped, cursor)

    async def quotes(
        self,
        current: ChatMessage,
        visible: tuple[ChatMessage, ...],
        allowed_senders: frozenset[PlayerId | CharacterId],
    ) -> list[dict[str, str | int]]:
        """Call only after resolving the Character's membership of this conversation."""
        conversation = current.conversation_id
        if (
            current not in visible
            or current.sender_id not in allowed_senders
            or any(sender.world_id != conversation.world_id for sender in allowed_senders)
            or any(
                item.conversation_id != conversation or item.sender_id not in allowed_senders
                for item in visible
            )
        ):
            raise EntityNotFoundError("chat_recall_scope_invalid")
        before = min(item.position for item in visible)
        visible_turns = {item.turn_id for item in visible}
        candidates: list[ChatMessage] = []
        scanned_bytes = 0
        for _ in range(_MAX_SCAN_PAGES):
            if before <= 1:
                break
            # The existing store checks World + selected Player + Conversation in SQL
            # before materializing text. Ranking never sees an unfiltered corpus.
            page = await self._messages.page_messages(conversation, _SCAN_PAGE_SIZE, before)
            for item in reversed(page.messages):
                if (
                    item.conversation_id != conversation
                    or item.sender_id not in allowed_senders
                    or item.message_id.world_id != conversation.world_id
                    or item.turn_id.world_id != conversation.world_id
                    or not 0 < item.position < before
                ):
                    raise EntityNotFoundError("chat_recall_scope_invalid")
                size = len(item.text.encode("utf-8"))
                scanned_bytes += size
                if scanned_bytes > _MAX_SCAN_BYTES:
                    break
                if item.turn_id not in visible_turns and size <= _MAX_QUOTE_BYTES:
                    candidates.append(item)
            cursor = page.next_before_position
            if scanned_bytes > _MAX_SCAN_BYTES or cursor is None:
                break
            if cursor >= before or not page.messages or cursor != page.messages[0].position:
                raise EntityNotFoundError("chat_recall_cursor_invalid")
            before = cursor
        if not candidates:
            return []
        ranked = await self._ranker.rank(
            current.text[-_MAX_QUERY_CHARS:], tuple(candidates), limit=_MAX_QUOTES * 2
        )
        known = {item.message_id: item for item in candidates}
        selected: dict[MessageId, ChatMessage] = {}
        used = 0
        for item in ranked:
            if known.get(item.message_id) != item:
                raise EntityNotFoundError("chat_recall_result_invalid")
            size = len(item.text.encode("utf-8"))
            if item.message_id in selected or used + size > _MAX_QUOTE_BYTES:
                continue
            selected[item.message_id] = item
            used += size
            if len(selected) == _MAX_QUOTES:
                break
        return [
            {
                "message_id": str(item.message_id.value),
                "conversation_id": str(conversation.value),
                "sender_id": str(item.sender_id.value),
                "sender_type": "player" if isinstance(item.sender_id, PlayerId) else "character",
                "position": item.position,
                "created_at_utc": item.created_at_utc.isoformat(),
                "text": item.text,
            }
            for item in sorted(selected.values(), key=lambda item: item.position)
        ]
