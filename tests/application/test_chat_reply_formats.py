"""Synthetic dialogue formats and mocked transport only; no DB, credentials or providers."""

import asyncio
import json
from dataclasses import replace
from uuid import uuid4

import pytest
from livingworld.application.chat_event_annotations import (
    AnnotatedDialogue,
    DialogueFormatError,
    annotate_request,
    completed_reply,
    decode_dialogue,
    decode_optional_dialogue,
)
from livingworld.application.chat_reply import ChatReplyValidationError, dialogue_text
from livingworld.application.llm import (
    FinishReason,
    InvocationId,
    LLMMessage,
    LLMPurpose,
    LLMRequest,
    LLMResponse,
    LLMStreamCompletion,
    MessageRole,
    ModelRef,
    ProviderId,
    StreamCompleted,
    TextContent,
    TextDelta,
)
from livingworld.application.llm_chat_turn_budget import ChatTurnTokenBudget
from livingworld.domain.identifiers import CharacterId, WorldId


@pytest.mark.parametrize(
    "body",
    [
        "[她放下茶杯，望向窗外。]“你来了。”",
        "{她推开窗户。}“外面下雨了。”",
        '*她写下 "reply": 这个单词，然后抬起头。*',
        "```text\n[她轻轻敲门。]\n```",
        "```\n*她向你挥手。*\n```",
        "[“第一句话”, “第二句话”]",
        "“你好。”\n\n*她转过身，披上外套。*",
    ],
)
def test_narrative_is_preserved_verbatim_without_metadata(body):
    result = decode_optional_dialogue(body)
    assert result == AnnotatedDialogue(body)


@pytest.mark.parametrize("fence", [False, True])
def test_complete_reply_and_valid_metadata_are_retained(fence):
    reply = "“明天见。”\n*她合上书，挥了挥手。*"
    document = {
        "reply": reply,
        "events": [{"kind": "plan", "title": "见面", "quote": "明天见", "time_text": "明天"}],
        "memories": [],
    }
    raw = json.dumps(document, ensure_ascii=False)
    if fence:
        raw = "```json\n" + raw + "\n```"
    result = decode_optional_dialogue(raw)
    assert result.text == reply
    assert len(result.events) == 1
    assert result.events[0].quote == "明天见"


@pytest.mark.parametrize(
    "tail",
    [
        "",
        ', "events": [',
        ', "events": broken}',
        ', "memories": [{"content": "unfinished',
        ', "media": {"intent": "unfinished',
    ],
)
def test_broken_auxiliary_syntax_does_not_lose_complete_body(tail):
    reply = "“路径是 C:\\合成资料。”\n*她笑了笑。*"
    raw = '{"reply":' + json.dumps(reply, ensure_ascii=False) + tail
    assert decode_optional_dialogue(raw) == AnnotatedDialogue(reply)
    assert completed_reply(raw) == reply


def test_literal_newline_is_decoded_without_inventing_or_truncating_body():
    raw = '{"reply":"第一段。\n第二段。", "events": []}'
    assert decode_optional_dialogue(raw) == AnnotatedDialogue("第一段。\n第二段。")


def test_outer_bom_and_whitespace_do_not_expose_transport_fields():
    raw = '\ufeff \n {"reply":"完整正文", "events":[]}'
    assert decode_optional_dialogue(raw) == AnnotatedDialogue("完整正文")


def test_invalid_auxiliary_values_are_ignored_without_leaking_fields():
    raw = json.dumps({"reply": "*她微笑。*", "events": "broken", "memories": 7, "media": {}})
    assert decode_optional_dialogue(raw) == AnnotatedDialogue("*她微笑。*")


@pytest.mark.parametrize(
    "raw",
    [
        '{"reply":"没有结束',
        '{"reply":"未完成的转义\\',
        '{"reply":"她说"你好"。", "events":[]}',
        '{"reply":"", "events":[',
        '{"reply":null, "events":[]}',
        '{"events":[], "memories":[]}',
        '[{"reply":"不能把数组当正文"}]',
        '{"reply":"第一条", "reply":"第二条"}',
        '{"reply":"第一条", "events": broken, "reply":"第二条"}',
        '{"reply":"\\ud800", "events":[]}',
        '{"reply":"有效正文", "events": NaN}',
    ],
)
def test_incomplete_ambiguous_or_invalid_envelopes_are_not_shown_as_text(raw):
    with pytest.raises(DialogueFormatError):
        decode_optional_dialogue(raw)


def test_strict_structured_contract_is_not_replaced_by_optional_recovery():
    with pytest.raises(DialogueFormatError):
        decode_dialogue('{"reply":"完整正文", "events": broken}')
    with pytest.raises(DialogueFormatError):
        decode_dialogue("[她微笑。]")


class _Gateway:
    def __init__(self, raw, finish):
        self.raw, self.finish, self.calls = raw, finish, 0

    async def generate(self, request, **_):
        self.calls += 1
        return LLMResponse(
            invocation_id=request.invocation_id,
            model_used=request.model,
            content=(TextContent(self.raw),),
            finish_reason=self.finish,
        )

    async def stream(self, request, **_):
        self.calls += 1
        for index in range(0, len(self.raw), 3):
            yield TextDelta(request.invocation_id, self.raw[index : index + 3])
        yield StreamCompleted(
            LLMStreamCompletion(
                invocation_id=request.invocation_id,
                model_used=request.model,
                finish_reason=self.finish,
            )
        )


