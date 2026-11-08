"""Private replies use one classified body; retired transport tags never become dialogue."""

import asyncio
import json
from dataclasses import replace
from uuid import uuid4

import pytest
from livingworld.adapters.http.chat_messages import _view
from livingworld.application.chat_event_annotations import (
    DialogueFormatError,
    annotate_request,
    completed_dialogue,
    decode_optional_dialogue,
)
from livingworld.application.chat_privacy import (
    boundaries,
    rebase_reply_parts,
    strip_internal_markers,
    visible_text,
)
from livingworld.application.chat_reply import ChatReplyValidationError
from livingworld.application.group_chat_reply import GroupChatReplyService
from livingworld.application.llm import FinishReason
from livingworld.application.long_chat_memory import MemoryAnnotation
from livingworld.domain.contracts import RequestId
from livingworld.infrastructure.persistence.long_chat_memory import SqlAlchemyLongChatMemoryStore
from livingworld.infrastructure.persistence.long_memory_models import LongChatMemoryRecord
from livingworld.infrastructure.persistence.models import ChatMessageRecord
from sqlalchemy import select
from test_chat_privacy import span_for
from test_chat_reply_formats import _Gateway, _request, _run
from test_group_chat_reply import _environment
from test_recent_dialogue import bodies, fitted
from test_scheduler_model import RecordingProvider, route

START, END = "【仅你与玩家可见】", "【私密片段结束】"


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("tail", ["}", ',"memories":[', ',"memories":broken}'])
@pytest.mark.parametrize("finish", [FinishReason.STOP, FinishReason.OUTPUT_LIMIT])
def test_complete_private_parts_survive_bad_auxiliary_tail_and_output_limit(
    streaming, tail, finish
):
    raw = (
        '{"reply_parts":'
        + json.dumps([{"text": "私下😀。", "private": True}, {"text": "公开。", "private": False}])
        + tail
    )
    gateway = _Gateway(raw, finish)
    request = annotate_request(_request(streaming), private=True)
    result = asyncio.run(_run(gateway, request, []))
    assert result.text == "私下😀。公开。"
    assert result.privacy_parts == (
        {"text": "私下😀。", "private": True},
        {"text": "公开。", "private": False},
    )
    assert result.memories == () and result.events == () and result.media is None
    assert gateway.calls == 1


@pytest.mark.parametrize(
    "raw",
    [
        '{"reply_parts":[{"text":"没写完',
        '{"reply_parts":[{"text":"一段完整","private":true},',
        '{"reply_parts":[{"text":"一段完整","private":true}',
        '{"reply_parts":[{"text":"重复","text":"另一条","private":true}],"memories":[',
        '{"reply_parts":[{"text":"完整","private":true}],"memories":broken,"reply_parts":[]}',
        '{"reply_parts":[{"text":"完整","private":true}]}unexpected',
    ],
)
def test_private_recovery_rejects_incomplete_or_ambiguous_body_without_replay(raw):
    assert completed_dialogue(raw, private=True) is None
    gateway = _Gateway(raw, FinishReason.OUTPUT_LIMIT)
    with pytest.raises(ChatReplyValidationError, match="chat_reply_output_limit"):
        asyncio.run(_run(gateway, annotate_request(_request(False), private=True), []))
    assert gateway.calls == 1


def test_recovered_bad_classification_is_private_and_literal_newlines_remain_exact():
    raw = '{"reply_parts":[{"text":"第一段\n第二段","private":"false"}],"memories":broken}'
    result = decode_optional_dialogue(raw, private=True)
    assert result.text == "第一段\n第二段" and result.privacy_parts is None


