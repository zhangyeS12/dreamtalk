"""Synthetic cross-channel chronology, source permissions, and complete-turn packing."""

import asyncio
import json
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from livingworld.application.chat_capacity import ContextPacker
from livingworld.application.chat_context import DirectChatContextBuilder
from livingworld.application.chat_timeline import recent_timeline
from livingworld.application.llm import InvocationId, LLMPurpose, LLMRequest, ModelRef, ProviderId
from livingworld.domain.contracts import RequestId
from livingworld.infrastructure.persistence.models import ChatMessageRecord
from test_group_chat_reply import _environment


def bodies(context):
    return "\n".join(part.text for message in context.messages for part in message.content)


def packer(context):
    request = LLMRequest(
        invocation_id=InvocationId(uuid4()),
        model=ModelRef(ProviderId("fixture"), "fixture"),
        purpose=LLMPurpose("character_dialogue"),
        messages=context.messages,
        max_output_tokens=100,
    )
    return ContextPacker(request, context.layout)


def fitted(context):
    return packer(context).render()


async def direct(messages, conversation, question, answer=None, *, memories=()):
    sent = await messages.send_player(
        RequestId(uuid4()), conversation.conversation_id, question, 50000
    )
    if answer:
        claim = await messages.claim_direct(conversation.conversation_id, sent.turn_id)
        await messages.complete_direct(claim, answer, memories=memories)
    return sent


@pytest.mark.parametrize("target_kind", ["group", "direct"])
def test_recent_context_is_chronological_without_long_memory_and_keeps_current_audience(
    tmp_path, target_kind
):
    async def run():
        db, group, messages, context = await _environment(tmp_path)
        try:
            first, second = group.participants
            one = await context._conversations.open_direct(
                group.conversation_id.world_id, first.root_import_id
            )
            two = await context._conversations.open_direct(
                group.conversation_id.world_id, second.root_import_id
            )
            await direct(messages, one, "以后请叫我 A。", "好，以后就叫你 A。")
            await direct(messages, two, "OTHER_ROLE_PRIVATE_CANARY", "OTHER_ROLE_REPLY_CANARY")
            sent = await messages.send_group_player(
                RequestId(uuid4()), group.conversation_id, "我们还在外面吃饭。", 50000
            )
            claim = await messages.claim_group(group.conversation_id, sent.turn_id)
            await messages.complete_group_reply(claim, first.character_id, 0, "吃完再去逛逛。")
            await messages.finish_group(claim)
            if target_kind == "group":
                latest = await messages.send_group_player(
                    RequestId(uuid4()), group.conversation_id, "你应该叫我什么？", 50000
                )
                built = await context.build_reply(latest, first.character_id)
            else:
                latest = await direct(messages, one, "你应该叫我什么？")
                builder = DirectChatContextBuilder(
                    context._conversations,
                    messages,
                    db.local_profile_store(),
                    db.character_memory_reader,
                )
                built = await builder.build(latest)
            assert context._long_memory is None
            packed = fitted(built)
            text = bodies(packed)
            assert (
                text.index("以后请叫我 A。")
                < text.index("好，以后就叫你 A。")
                < text.index("我们还在外面吃饭。")
                < text.index("吃完再去逛逛。")
                < text.rindex("你应该叫我什么？")
            )
            assert "OTHER_ROLE_PRIVATE_CANARY" not in text
            assert "OTHER_ROLE_REPLY_CANARY" not in text
            data = json.loads(packed.messages[1].content[0].text)
            assert data["current_conversation"]["kind"] == target_kind
            assert len(data["current_conversation"]["characters"]) == (
                2 if target_kind == "group" else 1
            )
            assert "不把多人对话当作与玩家单独相处" in text
            assert "【其他会话历史来源】" in text
            packing = packer(built)
            while packing.available:
                packing.drop_batch()
                reduced = bodies(packing.render())
                assert "你应该叫我什么？" in reduced
                assert ("以后请叫我 A。" in reduced) == ("好，以后就叫你 A。" in reduced)
                assert ("我们还在外面吃饭。" in reduced) == ("吃完再去逛逛。" in reduced)
            # Other group speakers receive no copy of the first role's private exchange.
            group_view = await context.build_reply(sent, second.character_id)
            assert "以后请叫我 A。" not in bodies(fitted(group_view))
        finally:
            await db.close()

    asyncio.run(run())


def test_later_messages_do_not_enter_an_earlier_generation_or_selector(tmp_path):
    async def run():
        db, group, messages, context = await _environment(tmp_path)
        try:
            person = group.participants[0]
            one = await context._conversations.open_direct(
                group.conversation_id.world_id, person.root_import_id
            )
            await direct(messages, one, "EARLIER_PRIVATE", "EARLIER_ANSWER")
            sent = await messages.send_group_player(
                RequestId(uuid4()), group.conversation_id, "CURRENT_GROUP", 50000
            )
            await direct(messages, one, "FUTURE_PRIVATE", "FUTURE_ANSWER")
            reply = bodies(fitted(await context.build_reply(sent, person.character_id)))
            assert "EARLIER_PRIVATE" in reply and "FUTURE_PRIVATE" not in reply
            selection = bodies(await context.build_selection(sent))
            assert "CURRENT_GROUP" in selection
            assert "EARLIER_PRIVATE" not in selection and "FUTURE_PRIVATE" not in selection
        finally:
            await db.close()

    asyncio.run(run())