def _request(streaming):
    return annotate_request(
        LLMRequest(
            invocation_id=InvocationId(uuid4()),
            model=ModelRef(ProviderId("synthetic"), "mock-dialogue"),
            purpose=LLMPurpose("character_dialogue"),
            messages=(LLMMessage(MessageRole.USER, (TextContent("合成问题"),)),),
            max_output_tokens=2048,
            streaming=streaming,
        )
    )


async def _run(gateway, request, progress):
    speaker = CharacterId(WorldId(uuid4()), uuid4())

    async def receive(event):
        progress.append(event)

    return await dialogue_text(gateway, request, ChatTurnTokenBudget(10000), None, receive, speaker)


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("[她微笑。]你好。", "[她微笑。]你好。"),
        ("*她抬起头。*你好😀。", "*她抬起头。*你好😀。"),
        ('{"reply":"*她笑了。*", "events": broken}', "*她笑了。*"),
        (json.dumps({"reply": "你好😀\n*她挥手。*"}), "你好😀\n*她挥手。*"),
    ],
)
def test_final_dialogue_is_usable_with_one_physical_call(streaming, raw, expected):
    gateway, progress = _Gateway(raw, FinishReason.STOP), []
    result = asyncio.run(_run(gateway, _request(streaming), progress))
    assert result.text == expected
    assert gateway.calls == 1
    if streaming:
        assert "".join(event.text for event in progress) == expected


@pytest.mark.parametrize("streaming", [False, True])
def test_output_limit_after_closed_body_preserves_body_only(streaming):
    gateway = _Gateway('{"reply":"*她合上书。*", "memories":[', FinishReason.OUTPUT_LIMIT)
    result = asyncio.run(_run(gateway, _request(streaming), []))
    assert result == AnnotatedDialogue("*她合上书。*")
    assert gateway.calls == 1


@pytest.mark.parametrize("raw", ['{"reply":"没写完', "*尚未完成的普通正文"])
def test_output_limit_never_turns_incomplete_body_into_a_complete_reply(raw):
    gateway = _Gateway(raw, FinishReason.OUTPUT_LIMIT)
    with pytest.raises(ChatReplyValidationError, match="chat_reply_output_limit"):
        asyncio.run(_run(gateway, _request(True), []))
    assert gateway.calls == 1


@pytest.mark.parametrize("streaming", [False, True])
def test_invalid_transport_unicode_is_a_safe_format_error_without_replay(streaming):
    gateway = _Gateway("无效正文\ud800", FinishReason.STOP)
    with pytest.raises(ChatReplyValidationError, match="chat_reply_format_invalid"):
        asyncio.run(_run(gateway, _request(streaming), []))
    assert gateway.calls == 1


def test_changed_provisional_decode_cannot_discard_valid_terminal_body(monkeypatch):
    values = iter(["旧预览", "另一个预览"])
    monkeypatch.setattr(
        "livingworld.application.chat_reply.partial_optional_reply", lambda _: next(values)
    )
    gateway = _Gateway('{"reply":"最终完整正文", "events":[]}', FinishReason.STOP)
    progress = []
    result = asyncio.run(_run(gateway, _request(True), progress))
    assert result.text == "最终完整正文"
    assert gateway.calls == 1
    assert [event.text for event in progress] == ["旧预览"]


def test_plain_narrative_streams_incrementally_without_envelope_fields():
    body = "*她合上书，向窗外望去。*“你来了。”"
    gateway, progress = _Gateway(body, FinishReason.STOP), []
    result = asyncio.run(_run(gateway, _request(True), progress))
    assert result.text == body
    assert len(progress) > 1
    assert "".join(event.text for event in progress) == body
    assert gateway.calls == 1


def test_card_and_full_opening_survive_optional_context_packing(canonical_draft):
    from livingworld.application.chat_capacity import ContextPacker
    from livingworld.application.chat_roleplay import roleplay_prompt
    from livingworld.domain.content.models import CharacterDefinition

    card = next(item for item in canonical_draft.contents if isinstance(item, CharacterDefinition))
    opening = "{{char}}向{{user}}招手。" + "开场。" * 3000
    card = replace(card, authored_instructions={"character_card": {"first_mes": opening}})
    speaker = CharacterId(WorldId(uuid4()), uuid4())
    roleplay = roleplay_prompt("补充背景", speaker, card, "玩家甲")
    system = roleplay.system
    request = replace(
        _request(False),
        messages=(
            LLMMessage(MessageRole.SYSTEM, (TextContent(system),)),
            LLMMessage(
                MessageRole.USER,
                (TextContent(json.dumps({"character": {}, "common_world_background": ["可选"]})),),
            ),
            *roleplay.demonstrations,
        ),
    )
    packer = ContextPacker(request)
    packer.drop_batch()
    packed = packer.render()
    assert packed.messages[0].content[0].text == system
    assert (
        opening.replace("{{char}}", card.display_name).replace("{{user}}", "玩家甲")
        == packed.messages[-1].content[0].text
    )
    assert packed.messages[-1].role is MessageRole.ASSISTANT
    assert json.loads(packed.messages[1].content[0].text)["common_world_background"] == []
