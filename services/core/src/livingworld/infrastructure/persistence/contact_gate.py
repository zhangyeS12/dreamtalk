"""Saved replies release the gate; retired conversations cannot await a reply."""

from sqlalchemy import exists, func, select
from sqlalchemy.orm import aliased

from livingworld.infrastructure.persistence.authored_lifecycle import removed_character_roots
from livingworld.infrastructure.persistence.models import ChatConversationRecord as Conversation
from livingworld.infrastructure.persistence.models import ChatMessageRecord as Message
from livingworld.infrastructure.persistence.models import ChatParticipantRecord as Participant
from livingworld.infrastructure.persistence.models import ChatTurnRecord as Turn
from livingworld.infrastructure.persistence.offline_contact_models import (
    OfflineContactEpisodeRecord as Offline,
)
from livingworld.infrastructure.persistence.proactive_models import ProactiveEpisodeRecord as Online


async def waiting_conversation(session, world, player):
    reply = aliased(Message)
    # Joint contact is one turn with two messages. The reply must follow both.
    delivered = (
        select(Message.conversation_id, func.max(Message.position).label("position"))
        .join(Turn, (Turn.world_id == Message.world_id) & (Turn.turn_id == Message.turn_id))
        .join(
            Conversation,
            (Conversation.world_id == Message.world_id)
            & (Conversation.conversation_id == Message.conversation_id),
        )
        .where(
            Message.world_id == world,
            Conversation.player_id == player,
            Turn.kind == "outreach",
            Message.sender_character_id.is_not(None),
        )
        .group_by(Message.conversation_id, Message.turn_id)
        .subquery()
    )
    removed = await removed_character_roots(session, world)
    retired = select(Participant.conversation_id).where(
        Participant.world_id == world, Participant.root_import_id.in_(removed)
    )
    return await session.scalar(
        select(delivered.c.conversation_id)
        .where(
            delivered.c.conversation_id.not_in(retired),
            ~exists(
                select(reply.message_id).where(
                    reply.world_id == world,
                    reply.conversation_id == delivered.c.conversation_id,
                    reply.sender_player_id == player,
                    reply.position > delivered.c.position,
                )
            ),
        )
        .order_by(delivered.c.conversation_id)
        .limit(1)
    )


async def contact_blocked(session, world, player, *, exclude_online=None, exclude_offline=None):
    online = select(Online.episode_id).where(
        Online.world_id == world, Online.player_id == player, Online.state == "writing"
    )
    offline = select(Offline.episode_id).where(
        Offline.world_id == world,
        Offline.player_id == player,
        Offline.state.in_(["queued", "planning", "writing"]),
    )
    if exclude_online is not None:
        online = online.where(Online.episode_id != exclude_online)
    if exclude_offline is not None:
        offline = offline.where(Offline.episode_id != exclude_offline)
    return bool(
        await session.scalar(online.limit(1))
        or await session.scalar(offline.limit(1))
        or await waiting_conversation(session, world, player)
    )
