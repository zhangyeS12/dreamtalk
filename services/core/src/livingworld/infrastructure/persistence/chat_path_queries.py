"""Explicit transcript visibility shared by history, generation, recall and sources."""

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import aliased

from livingworld.application.errors import ChatTurnUnavailableError
from livingworld.infrastructure.persistence.chat_path_models import (
    ChatMemoryOriginRecord as Origin,
)
from livingworld.infrastructure.persistence.chat_path_models import (
    ChatPathMessageRecord as Member,
)
from livingworld.infrastructure.persistence.chat_path_models import (
    ChatPathRecord as Path,
)
from livingworld.infrastructure.persistence.chat_path_models import (
    ChatPathStateRecord as State,
)
from livingworld.infrastructure.persistence.chat_path_models import (
    ChatPathTurnRecord as PathTurn,
)


def message_visible_clause(world, conversation, identity):
    """Legacy conversations have one implicit path; initialized paths are exact sets."""
    state, member = aliased(State), aliased(Member)
    current = (
        select(state.active_path_id)
        .where(
            state.world_id == world,
            state.conversation_id == conversation,
        )
        .correlate_except(state)
        .scalar_subquery()
    )
    included = exists(
        select(member.message_id)
        .where(
            member.world_id == world,
            member.path_id == current,
            member.message_id == identity,
        )
        .correlate_except(member)
    )
    return or_(current.is_(None), included)


def active_message_clause(message):
    return message_visible_clause(message.world_id, message.conversation_id, message.message_id)


def writable_conversation_clause(conversation):
    state, path = aliased(State), aliased(Path)
    return ~exists(
        select(state.conversation_id)
        .join(
            path,
            and_(
                path.world_id == state.world_id,
                path.path_id == state.active_path_id,
            ),
        )
        .where(
            state.world_id == conversation.world_id,
            state.conversation_id == conversation.conversation_id,
            path.kind == "checkpoint",
        )
        .correlate_except(state, path)
    )


def memory_visible_clause(memory):
    state, origin = aliased(State), aliased(Origin)
    initialized = exists(
        select(state.conversation_id)
        .where(
            state.world_id == memory.world_id,
            state.conversation_id == memory.conversation_id,
        )
        .correlate_except(state)
    )
    provenance = exists(
        select(origin.entry_id)
        .where(
            origin.world_id == memory.world_id,
            origin.entry_id == memory.entry_id,
            message_visible_clause(memory.world_id, memory.conversation_id, origin.message_id),
        )
        .correlate_except(origin)
    )
    return and_(
        message_visible_clause(memory.world_id, memory.conversation_id, memory.message_id),
        or_(~initialized, provenance),
    )


def active_memory_clause(memory):
    successor = aliased(type(memory) if not isinstance(memory, type) else memory)
    replaced = exists(
        select(successor.entry_id)
        .where(
            successor.world_id == memory.world_id,
            successor.player_id == memory.player_id,
            successor.character_id == memory.character_id,
            successor.replaces == memory.entry_id,
            memory_visible_clause(successor),
        )
        .correlate_except(successor)
    )
    return and_(memory.state != "forgotten", ~replaced)


async def active_path_id(session, world, conversation):
    return (
        await session.scalar(
            select(State.active_path_id).where(
                State.world_id == world, State.conversation_id == conversation
            )
        )
        or conversation
    )


async def require_writable_path(session, world, conversation):
    kind = await session.scalar(
        select(Path.kind)
        .join(State, and_(State.world_id == Path.world_id, State.active_path_id == Path.path_id))
        .where(State.world_id == world, State.conversation_id == conversation)
    )
    if kind == "checkpoint":
        raise ChatTurnUnavailableError("chat_checkpoint_read_only")


async def stamp_message(session, message):
    """Use only inside the transaction that creates the immutable message."""
    state = await session.get(State, (message.world_id, message.conversation_id))
    if state is None:
        return
    await require_writable_path(session, message.world_id, message.conversation_id)
    if (
        await session.get(Member, (message.world_id, state.active_path_id, message.message_id))
        is None
    ):
        session.add(
            Member(
                world_id=message.world_id,
                path_id=state.active_path_id,
                message_id=message.message_id,
            )
        )


async def stamp_turn(session, turn):
    state = await session.get(State, (turn.world_id, turn.conversation_id))
    if state is not None and await session.get(PathTurn, (turn.world_id, turn.turn_id)) is None:
        session.add(
            PathTurn(world_id=turn.world_id, turn_id=turn.turn_id, path_id=state.active_path_id)
        )


async def require_current_attempt(session, turn):
    binding = await session.get(PathTurn, (turn.world_id, turn.turn_id))
    state = await session.get(State, (turn.world_id, turn.conversation_id))
    if binding is not None and (state is None or state.active_path_id != binding.path_id):
        raise ChatTurnUnavailableError("chat_path_changed")