def test_recovered_private_body_persists_audiences_and_stays_hidden_from_other_member(tmp_path):
    async def run():
        db, group, messages, context = await _environment(tmp_path)
        try:
            one, two = group.participants
            raw = (
                '{"reply_parts":'
                + json.dumps(
                    [
                        {"text": "PRIVATE_RECOVERED", "private": True},
                        {"text": "PUBLIC_RECOVERED", "private": False},
                    ]
                )
                + ',"memories":broken}'
            )
            provider, selector = RecordingProvider((raw,)), RecordingProvider(("STOP",))
            service = GroupChatReplyService(
                messages,
                context,
                *route(provider, "body"),
                scheduler_configuration=route(selector, "scheduler"),
                event_capture=True,
            )
            secret = f"@{one.character_name}（低声）PRIVATE_INPUT。"
            sent = await messages.send_group_player(
                RequestId(uuid4()),
                group.conversation_id,
                secret + "PUBLIC_INPUT。",
                50000,
                privacy=span_for(secret, one),
            )
            reply = (await service.reply(sent)).replies[0]
            saved = await messages.group_turn(group.conversation_id, sent.turn_id)
            assert saved.replies[0] == reply and saved.state == "completed"
            assert visible_text(reply.text, reply.privacy) == "PUBLIC_RECOVERED"
            visible = bodies(fitted(await context.build_reply(sent, two.character_id)))
            assert "PRIVATE_RECOVERED" not in visible and "PUBLIC_RECOVERED" in visible
            assert provider.calls == 1 and selector.calls == 1
        finally:
            await db.close()

    asyncio.run(run())


def envelope(parts):
    return json.dumps({"reply_parts": parts, "memories": []}, ensure_ascii=False)


@pytest.mark.parametrize("with_private_reply", [False, True])
def test_public_actions_after_private_input_keep_their_audience_through_save_and_history(
    tmp_path, with_private_reply
):
    async def run():
        db, group, messages, context = await _environment(tmp_path)
        try:
            one, two = group.participants
            public_before = "她拿起菜单，"
            private = "只让你听见地说：‘PRIVATE_REPLY_CANARY。’"
            public_after = "随后向大家问：‘还要加菜吗？’"
            parts = [{"text": public_before, "private": False}]
            if with_private_reply:
                parts.append({"text": private, "private": True})
            parts.append({"text": public_after, "private": False})
            provider = RecordingProvider((envelope(parts),))
            selector = RecordingProvider(("STOP",))
            service = GroupChatReplyService(
                messages,
                context,
                *route(provider, "body"),
                scheduler_configuration=route(selector, "scheduler"),
                event_capture=True,
            )
            source = f"@{one.character_name}（秘密动作）PRIVATE_INPUT_CANARY。"
            sent = await messages.send_group_player(
                RequestId(uuid4()),
                group.conversation_id,
                source + "大家继续吃饭。",
                50000,
                privacy=span_for(source, one),
            )
            reply = (await service.reply(sent)).replies[0]
            assert (
                reply.text == public_before + (private if with_private_reply else "") + public_after
            )
            assert reply.privacy_fallback is False
            assert visible_text(reply.text, reply.privacy) == public_before + public_after
            if with_private_reply:
                assert reply.privacy == (
                    {
                        "start": max(boundaries(public_before)),
                        "end": max(boundaries(public_before + private)),
                        "character_id": str(one.character_id.value),
                    },
                )
            else:
                assert reply.privacy == ()
            assert (await messages.list_messages(group.conversation_id))[-1] == reply
            public_context = bodies(fitted(await context.build_reply(sent, two.character_id)))
            assert "PRIVATE_INPUT_CANARY" not in public_context
            assert "PRIVATE_REPLY_CANARY" not in public_context
            assert public_before in public_context and public_after in public_context
            own_context = bodies(fitted(await context.build_reply(sent, one.character_id)))
            assert ("PRIVATE_REPLY_CANARY" in own_context) is with_private_reply
            assert provider.calls == 1 and selector.calls == 1
        finally:
            await db.close()

    asyncio.run(run())


