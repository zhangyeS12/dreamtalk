"""Message-anchored lore timing. No world clock, model call or secret-content read."""

from sqlalchemy import func, select

from livingworld.application.errors import EntityNotFoundError
from livingworld.application.lore_activation import (
    ActivationContext,
    _count,
    active_common_lore,
    entry_key,
    select_common_background,
)
from livingworld.infrastructure.persistence.chat_path_models import (
    ChatLoreActivationRecord as Start,
)
from livingworld.infrastructure.persistence.chat_path_queries import active_message_clause
from livingworld.infrastructure.persistence.models import ChatMessageRecord as Message


class SqlAlchemyChatLoreReader:
    def __init__(self, sessions):
        self._sessions = sessions

    async def __call__(self, conversation, anchor, entries, texts):
        async with self._sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            scope = (
                Message.world_id == conversation.world_id.value,
                Message.conversation_id == conversation.value,
                Message.position <= anchor.position,
                active_message_clause(Message),
            )
            if (
                await session.scalar(
                    select(Message.message_id).where(
                        *scope,
                        Message.message_id == anchor.message_id.value,
                    )
                )
                is None
            ):
                raise EntityNotFoundError("chat_message_not_found")
            count = await session.scalar(select(func.count()).select_from(Message).where(*scope))
            keys = {entry_key(item) for item in entries}
            # One newest visible activation per current entry; no arbitrary history cap.
            starts = await session.execute(
                select(Start.entry_key, func.max(Message.position))
                .join(
                    Message,
                    (Start.world_id == Message.world_id) & (Start.anchor_id == Message.message_id),
                )
                .where(
                    *scope,
                    Start.conversation_id == conversation.value,
                    Start.entry_key.in_(keys),
                    Start.started.is_(True),
                )
                .group_by(Start.entry_key)
            )
            elapsed, already = {}, set()
            for key, position in starts:
                if position == anchor.position:
                    already.add(key)
                else:
                    elapsed[key] = await session.scalar(
                        select(func.count())
                        .select_from(Message)
                        .where(*scope, Message.position > position)
                    )
            context = ActivationContext(
                str(anchor.message_id.value), count, elapsed, frozenset(already)
            )
            selected = select_common_background(
                entries, texts, context=context, include_references=True
            )
            kept = {(item["import_id"], item["entry_id"]) for item in selected}
            new_starts = set()
            for item in active_common_lore(entries, texts, context=context):
                key = entry_key(item)
                if (str(item.import_id), str(item.entry.content_id.value)) not in kept:
                    continue
                sticky = key in elapsed and elapsed[key] < _count(
                    item.entry.activation_metadata, "sticky"
                )
                if key in already or sticky:
                    continue
                new_starts.add(key)
            item_keys = {
                (str(item.import_id), str(item.entry.content_id.value)): entry_key(item)
                for item in entries
            }
            result = []
            for item in selected:
                key = item_keys[(str(item["import_id"]), str(item["entry_id"]))]
                value = {
                    name: value
                    for name, value in item.items()
                    if name not in {"import_id", "entry_id"}
                }
                if key in new_starts:
                    value["_lore_start_key"] = key
                result.append(value)
            return result

    async def commit(self, conversation, anchor, keys):
        """Only the successfully fitted subset starts timing; repeats are receipts."""
        if not keys:
            return
        async with self._sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            if (
                await session.scalar(
                    select(Message.message_id).where(
                        Message.world_id == conversation.world_id.value,
                        Message.conversation_id == conversation.value,
                        Message.message_id == anchor.message_id.value,
                        active_message_clause(Message),
                    )
                )
                is None
            ):
                raise EntityNotFoundError("chat_message_not_found")
            for key in set(keys):
                identity = (
                    conversation.world_id.value,
                    conversation.value,
                    anchor.message_id.value,
                    key,
                )
                if await session.get(Start, identity) is None:
                    session.add(
                        Start(
                            world_id=identity[0],
                            conversation_id=identity[1],
                            anchor_id=identity[2],
                            entry_key=identity[3],
                            started=True,
                        )
                    )
