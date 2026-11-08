"""Bounded, authorized recent dialogue; no keyword search or derived memory required."""

from collections import Counter

from sqlalchemy import LargeBinary, and_, cast, exists, func, or_, select
from sqlalchemy.orm import aliased

from livingworld.application.chat_messages import RecentDialogue
from livingworld.application.chat_privacy import project_message
from livingworld.application.errors import EntityNotFoundError
from livingworld.domain.identifiers import CharacterId
from livingworld.infrastructure.persistence.chat_path_queries import (
    active_memory_clause,
    active_message_clause,
)
from livingworld.infrastructure.persistence.long_memory_models import LongChatMemoryRecord as Memory
from livingworld.infrastructure.persistence.models import (
    CharacterRecord,
)
from livingworld.infrastructure.persistence.models import (
    ChatConversationRecord as Conversation,
)
from livingworld.infrastructure.persistence.models import (
    ChatMessageRecord as Message,
)
from livingworld.infrastructure.persistence.models import (
    ChatParticipantRecord as Participant,
)


async def recent_dialogue(sessions, character, player, current, to_message):
    if not character.world_id == player.world_id == current.conversation_id.world_id:
        raise EntityNotFoundError("chat_world_mismatch")
    async with sessions() as session:
        owner = await session.get(
            Participant,
            (character.world_id.value, current.conversation_id.value, character.value),
        )
        conversation = await session.get(
            Conversation, (character.world_id.value, current.conversation_id.value)
        )
        if owner is None or conversation is None or conversation.player_id != player.value:
            raise EntityNotFoundError("conversation_not_found")
        source = aliased(Message)
        excluded_source = exists(
            select(Memory.entry_id)
            .join(
                source,
                and_(source.world_id == Memory.world_id, source.message_id == Memory.message_id),
            )
            .where(
                source.world_id == Message.world_id,
                source.turn_id == Message.turn_id,
                Memory.player_id == player.value,
                Memory.character_id == character.value,
                or_(Memory.state == "forgotten", ~active_memory_clause(Memory)),
            )
        )
        authorized = (
            select(Message, Conversation.kind)
            .join(
                Participant,
                and_(
                    Participant.world_id == Message.world_id,
                    Participant.conversation_id == Message.conversation_id,
                ),
            )
            .join(
                Conversation,
                and_(
                    Conversation.world_id == Message.world_id,
                    Conversation.conversation_id == Message.conversation_id,
                ),
            )
            .where(
                active_message_clause(Message),
                ~excluded_source,
                Message.world_id == character.world_id.value,
                Participant.character_id == character.value,
                Conversation.player_id == player.value,
                Conversation.kind.in_(("direct", "group")),
                Message.conversation_id != current.conversation_id.value,
                Message.created_at_utc < current.created_at_utc,
            )
        )
        # Inspect at most 256 identities, then fetch at most 32 recent turns.
        identities = (
            (
                await session.execute(
                    authorized.with_only_columns(Message.turn_id)
                    .order_by(
                        Message.created_at_utc.desc(), Message.position.desc(), Message.message_id
                    )
                    .limit(256)
                )
            )
            .scalars()
            .all()
        )
        turn_ids = tuple(dict.fromkeys(identities))[:32]
        if not turn_ids:
            return ()
        scope = authorized.where(Message.turn_id.in_(turn_ids))
        # Count only these bounded candidate turns so an oversized turn is never
        # silently cut in half by the payload limit below.
        totals = (
            await session.execute(
                scope.with_only_columns(
                    Message.turn_id,
                    func.count(),
                    func.sum(func.length(cast(Message.text, LargeBinary))),
                ).group_by(Message.turn_id)
            )
        ).all()
        counts = {
            identity: count
            for identity, count, size in totals
            if count <= 128 and size <= 96 * 1024
        }
        scope = scope.where(Message.turn_id.in_(counts))
        rows = (
            await session.execute(
                scope.order_by(
                    Message.created_at_utc.desc(), Message.position.desc(), Message.message_id
                ).limit(513)
            )
        ).all()
        present = Counter(row.turn_id for row, _kind in rows)
        rows = [(row, kind) for row, kind in rows if present[row.turn_id] == counts[row.turn_id]]
        character_ids = {row.sender_character_id for row, _kind in rows} - {None}
        names = tuple(
            (CharacterId(character.world_id, row.character_id), row.name)
            for row in (
                await session.scalars(
                    select(CharacterRecord).where(
                        CharacterRecord.world_id == character.world_id.value,
                        CharacterRecord.character_id.in_(character_ids),
                    )
                )
            ).all()
        )
        return tuple(
            RecentDialogue(message, kind, names)
            for row, kind in rows
            if (message := project_message(to_message(row), character)).text.strip()
            or message.media
        )