@pytest.mark.parametrize("classification", ["mixed", "private", "missing", "invalid"])
def test_private_reply_fallback_provenance_survives_reload_and_context_projection(
    tmp_path, classification
):
    async def run():
        db, group, messages, context = await _environment(tmp_path)
        try:
            one, two = group.participants
            parts = (
                [
                    {"text": "PUBLIC_PREFIX。", "private": False},
                    {"text": "SECRET😀。", "private": True},
                    {"text": "PUBLIC_SUFFIX。", "private": False},
                ]
                if classification == "mixed"
                else [{"text": "SECRET😀。", "private": True}]
            )
            raw = envelope(parts)
            if classification == "missing":
                raw = json.dumps({"reply": "SECRET😀。"})
            elif classification == "invalid":
                raw = envelope([{"text": "SECRET😀。", "private": "yes"}])
            provider, selector = RecordingProvider((raw,)), RecordingProvider(("STOP",))
            service = GroupChatReplyService(
                messages,
                context,
                *route(provider, "body"),
                scheduler_configuration=route(selector, "scheduler"),
                event_capture=True,
            )
            secret = f"@{one.character_name} PRIVATE_INPUT。"
            sent = await messages.send_group_player(
                RequestId(uuid4()),
                group.conversation_id,
                secret + "PUBLIC_INPUT。",
                50000,
                privacy=span_for(secret, one),
            )
            reply = (await service.reply(sent)).replies[0]
            fallback = classification in {"missing", "invalid"}
            assert reply.privacy_fallback is fallback
            loaded = (await messages.list_messages(group.conversation_id))[-1]
            assert loaded == reply and _view(loaded)["privacy_fallback"] is fallback
            public = visible_text(loaded.text, loaded.privacy)
            assert public == ("PUBLIC_PREFIX。PUBLIC_SUFFIX。" if classification == "mixed" else "")
            assert "SECRET" not in bodies(fitted(await context.build_reply(sent, two.character_id)))
            own = bodies(fitted(await context.build_reply(sent, one.character_id)))
            assert "SECRET" in own and "privacy_fallback" not in own
            assert provider.calls == 1 and selector.calls == 1
        finally:
            await db.close()

    asyncio.run(run())


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("finish", [FinishReason.STOP, FinishReason.OUTPUT_LIMIT])
@pytest.mark.parametrize("private", [False, True, "invalid"])
def test_ordinary_group_accepts_segmented_body_without_revealing_private_parts(
    streaming, finish, private
):
    request = _request(streaming)
    request = replace(request, metadata={**request.metadata, "chat_kind": "group"})
    gateway = _Gateway(envelope([{"text": "完整角色正文", "private": private}]), finish)
    progress = []
    result = asyncio.run(_run(gateway, request, progress))
    assert result.text == "完整角色正文"
    assert result.private_context is (private is not False)
    if private is not False:
        assert not any(event.kind == "delta" for event in progress)
    assert gateway.calls == 1


@pytest.mark.parametrize("legacy", [False, True])
def test_ordinary_group_segmented_reply_preserves_audiences_after_save_and_reload(tmp_path, legacy):
    async def run():
        db, group, messages, context = await _environment(tmp_path)
        try:
            one, two = group.participants
            parts = [
                {"text": "PRIVATE_FROM_MODEL", "private": True},
                {"text": "PUBLIC_FROM_MODEL", "private": False},
            ]
            raw = (
                json.dumps({"reply": "PRIVATE_FROM_MODELPUBLIC_FROM_MODEL", "privacy_parts": parts})
                if legacy
                else envelope(parts)
            )
            provider, selector = RecordingProvider((raw,)), RecordingProvider(("STOP",))
            service = GroupChatReplyService(
                messages,
                context,
                *route(provider, "body"),
                scheduler_configuration=route(selector, "scheduler"),
                event_capture=True,
            )
            sent = await messages.send_group_player(
                RequestId(uuid4()),
                group.conversation_id,
                f"@{one.character_name} PUBLIC_QUESTION",
                50000,
            )
            assert not (await context.build_reply(sent, one.character_id)).private_context
            reply = (await service.reply(sent)).replies[0]
            assert visible_text(reply.text, reply.privacy) == "PUBLIC_FROM_MODEL"
            assert (
                visible_text(reply.text, reply.privacy, one.character_id)
                == "PRIVATE_FROM_MODELPUBLIC_FROM_MODEL"
            )
            saved = await messages.group_turn(group.conversation_id, sent.turn_id)
            assert saved.state == "completed" and saved.replies[0].privacy == reply.privacy
            other = bodies(fitted(await context.build_reply(sent, two.character_id)))
            assert "PRIVATE_FROM_MODEL" not in other and "PUBLIC_FROM_MODEL" in other
            assert provider.calls == 1 and selector.calls == 1
        finally:
            await db.close()

    asyncio.run(run())


