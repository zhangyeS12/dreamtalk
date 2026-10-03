"""Owner-authorized chat memories and bounded FTS5 recall across conversations."""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import LargeBinary, and_, cast, exists, false, func, or_, select

from livingworld.application.errors import EntityNotFoundError
from livingworld.application.long_chat_memory import LongMemoryError
from livingworld.infrastructure.persistence.long_memory_models import LongChatMemoryRecord as Memory
from livingworld.infrastructure.persistence.long_memory_models import (
    LongChatMemorySettingsRecord as Settings,
)
from livingworld.infrastructure.persistence.models import ChatConversationRecord as Conversation
from livingworld.infrastructure.persistence.models import ChatMessageRecord as Message
from livingworld.infrastructure.persistence.models import ChatParticipantRecord as Participant
from livingworld.infrastructure.persistence.models import LocalPlayerBindingRecord as Binding


def _scope(world, player, character):
    return (
        Memory.world_id == world,
        Memory.player_id == player,
        Memory.character_id == character,
        exists(
            select(Participant.character_id)
            .join(
                Conversation,
                and_(
                    Conversation.world_id == Participant.world_id,
                    Conversation.conversation_id == Participant.conversation_id,
                ),
            )
            .where(
                Participant.world_id == Memory.world_id,
                Participant.conversation_id == Memory.conversation_id,
                Participant.character_id == Memory.character_id,
                Conversation.player_id == Memory.player_id,
            )
        ),
    )


async def _authorize(session, conversation, player, character):
    if not conversation.world_id == player.world_id == character.world_id:
        raise EntityNotFoundError("conversation_not_found")
    found = await session.scalar(
        select(Participant.character_id)
        .join(
            Conversation,
            and_(
                Conversation.world_id == Participant.world_id,
                Conversation.conversation_id == Participant.conversation_id,
            ),
        )
        .join(
            Binding,
            and_(
                Binding.world_id == Conversation.world_id,
                Binding.player_id == Conversation.player_id,
            ),
        )
        .where(
            Conversation.world_id == conversation.world_id.value,
            Conversation.conversation_id == conversation.value,
            Conversation.player_id == player.value,
            Participant.character_id == character.value,
        )
    )
    if found is None:
        raise EntityNotFoundError("conversation_not_found")


def _view(row):
    return {
        "entry_id": str(row.entry_id),
        "character_id": str(row.character_id),
        "kind": row.kind,
        "topic": row.topic,
        "content": row.content,
        "quote": row.quote,
        "source_kind": row.source_kind,
        "source_sender_id": str(row.source_sender_id),
        "conversation_id": str(row.conversation_id),
        "message_id": str(row.message_id),
        "created_at": row.created_at.isoformat(),
        "world_time": str(row.world_time) if row.world_time is not None else None,
        "state": row.state,
        "pinned": row.pinned,
        "revision": row.revision,
        "replaces": str(row.replaces) if row.replaces else None,
    }


