"""Synthetic labels and one-call gateway output; no user storage or provider access."""

import asyncio
import json
from uuid import UUID, uuid4

import pytest
from livingworld.application.chat_event_annotations import annotate_request
from livingworld.application.chat_reply import ChatReplyValidationError, dialogue_text
from livingworld.application.chat_speaker_labels import (
    SpeakerReplyText,
    without_legacy_speaker_header,
)
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

SPEAKER = CharacterId(WorldId(UUID(int=1)), UUID(int=2))
NAME = "合成角色甲"
HEADER = f"{NAME}（发言者标识：{SPEAKER.value}）：\n"
BODY = "*她点点头。*“接着说吧。”"


@pytest.mark.parametrize(
    "header",
    [
        HEADER,
        f" {NAME} ( 发言者标识 : {SPEAKER.value} ) :\r\n",
        f"{NAME}（发言者标识：{SPEAKER.value}）： ",
    ],
)
def test_current_sender_header_is_removed_without_losing_roleplay(header):
    cleaner = SpeakerReplyText(NAME, SPEAKER)
    raw = header + BODY
    assert cleaner.complete(raw) == BODY
    for end in range(1, len(raw) + 1):
        preview = cleaner.preview(raw[:end])
        assert preview is None or BODY.startswith(preview)


@pytest.mark.parametrize(
    "body",
    [
        NAME,
        NAME + "走到门边。",
        NAME + "（低声）：你好。",
        f"记录编号是{SPEAKER.value}。",
        f"她说：“示例标签{HEADER.strip()}”。",
        f"另一位（发言者标识：{UUID(int=3)}）：\n原样引用。",
        "```\n" + HEADER + "```",
    ],
)
def test_dialogue_uuids_quoted_labels_and_other_sender_headers_are_not_scrubbed(body):
    cleaner = SpeakerReplyText(NAME, SPEAKER)
    assert cleaner.complete(body) == body
    assert cleaner.preview(body) in {None, body}


def test_renamed_legacy_header_is_removed_only_in_prepared_copy():
    stored = HEADER.replace(NAME, "旧名字") + BODY
    assert without_legacy_speaker_header(stored, SPEAKER) == BODY
    assert stored == HEADER.replace(NAME, "旧名字") + BODY


class Gateway:
    def __init__(self, raw):
        self.raw, self.calls = raw, 0

    async def generate(self, request, **_):
        self.calls += 1
        return LLMResponse(
            invocation_id=request.invocation_id,
            model_used=request.model,
            content=(TextContent(self.raw),),
            finish_reason=FinishReason.STOP,
        )

    async def stream(self, request, **_):
        self.calls += 1
        for character in self.raw:
            yield TextDelta(request.invocation_id, character)
        yield StreamCompleted(
            LLMStreamCompletion(
                invocation_id=request.invocation_id,
                model_used=request.model,
                finish_reason=FinishReason.STOP,
            )
        )


async def run(raw, *, streaming, annotations, name=NAME):
    gateway, progress = Gateway(raw), []
    request = LLMRequest(
        invocation_id=InvocationId(uuid4()),
        model=ModelRef(ProviderId("synthetic"), "mock-dialogue"),
        purpose=LLMPurpose("character_dialogue"),
        messages=(LLMMessage(MessageRole.USER, (TextContent("合成问题"),)),),
        max_output_tokens=2048,
        streaming=streaming,
        metadata={"reply_speaker_name": name},
    )
    if annotations:
        request = annotate_request(request)

    async def receive(event):
        progress.append(event.text)

    result = await dialogue_text(
        gateway, request, ChatTurnTokenBudget(10000), None, receive, SPEAKER
    )
    return result, gateway.calls, progress


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("encoding", ["plain", "optional", "json"])
def test_reply_and_each_stream_delta_exclude_prefix_with_one_call(streaming, encoding):
    raw = HEADER + BODY
    if encoding == "json":
        raw = json.dumps({"reply": raw}, ensure_ascii=False)
    result, calls, progress = asyncio.run(
        run(raw, streaming=streaming, annotations=encoding != "plain")
    )
    assert (result if isinstance(result, str) else result.text) == BODY
    assert calls == 1
    if streaming:
        assert "".join(progress) == BODY
        assert len(progress) > 1
        assert all("发言者标识" not in text and str(SPEAKER.value) not in text for text in progress)


def test_removed_header_cannot_be_an_event_or_reply_memory_quote():
    def memory(source, quote):
        return {
            "kind": "experience",
            "topic": "合成",
            "content": "合成记忆",
            "source": source,
            "quote": quote,
        }

    raw = json.dumps(
        {
            "reply": HEADER + BODY,
            "events": [
                {"kind": "plan", "title": "合成", "quote": HEADER.strip()},
                {"kind": "plan", "title": "合成", "quote": "接着说吧。"},
            ],
            "memories": [
                memory("reply", HEADER.strip()),
                memory("reply", "接着说吧。"),
                memory("player", "合成玩家消息"),
            ],
        },
        ensure_ascii=False,
    )
    result, calls, _ = asyncio.run(run(raw, streaming=True, annotations=True))
    assert result.text == BODY
    assert [event.quote for event in result.events] == ["接着说吧。"]
    assert [item.source for item in result.memories] == ["reply", "player"]
    assert calls == 1


@pytest.mark.parametrize("annotations", [False, True])
@pytest.mark.parametrize("raw", [HEADER, HEADER[:-5]])
def test_bare_header_cannot_create_a_message_or_trigger_replay(annotations, raw):
    async def check():
        gateway = Gateway(raw)
        request = LLMRequest(
            invocation_id=InvocationId(uuid4()),
            model=ModelRef(ProviderId("synthetic"), "mock-dialogue"),
            purpose=LLMPurpose("character_dialogue"),
            messages=(LLMMessage(MessageRole.USER, (TextContent("合成问题"),)),),
            max_output_tokens=512,
            metadata={"reply_speaker_name": NAME},
        )
        if annotations:
            request = annotate_request(request)
        with pytest.raises(ChatReplyValidationError):
            await dialogue_text(gateway, request, ChatTurnTokenBudget(10000), None, None, SPEAKER)
        assert gateway.calls == 1

    asyncio.run(check())


def test_local_speaker_hint_is_not_required_for_unmodified_callers():
    result, calls, _ = asyncio.run(run(BODY, streaming=True, annotations=True, name=""))
    assert result.text == BODY and calls == 1