def test_public_segmented_group_reply_keeps_public_memory_capture(tmp_path):
    async def run():
        db, group, messages, context = await _environment(tmp_path)
        try:
            one = group.participants[0]
            raw = json.dumps(
                {
                    "reply_parts": [{"text": "我偏好茶。", "private": False}],
                    "memories": [
                        {
                            "kind": "preference",
                            "topic": "饮品",
                            "content": "角色偏好茶",
                            "source": "reply",
                            "quote": "我偏好茶",
                        }
                    ],
                }
            )
            provider, selector = RecordingProvider((raw,)), RecordingProvider(("STOP",))
            service = GroupChatReplyService(
                messages,
                context,
                *route(provider, "body"),
                scheduler_configuration=route(selector, "scheduler"),
                event_capture=True,
            )
            sent = await messages.send_group_player(
                RequestId(uuid4()),
                group.conversation_id,
                f"@{one.character_name} PUBLIC_QUESTION",
                50000,
            )
            reply = (await service.reply(sent)).replies[0]
            assert reply.text == "我偏好茶。" and reply.privacy == ()
            async with db._sessions() as session:
                row = await session.scalar(
                    select(ChatMessageRecord).where(
                        ChatMessageRecord.message_id == reply.message_id.value
                    )
                )
                assert row.privacy_json is None
                memories = (await session.scalars(select(LongChatMemoryRecord))).all()
                assert {m.character_id for m in memories} == {
                    p.character_id.value for p in group.participants
                }
        finally:
            await db.close()

    asyncio.run(run())


@pytest.mark.parametrize("private", [True, False])
def test_ordinary_group_defers_legacy_json_until_its_audience_is_known(private):
    request = _request(True)
    request = replace(request, metadata={**request.metadata, "chat_kind": "group"})
    raw = json.dumps(
        {"reply": "完整角色正文", "privacy_parts": [{"text": "完整角色正文", "private": private}]}
    )
    progress = []
    result = asyncio.run(_run(_Gateway(raw, FinishReason.STOP), request, progress))
    deltas = [event.text for event in progress if event.kind == "delta"]
    assert result.text == "完整角色正文" and result.private_context is private
    assert deltas == ([] if private else ["完整角色正文"])


@pytest.mark.parametrize("fenced", [False, True])
def test_segmented_body_requires_an_audience_aware_decoder(fenced):
    raw = envelope(
        [{"text": "私下回应。", "private": True}, {"text": "公开回应。", "private": False}]
    )
    if fenced:
        raw = "```json\n" + raw + "\n```"
    decoded = decode_optional_dialogue(raw, private=True)
    assert decoded.text == "私下回应。公开回应。"
    assert len(decoded.privacy_parts) == 2
    with pytest.raises(DialogueFormatError, match="chat_reply_invalid"):
        decode_optional_dialogue(raw)


@pytest.mark.parametrize(
    "part",
    [
        {"text": "正文", "private": "false"},
        {"text": "正文", "private": False, "audience": "all"},
        {"text": 1, "private": False},
    ],
)
def test_malformed_parts_cannot_turn_a_fallback_body_public(part):
    if isinstance(part["text"], str):
        fallback = decode_optional_dialogue(envelope([part]), private=True)
        assert fallback.text == part["text"] and fallback.privacy_parts is None
    else:
        with pytest.raises(DialogueFormatError):
            decode_optional_dialogue(envelope([part]), private=True)
    decoded = decode_optional_dialogue(
        json.dumps({"reply": "保留的完整正文", "reply_parts": [part]}, ensure_ascii=False),
        private=True,
    )
    assert decoded.text == "保留的完整正文" and decoded.privacy_parts is None


def test_known_header_removal_rebases_parts_without_changing_audiences():
    parts = (
        {"text": "协议头：", "private": True},
        {"text": "私密。", "private": True},
        {"text": "公开。", "private": False},
    )
    assert rebase_reply_parts("协议头：私密。公开。", "私密。公开。", parts) == parts[1:]
    assert rebase_reply_parts("协议头：私密。公开。", "未知变化", parts) is None