async def record_chat_memories(
    session, reply, player, candidates, world_time=None, *, source_player=None
):
    """Called only inside the completed-reply transaction after the claim checks."""
    if not candidates:
        return
    source_player = source_player or await session.scalar(
        select(Message).where(
            Message.world_id == reply.world_id,
            Message.turn_id == reply.turn_id,
            Message.conversation_id == reply.conversation_id,
            Message.sender_player_id == player.value,
        )
    )
    if source_player is None:
        return
    owners = (
        await session.scalars(
            select(Participant.character_id).where(
                Participant.world_id == reply.world_id,
                Participant.conversation_id == reply.conversation_id,
            )
        )
    ).all()
    # The selected speaker's permitted ID identifies a source, not another
    # member's private record. Resolve each owner's copy by source fingerprint.
    replacements = {}
    for item in candidates[:4]:
        if not item.replaces:
            continue
        try:
            old_id = UUID(item.replaces)
        except ValueError:
            continue
        source = source_player if item.source == "player" else reply
        sender = source.sender_player_id or source.sender_character_id
        old = await session.scalar(
            select(Memory).where(
                *_scope(reply.world_id, player.value, reply.sender_character_id),
                Memory.entry_id == old_id,
                Memory.state == "active",
                or_(
                    Memory.source_sender_id == sender,
                    and_(item.source == "player", Memory.kind == "promise"),
                ),
            )
        )
        if old is not None:
            replacements[item.replaces] = old.fingerprint
    for owner in owners:
        settings = await session.get(Settings, (reply.world_id, player.value, owner))
        if settings is not None and not settings.enabled:
            continue
        for item in candidates[:4]:
            source = source_player if item.source == "player" else reply
            sender = source.sender_player_id or source.sender_character_id
            if (
                not item.topic.strip()
                or not item.content.strip()
                or not item.quote.strip()
                or item.quote not in source.text
                or len(item.quote.encode("utf-8")) > 4096
            ):
                continue
            fingerprint = hashlib.sha256(
                json.dumps(
                    [str(source.message_id), item.kind, item.topic.strip().casefold(), item.quote],
                    ensure_ascii=False,
                ).encode()
            ).hexdigest()
            previous = await session.scalar(
                select(Memory.entry_id).where(
                    *_scope(reply.world_id, player.value, owner), Memory.fingerprint == fingerprint
                )
            )
            if previous is not None:
                continue
            old = None
            if item.replaces:
                old_fingerprint = replacements.get(item.replaces)
                if old_fingerprint is None:
                    continue
                old = await session.scalar(
                    select(Memory).where(
                        *_scope(reply.world_id, player.value, owner),
                        Memory.fingerprint == old_fingerprint,
                        Memory.state == "active",
                    )
                )
                if old is None and owner == reply.sender_character_id:
                    continue
            # A shared topic alone does not prove a correction. Supplements coexist.
            if old is not None:
                old.state, old.revision = "superseded", old.revision + 1
            session.add(
                Memory(
                    world_id=reply.world_id,
                    entry_id=uuid4(),
                    player_id=player.value,
                    character_id=owner,
                    conversation_id=reply.conversation_id,
                    message_id=source.message_id,
                    source_sender_id=sender,
                    source_kind="player" if source.sender_player_id else "character",
                    kind=item.kind,
                    topic=item.topic.strip(),
                    content=item.content.strip(),
                    quote=item.quote,
                    created_at=reply.created_at_utc,
                    world_time=world_time,
                    state="active",
                    pinned=bool(old and old.pinned),
                    revision=0,
                    replaces=old.entry_id if old else None,
                    fingerprint=fingerprint,
                )
            )
            await session.flush()


@dataclass(frozen=True)
class RecallCandidate:
    text: str
    row: object
    scope_key: str = ""