@pytest.mark.parametrize("operation", ["branch", "edit"])
def test_inactive_private_routes_are_filtered_before_merge(tmp_path, operation):
    from test_chat_paths import mutate

    async def run():
        db, group, messages, context = await _environment(tmp_path)
        try:
            person = group.participants[0]
            one = await context._conversations.open_direct(
                group.conversation_id.world_id, person.root_import_id
            )
            first = await direct(messages, one, "VISIBLE_QUESTION", "VISIBLE_ANSWER")
            hidden = await direct(messages, one, "INACTIVE_PRIVATE", "INACTIVE_REPLY")
            await mutate(
                db.chat_path_store(),
                one,
                operation,
                message_id=first.message.message_id.value,
                **({"text": "EDITED_VISIBLE_QUESTION"} if operation == "edit" else {}),
            )
            sent = await messages.send_group_player(
                RequestId(uuid4()), group.conversation_id, "GROUP_QUESTION", 50000
            )
            text = bodies(fitted(await context.build_reply(sent, person.character_id)))
            assert (
                "EDITED_VISIBLE_QUESTION" if operation == "edit" else "VISIBLE_QUESTION"
            ) in text
            assert hidden.message.text not in text and "INACTIVE_REPLY" not in text
        finally:
            await db.close()

    asyncio.run(run())


def test_equal_timestamps_preserve_message_order_and_cutoff(tmp_path):
    async def run():
        db, group, messages, context = await _environment(tmp_path)
        try:
            person = group.participants[0]
            one = await context._conversations.open_direct(
                group.conversation_id.world_id, person.root_import_id
            )
            old = await direct(messages, one, "SAME_TIME_QUESTION", "SAME_TIME_ANSWER")
            sent = await messages.send_group_player(
                RequestId(uuid4()), group.conversation_id, "CURRENT", 50000
            )
            async with db._sessions() as session, session.begin():
                from sqlalchemy import update

                await session.execute(
                    update(ChatMessageRecord)
                    .where(ChatMessageRecord.conversation_id == one.conversation_id.value)
                    .values(created_at_utc=sent.message.created_at_utc - timedelta(seconds=1))
                )
            entries = await messages.recent_dialogue(person.character_id, sent.message)
            assert {entry.message.turn_id for entry in entries} == {old.turn_id}
            text = bodies(fitted(await context.build_reply(sent, person.character_id)))
            assert (
                text.index("SAME_TIME_QUESTION")
                < text.index("SAME_TIME_ANSWER")
                < text.rindex("CURRENT")
            )
        finally:
            await db.close()

    asyncio.run(run())


@pytest.mark.parametrize("state", ["active", "forgotten"])
def test_excluded_memory_source_is_not_reintroduced_as_recent_private_dialogue(tmp_path, state):
    from livingworld.application.long_chat_memory import MemoryAnnotation
    from livingworld.infrastructure.persistence.long_memory_models import LongChatMemoryRecord
    from sqlalchemy import update

    async def run():
        db, group, messages, context = await _environment(tmp_path)
        try:
            person = group.participants[0]
            one = await context._conversations.open_direct(
                group.conversation_id.world_id, person.root_import_id
            )
            await direct(
                messages,
                one,
                "请记住我的称呼是 A。",
                "我会称呼你为 A。",
                memories=(
                    MemoryAnnotation(
                        kind="identity",
                        topic="称呼",
                        content="玩家希望被称为 A。",
                        source="player",
                        quote="请记住我的称呼是 A。",
                    ),
                ),
            )
            async with db._sessions() as session, session.begin():
                await session.execute(update(LongChatMemoryRecord).values(state=state))
            sent = await messages.send_group_player(
                RequestId(uuid4()), group.conversation_id, "GROUP_QUESTION", 50000
            )
            text = bodies(fitted(await context.build_reply(sent, person.character_id)))
            assert ("请记住我的称呼是 A。" in text) == (state == "active")
            assert ("我会称呼你为 A。" in text) == (state == "active")
        finally:
            await db.close()

    asyncio.run(run())


def test_recent_window_drops_whole_turns_and_preserves_current_turn(tmp_path):
    async def run():
        from livingworld.application.chat_messages import RecentDialogue
        from livingworld.domain.identifiers import ChatTurnId, MessageId

        db, group, messages, context = await _environment(tmp_path)
        try:
            person = group.participants[0]
            sent = await messages.send_group_player(
                RequestId(uuid4()), group.conversation_id, "CURRENT", 50000
            )
            base = sent.message
            past = []
            for n in range(80):
                turn = ChatTurnId(base.conversation_id.world_id, uuid4())
                for reply in (False, True):
                    item = replace(
                        base,
                        message_id=MessageId(base.conversation_id.world_id, uuid4()),
                        turn_id=turn,
                        position=n * 2 + int(reply),
                        created_at_utc=base.created_at_utc - timedelta(seconds=100 - n),
                        text=f"turn-{n}-{'reply' if reply else 'question'}",
                        sender_id=person.character_id if reply else base.sender_id,
                    )
                    past.append(RecentDialogue(item, "direct"))
            result = await recent_timeline(
                SimpleNamespace(recent_dialogue=AsyncMock(return_value=tuple(past))),
                person.character_id,
                base,
                (base,),
            )
            assert len(result) <= 128 and result[-1].message == base
            for n in range(80):
                assert sum(e.message.text.startswith(f"turn-{n}-") for e in result) in (0, 2)
        finally:
            await db.close()

    asyncio.run(run())