def test_truncated_legacy_classification_keeps_complete_body_conservatively():
    decoded = decode_optional_dialogue(
        '{"reply":"完整正文。","privacy_parts":[{"text":"未完成', private=True
    )
    assert decoded.text == "完整正文。" and decoded.privacy_parts is None


def test_marker_cleanup_preserves_unicode_private_boundaries():
    owner = "11111111-1111-4111-8111-111111111111"
    before = "公开😀" + START + START + "秘密😀" + END + "仍公开"
    start = max(boundaries("公开😀"))
    end = max(boundaries(before.removesuffix("仍公开")))
    text, spans = strip_internal_markers(
        before, ({"start": start, "end": end, "character_id": owner},)
    )
    assert text == "公开😀秘密😀仍公开"
    assert visible_text(text, spans) == "公开😀仍公开"
    assert visible_text(text, spans, owner) == text


@pytest.mark.parametrize("header", [False, True])
def test_mixed_private_reply_and_later_public_reply_do_not_stay_all_gray(tmp_path, header):
    async def run():
        db, group, messages, context = await _environment(tmp_path)
        try:
            one, two = group.participants
            prefix = (
                f"{one.character_name}（发言者标识：{one.character_id.value}）：\n"
                if header
                else ""
            )
            parts = ([{"text": prefix, "private": True}] if prefix else []) + [
                {"text": "PRIVATE_REPLY。", "private": True},
                {"text": "PUBLIC_REPLY。", "private": False},
            ]
            provider = RecordingProvider(
                (envelope(parts), envelope([{"text": "PUBLIC_AGAIN。", "private": False}]))
            )
            selector = RecordingProvider(("STOP", "STOP"))
            service = GroupChatReplyService(
                messages,
                context,
                *route(provider, "body"),
                scheduler_configuration=route(selector, "scheduler"),
                event_capture=True,
            )
            secret = f"@{one.character_name}（低声）PRIVATE_INPUT。"
            sent = await messages.send_group_player(
                RequestId(uuid4()),
                group.conversation_id,
                secret + "PUBLIC_INPUT。",
                50000,
                privacy=span_for(secret, one),
            )
            first = (await service.reply(sent)).replies[0]
            assert first.text == "PRIVATE_REPLY。PUBLIC_REPLY。"
            assert visible_text(first.text, first.privacy) == "PUBLIC_REPLY。"
            public = await messages.send_group_player(
                RequestId(uuid4()),
                group.conversation_id,
                f"@{one.character_name} PUBLIC_NEXT。",
                50000,
            )
            second = (await service.reply(public)).replies[0]
            assert second.text == "PUBLIC_AGAIN。" and second.privacy == ()
            for request in provider.requests:
                system = " ".join(
                    block.text
                    for message in request.messages
                    if message.role.value == "system"
                    for block in message.content
                )
                assert "必须使用分段JSON" in system
                assert "可以直接输出角色正文" not in system
                assert "这段新回复本身的可见／可听范围" in system
                assert "不能仅因与私密交流有关就连带遮住" in system
                assert "不把局部不确定扩大为整段或整条私密" in system
                assert "玩家已标私密的动作与话语保持原受众" in system
                assert "对私下话语的回应、仅双方知道的动作和心理" not in system
                all_text = " ".join(
                    block.text for message in request.messages for block in message.content
                )
                assert START not in all_text and END not in all_text
            for request in selector.requests:
                text = " ".join(
                    block.text for message in request.messages for block in message.content
                )
                assert "PRIVATE_INPUT" not in text and "PRIVATE_REPLY" not in text
            next_context = bodies(fitted(await context.build_reply(public, two.character_id)))
            assert "PRIVATE_INPUT" not in next_context and "PRIVATE_REPLY" not in next_context
            assert provider.calls == 2 and selector.calls == 2
        finally:
            await db.close()

    asyncio.run(run())