class SqlAlchemyLongChatMemoryStore:
    def __init__(self, sessions, ranker):
        self.sessions, self.ranker = sessions, ranker

    async def _queries(self, session, conversation, player, current):
        # Current membership is authorized before this same-conversation read.
        previous = (
            await session.scalars(
                select(Message.text)
                .where(
                    Message.world_id == conversation.world_id.value,
                    Message.conversation_id == conversation.value,
                    Message.position < current.position,
                    func.length(cast(Message.text, LargeBinary)) <= 8192,
                )
                .order_by(Message.position.desc())
                .limit(2)
            )
        ).all()
        return tuple(dict.fromkeys([current.text[:2000], *(text[:1000] for text in previous)]))

    async def _terms(self, queries):
        terms = []
        for query in queries[:3]:
            terms.extend(await self.ranker.query_terms(query[:2000]))
        return tuple(dict.fromkeys(terms))

    async def _matching(self, session, world, player, character, query, cutoff=None, modes=None):
        queries = (query,) if isinstance(query, str) else query
        terms = await self._terms(queries)
        predicates = [
            *_scope(world, player, character),
            Memory.state == "active",
            or_(
                false(),
                *(
                    or_(
                        Memory.content.contains(term, autoescape=True),
                        Memory.topic.contains(term, autoescape=True),
                        Memory.quote.contains(term, autoescape=True),
                    )
                    for term in terms
                ),
            ),
        ]
        if cutoff is not None:
            predicates.append(Memory.created_at <= cutoff)
        rows = (
            await session.scalars(
                select(Memory)
                .where(*predicates)
                .order_by(Memory.created_at.desc(), Memory.entry_id)
                .limit(500)
            )
        ).all()
        independent = (
            await session.scalars(
                select(Memory)
                .where(
                    *_scope(world, player, character),
                    Memory.state == "active",
                    *([Memory.created_at <= cutoff] if cutoff is not None else []),
                )
                .order_by(Memory.created_at.desc(), Memory.entry_id)
                .limit(256)
            )
        ).all()
        candidates, seen = [], set()
        for pool in (independent, rows):
            size = 0
            for row in pool:
                text = row.topic + " " + row.content + " " + row.quote
                amount = len(text.encode("utf-8"))
                if row.entry_id in seen or size + amount > 256 * 1024:
                    continue
                candidates.append(RecallCandidate(text, row, f"{world}:{player}:{character}"))
                size += amount
                seen.add(row.entry_id)
        ranked = await self._rank(queries, candidates, 12, modes)
        return [item.row for item in ranked]

    async def _older_quotes(
        self, session, conversation, player, character, current, queries, modes=None
    ):
        """Authorized by the user on 2026-10-02; no background history export."""
        terms = await self._terms(queries)
        recent = (
            select(Message.message_id)
            .where(
                Message.world_id == conversation.world_id.value,
                Message.conversation_id == conversation.value,
                Message.position <= current.position,
            )
            .order_by(Message.position.desc())
            .limit(128)
        )
        hidden = exists(
            select(Memory.entry_id).where(
                Memory.world_id == Message.world_id,
                Memory.player_id == player.value,
                Memory.character_id == character.value,
                Memory.message_id == Message.message_id,
                Memory.state.in_(("forgotten", "superseded")),
            )
        )
        authorized = (
            select(Message)
            .join(
                Conversation,
                and_(
                    Conversation.world_id == Message.world_id,
                    Conversation.conversation_id == Message.conversation_id,
                ),
            )
            .join(
                Participant,
                and_(
                    Participant.world_id == Conversation.world_id,
                    Participant.conversation_id == Conversation.conversation_id,
                ),
            )
            .where(
                Message.world_id == conversation.world_id.value,
                Conversation.player_id == player.value,
                Participant.character_id == character.value,
                Message.created_at_utc < current.created_at_utc,
                Message.message_id.not_in(recent),
                ~hidden,
                func.length(cast(Message.text, LargeBinary)) <= 8192,
            )
            .order_by(Message.created_at_utc.desc(), Message.message_id)
        )
        lexical = (
            (
                await session.scalars(
                    authorized.where(
                        or_(*(Message.text.contains(term, autoescape=True) for term in terms))
                    ).limit(200)
                )
            ).all()
            if terms
            else []
        )
        independent = (await session.scalars(authorized.limit(256))).all()
        # Give both channels space; a large keyword corpus cannot evict all semantic candidates.
        candidates, seen = [], set()
        for rows in (independent, lexical):
            used = 0
            for row in rows:
                size = len(row.text.encode("utf-8"))
                if row.message_id in seen or used + size > 96 * 1024:
                    continue
                used += size
                seen.add(row.message_id)
                candidates.append(
                    RecallCandidate(
                        row.text,
                        row,
                        f"{conversation.world_id.value}:{player.value}:{character.value}",
                    )
                )
        ranked = await self._rank(queries, candidates, 4, modes)
        result, used = [], 2
        for item in ranked:
            row = item.row
            value = {
                "message_id": str(row.message_id),
                "conversation_id": str(row.conversation_id),
                "source_kind": "player" if row.sender_player_id else "character",
                "source_sender_id": str(row.sender_player_id or row.sender_character_id),
                "created_at": row.created_at_utc.isoformat(),
                "quote": row.text,
            }
            size = len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())
            if used + size + 1 > 8192:
                continue
            used += size + 1
            result.append(value)
        return result

    async def _rank(self, queries, candidates, limit, modes):
        method = getattr(self.ranker, "rank_with_mode", None)
        if method is None:
            return await self.ranker.rank_queries(queries, tuple(candidates), limit=limit)
        result, mode = await method(queries, tuple(candidates), limit=limit)
        if modes is not None:
            modes.append(mode)
        return result

    async def for_character(self, conversation, player, character, current):
        async with self.sessions() as session:
            await _authorize(session, conversation, player, character)
            settings = await session.get(
                Settings, (conversation.world_id.value, player.value, character.value)
            )
            scope = (
                *_scope(conversation.world_id.value, player.value, character.value),
                Memory.state == "active",
                Memory.created_at <= current.created_at_utc,
            )
            pinned = (
                await session.scalars(
                    select(Memory)
                    .where(*scope, Memory.pinned.is_(True))
                    .order_by(Memory.created_at.desc(), Memory.entry_id)
                    .limit(8)
                )
            ).all()
            # SQLite's window function caps each kind/speaker separately. Many
            # recent promises cannot evict the player's older identity/preference.
            core_slots = (
                select(
                    Memory.entry_id,
                    func.row_number()
                    .over(
                        partition_by=(Memory.kind, Memory.source_sender_id),
                        order_by=(Memory.created_at.desc(), Memory.entry_id),
                    )
                    .label("slot"),
                )
                .where(
                    *scope,
                    Memory.kind.in_(("identity", "preference", "promise")),
                    Memory.source_sender_id.in_((player.value, character.value)),
                )
                .subquery()
            )
            core_rows = (
                await session.scalars(
                    select(Memory)
                    .join(core_slots, core_slots.c.entry_id == Memory.entry_id)
                    .where(*scope, core_slots.c.slot <= 4)
                    .order_by(core_slots.c.slot, Memory.kind, Memory.source_sender_id)
                )
            ).all()
            buckets = {
                (kind, sender): [
                    row for row in core_rows if row.kind == kind and row.source_sender_id == sender
                ]
                for kind in ("identity", "preference", "promise")
                for sender in (player.value, character.value)
            }
            core = [
                bucket[index]
                for index in range(4)
                for bucket in buckets.values()
                if len(bucket) > index
            ]
            queries = await self._queries(session, conversation, player, current)
            modes = []
            related = await self._matching(
                session,
                conversation.world_id.value,
                player.value,
                character.value,
                queries,
                current.created_at_utc,
                modes,
            )
            result, seen, size = [], set(), 2
            for row in [*pinned[:2], *core[:6], *related[:4], *pinned[2:], *core[6:], *related[4:]]:
                if row.entry_id in seen:
                    continue
                # Keep prompt facts compact; full source IDs stay in management views.
                value = {
                    key: value
                    for key, value in _view(row).items()
                    if key
                    in {
                        "entry_id",
                        "kind",
                        "topic",
                        "content",
                        "quote",
                        "source_kind",
                        "source_sender_id",
                        "created_at",
                        "world_time",
                    }
                }
                encoded = len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())
                if size + encoded + 1 > 8192 or len(result) >= 16:
                    continue
                size += encoded + 1
                seen.add(row.entry_id)
                result.append(value)
            older_quotes = await self._older_quotes(
                session, conversation, player, character, current, queries, modes
            )
            return {
                "_retrieval_mode": "hybrid_partial"
                if "hybrid_partial" in modes
                else "hybrid"
                if "hybrid" in modes
                else "keyword_fallback"
                if "keyword_fallback" in modes
                else "keyword",
                "long_term_original_quotes": older_quotes,
                "long_memory_capture_enabled": settings is None or settings.enabled,
                "long_term_dialogue_memories": result,
            }

    async def snapshot(self, conversation, player, character, before=None, query=""):
        async with self.sessions() as session:
            await _authorize(session, conversation, player, character)
            settings = await session.get(
                Settings, (conversation.world_id.value, player.value, character.value)
            )
            conditions = list(_scope(conversation.world_id.value, player.value, character.value))
            if query:
                rows = await self._matching(
                    session, conversation.world_id.value, player.value, character.value, query
                )
            else:
                if before:
                    try:
                        date, identity = before.rsplit("|", 1)
                        stamp, entry = datetime.fromisoformat(date), UUID(identity)
                        if stamp.tzinfo is None:
                            raise ValueError()
                    except ValueError:
                        raise LongMemoryError("long_memory_cursor_invalid") from None
                    conditions.append(
                        or_(
                            Memory.created_at < stamp,
                            and_(Memory.created_at == stamp, Memory.entry_id > entry),
                        )
                    )
                rows = (
                    await session.scalars(
                        select(Memory)
                        .where(*conditions)
                        .order_by(Memory.created_at.desc(), Memory.entry_id)
                        .limit(51)
                    )
                ).all()
            more = len(rows) > 50
            rows = rows[:50]
            return {
                "enabled": settings is None or settings.enabled,
                "settings_revision": settings.revision if settings else 0,
                "items": [_view(row) for row in rows],
                "next_cursor": rows[-1].created_at.isoformat() + "|" + str(rows[-1].entry_id)
                if more
                else None,
            }

    async def configure(self, conversation, player, character, enabled, revision):
        async with self.sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            await _authorize(session, conversation, player, character)
            key = (conversation.world_id.value, player.value, character.value)
            settings = await session.get(Settings, key)
            if (settings.revision if settings else 0) != revision:
                raise LongMemoryError("long_memory_changed")
            if settings is None:
                settings = Settings(
                    world_id=key[0],
                    player_id=key[1],
                    character_id=key[2],
                    enabled=enabled,
                    revision=1,
                )
                session.add(settings)
            else:
                settings.enabled, settings.revision = enabled, settings.revision + 1

    async def mark(self, conversation, player, character, entry, active, pinned, revision):
        async with self.sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            await _authorize(session, conversation, player, character)
            row = await session.scalar(
                select(Memory).where(
                    *_scope(conversation.world_id.value, player.value, character.value),
                    Memory.entry_id == entry,
                )
            )
            if row is None:
                raise EntityNotFoundError("long_memory_not_found")
            if row.revision != revision or row.state == "superseded":
                raise LongMemoryError("long_memory_changed")
            row.state, row.pinned, row.revision = (
                "active" if active else "forgotten",
                pinned,
                revision + 1,
            )
