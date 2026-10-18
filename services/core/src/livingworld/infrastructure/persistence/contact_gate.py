"""Saved replies release the gate; retired conversations cannot await a reply."""

from sqlalchemy import and_, exists, func, select
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


def _private_episode_answered(delivered, world, player):
    """Only a saved reply to one of this episode's two explicit deliveries counts."""
    episode = aliased(Online)
    turn, invitation, reply = aliased(Turn), aliased(Message), aliased(Message)
    path = "$.private_delivery_turn_ids"
    turns = (
        func.json_extract(episode.input_json, path + "[0]"),
        func.json_extract(episode.input_json, path + "[1]"),
    )
    return exists(
        select(episode.episode_id)
        .join(
            turn,
            and_(
                turn.world_id == episode.world_id,
                turn.turn_id.in_(turns),
                turn.kind == "outreach",
            ),
        )
        .join(
            invitation,
            and_(
                invitation.world_id == turn.world_id,
                invitation.turn_id == turn.turn_id,
                invitation.conversation_id == turn.conversation_id,
                invitation.sender_character_id.is_not(None),
            ),
        )
        .join(
            reply,
            and_(
                reply.world_id == invitation.world_id,
                reply.conversation_id == invitation.conversation_id,
                reply.sender_player_id == player,
                reply.position > invitation.position,
            ),
        )
        .where(
            episode.world_id == world,
            episode.player_id == player,
            episode.state == "delivered",
            episode.source_kind == "shared",
            func.json_type(episode.input_json, path) == "array",
            func.json_array_length(episode.input_json, path) == 2,
            delivered.c.turn_id.in_(turns),
        )
        .correlate(delivered)
    )


async def waiting_conversation(session, world, player):
    reply = aliased(Message)
    # A group reply follows both messages; a split invitation accepts either private reply.
    delivered = (
        select(
            Message.conversation_id, Message.turn_id, func.max(Message.position).label("position")
        )
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
            ~_private_episode_answered(delivered, world, player),
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