def test_unclassified_echo_is_cleaned_but_stays_private(tmp_path):
    async def run():
        db, group, messages, context = await _environment(tmp_path)
        try:
            one = group.participants[0]
            provider, selector = (
                RecordingProvider((START + START + "完整回应。" + END,)),
                RecordingProvider(("STOP",)),
            )
            service = GroupChatReplyService(
                messages,
                context,
                *route(provider, "body"),
                scheduler_configuration=route(selector, "scheduler"),
            )
            secret = f"@{one.character_name} 私下问题。"
            sent = await messages.send_group_player(
                RequestId(uuid4()),
                group.conversation_id,
                secret + "公开问题。",
                50000,
                privacy=span_for(secret, one),
            )
            reply = (await service.reply(sent)).replies[0]
            assert reply.text == "完整回应。" and reply.privacy
            assert visible_text(reply.text, reply.privacy) == ""
            async with db._sessions() as session:
                row = await session.get(
                    ChatMessageRecord, (reply.message_id.world_id.value, reply.message_id.value)
                )
                assert row.text == "完整回应。"
            assert provider.calls == 1
        finally:
            await db.close()

    asyncio.run(run())


def test_old_private_record_is_cleaned_for_display_and_context_without_rewriting_save(tmp_path):
    async def run():
        db, group, messages, context = await _environment(tmp_path)
        try:
            one, two = group.participants
            secret = f"@{one.character_name} 旧私密问题。"
            sent = await messages.send_group_player(
                RequestId(uuid4()),
                group.conversation_id,
                secret + "公开问题。",
                50000,
                privacy=span_for(secret, one),
            )
            claim = await messages.claim_group(group.conversation_id, sent.turn_id)
            private_body = START + START + "SECRET😀" + END
            original = "PUBLIC_PRE" + private_body + "PUBLIC_POST"
            spans = (
                {
                    "start": len("PUBLIC_PRE"),
                    "end": max(boundaries("PUBLIC_PRE" + private_body)),
                    "character_id": str(one.character_id.value),
                },
            )
            reply = await messages.complete_group_reply(
                claim,
                one.character_id,
                0,
                original,
                privacy=spans,
                memories=(
                    MemoryAnnotation(
                        kind="experience",
                        topic="旧来源",
                        content=START + "OLD_MEMORY" + END,
                        source="reply",
                        quote="SECRET😀",
                        replaces=None,
                    ),
                ),
            )
            await messages.finish_group(claim)
            async with db._sessions() as session:
                before = (
                    await session.execute(
                        select(ChatMessageRecord.text, ChatMessageRecord.privacy_json).where(
                            ChatMessageRecord.message_id == reply.message_id.value
                        )
                    )
                ).one()
                assert before.text == original
            loaded = (await messages.list_messages(group.conversation_id))[-1]
            assert _view(loaded)["text"] == "PUBLIC_PRESECRET😀PUBLIC_POST"
            assert visible_text(loaded.text, loaded.privacy) == "PUBLIC_PREPUBLIC_POST"
            public = await messages.send_group_player(
                RequestId(uuid4()), group.conversation_id, "PUBLIC_NOW", 50000
            )
            for person in (one, two):
                rendered = bodies(fitted(await context.build_reply(public, person.character_id)))
                assert START not in rendered and END not in rendered
                assert ("SECRET😀" in rendered) == (person == one)

            class Ranker:
                async def query_terms(self, query):
                    return tuple(query.split())

                async def rank_queries(self, queries, candidates, *, limit):
                    return candidates[:limit]

            memory = await SqlAlchemyLongChatMemoryStore(db._sessions, Ranker()).for_character(
                group.conversation_id, group.player_id, one.character_id, public.message
            )
            assert "OLD_MEMORY" in json.dumps(memory, ensure_ascii=False)
            assert START not in json.dumps(memory, ensure_ascii=False)
            async with db._sessions() as session:
                after = (
                    await session.execute(
                        select(ChatMessageRecord.text, ChatMessageRecord.privacy_json).where(
                            ChatMessageRecord.message_id == reply.message_id.value
                        )
                    )
                ).one()
                assert before == after
                raw_memory = (await session.scalars(select(LongChatMemoryRecord))).one()
                assert START in raw_memory.content
        finally:
            await db.close()

    asyncio.run(run())
