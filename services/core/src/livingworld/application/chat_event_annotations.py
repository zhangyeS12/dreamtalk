"""Same-call dialogue annotations are reported claims, never world facts."""

import json
import re
from dataclasses import dataclass, replace
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic_core import from_json

from livingworld.application.chat_media import MediaIntent
from livingworld.application.llm import (
    LLMMessage,
    MessageRole,
    TextContent,
)
from livingworld.application.long_chat_memory import MEMORY_INSTRUCTIONS, MemoryAnnotation

CHAT_ANNOTATION_ENCODING = "same_call_chat_annotations_v1"
_JSON_FENCE_START = re.compile(r"\A```(?:json)?[ \t]*\r?\n", re.IGNORECASE)
_CODE_FENCE = re.compile(
    r"\A```(?P<language>[\w+-]*)[ \t]*\r?\n(?P<body>.*?)\r?\n```[ \t]*\Z",
    re.IGNORECASE | re.DOTALL,
)
_ENVELOPE_START = re.compile(r'\A(?:\{\s*(?:["}]|(?:reply|events|memories|media)\s*:)|\[\s*\{\s*")')
_LEADING_REPLY = re.compile(r'\A\{\s*"reply"\s*:\s*')
_AUXILIARY_TAIL = re.compile(r'\A,\s*"(?:events|memories|media)"\s*:')
_REPLY_MEMBER = re.compile(r'(?<!\\)"reply"\s*:')

ANNOTATION_SCHEMA = {
    "type": "object",
    "properties": {"reply": {"type": "string", "minLength": 1}, "events": {}, "memories": {}},
    "required": ["reply"],
    "additionalProperties": True,
}
ANNOTATION_INSTRUCTIONS = (
    "首先完成自然、完整的角色回复。可以直接输出角色正文；事件、记忆和媒体数据是可选辅助内容，"
    "不需要辅助数据或无法可靠组织JSON时直接输出正文，不附带字段、解释或残缺JSON。"
    "需要提供辅助数据时输出同一个完整json对象，不加Markdown代码块、解释或对象外文字。先完成非空reply角色回复，"
    "再写events和memories。角色扮演回复是首要任务，即使没有活动记录、事件或新记忆也必须正常回应。"
    "没有重要辅助信息时，events和memories为空数组；不要以空正文或空reply代替回答。"
    "reply是完整角色回复，可含台词、动作、神态、心理和场景描写，不向玩家显示字段。"
    "辅助字段不规定人物口吻、篇幅或情节；reply遵循角色卡和当前互动。"
    "events是本次reply明确告知玩家的具体活动、未来计划、传闻、邀请或计划改变，最多3条；"
    "寒暄、感受、性格习惯、纯假设、玩笑和重复闲聊不记录，允许events为空数组，不为记录而编造剧情。"
    "明确表达可约时间或带条件的实际邀约仍应记录；标题与quote保留全部条件和取消分支，"
    "不能拆成无条件赴约或写成已经见面，不把修辞当事件。"
    "每条只含kind(activity/plan/rumor/invitation/change)、title(简短标题)、quote(reply中完整原句)、"
    "time_text(原句中的时间说法，无则null)、source_event_id(输入提供且本人有权知道的实际事件ID，无则null)、"
    "updates_entry_id(本会话提供的旧事件记录ID，只有明确取消/改变它才填写，否则null)。"
    "quote必须逐字出现在reply，time_text必须逐字出现在quote。计划不能说成已发生，传闻不能说成证实。"
    "活动回答仍以本人已提交的活动记录为依据，结构化字段不能增加台词没有告知的内容。"
)


class ChatEventAnnotation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: Literal["activity", "plan", "rumor", "invitation", "change"]
    title: str = Field(min_length=1, max_length=80)
    quote: str = Field(min_length=3, max_length=1000)
    time_text: str | None = Field(default=None, max_length=100)
    source_event_id: str | None = Field(default=None, max_length=36)
    updates_entry_id: str | None = Field(default=None, max_length=36)


@dataclass(frozen=True, slots=True)
class AnnotatedDialogue:
    text: str
    events: tuple[ChatEventAnnotation, ...] = ()
    memories: tuple[MemoryAnnotation, ...] = ()
    media: MediaIntent | None = None


class DialogueFormatError(ValueError):
    """A fixed category only; never retain the rejected dialogue or JSON values."""

    def __init__(self, reason):
        super().__init__("chat_reply_invalid")
        self.reason = reason


def annotate_request(request):
    return replace(
        request,
        # Put the optional transport contract after role instructions and before
        # the unchanged conversation; retain the full body in either encoding.
        # Messages/Interactions accept one leading system instruction. Keep all
        # existing blocks and append the same-call contract without changing roles
        # or moving conversation data into that privileged instruction.
        messages=(
            LLMMessage(
                MessageRole.SYSTEM,
                tuple(
                    block
                    for message in request.messages
                    if message.role is MessageRole.SYSTEM
                    for block in message.content
                )
                + (TextContent("\n\n" + ANNOTATION_INSTRUCTIONS + MEMORY_INSTRUCTIONS),),
            ),
        )
        + tuple(m for m in request.messages if m.role is not MessageRole.SYSTEM),
        # Annotations are optional dialogue data, not a mandatory provider
        # structured-output result. Complete normal dialogue may still succeed.
        structured_output=None,
        metadata={**request.metadata, "chat_reply_encoding": CHAT_ANNOTATION_ENCODING},
    )


def optional_annotation_request(request):
    return request.metadata.get("chat_reply_encoding") == CHAT_ANNOTATION_ENCODING


def annotation_request(request):
    return optional_annotation_request(request) or (
        request.structured_output is not None
        and request.structured_output.schema_name == "chat_event_reply"
    )


def partial_reply(raw):
    """Use the existing mature JSON parser; no handwritten escape/token parser."""
    candidate = raw.lstrip()
    if start := _JSON_FENCE_START.match(candidate):
        candidate = candidate[start.end() :]
        if candidate.rstrip().endswith("\n```"):
            candidate = candidate.rstrip()[:-4]
    try:
        value = from_json(candidate.encode("utf-8"), allow_partial="trailing-strings")
    except ValueError:
        return None
    reply = value.get("reply") if isinstance(value, dict) else None
    return reply if isinstance(reply, str) else None


def partial_optional_reply(raw):
    """Stream unambiguous prose; withhold possible envelopes and code fences."""
    candidate = raw.lstrip("\ufeff \t\r\n")
    if candidate and candidate[0] not in "{[`":
        return raw
    return partial_reply(raw)


def _unique_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DialogueFormatError("duplicate_member")
        result[key] = value
    return result


def _reject_non_finite(_):
    raise DialogueFormatError("non_finite")


def _valid_reply(text):
    if not isinstance(text, str):
        raise DialogueFormatError("invalid_reply_type")
    if not text.strip():
        raise DialogueFormatError("empty_reply")
    try:
        size = len(text.encode("utf-8"))
    except UnicodeEncodeError:
        raise DialogueFormatError("invalid_reply_text") from None
    if size > 65536:
        raise DialogueFormatError("oversized_reply")
    return text


def completed_reply(raw):
    """Decode only a closed, leading reply value; never repair or finish its text."""
    candidate = raw.strip().lstrip("\ufeff").lstrip()
    if fence := _CODE_FENCE.fullmatch(candidate):
        candidate = fence["body"].strip()
    elif start := _JSON_FENCE_START.match(candidate):
        candidate = candidate[start.end() :].lstrip()
    start = _LEADING_REPLY.match(candidate)
    if start is None:
        return None
    try:
        # strict=False permits literal newlines in an otherwise complete string.
        # Python owns quote/escape decoding and returns the exact end boundary.
        reply, end = json.JSONDecoder(strict=False).raw_decode(candidate, start.end())
        reply = _valid_reply(reply)
    except (ValueError, TypeError, RecursionError):
        return None
    tail = candidate[end:].lstrip()
    if _REPLY_MEMBER.search(tail):
        return None  # An ambiguous second reply must never replace the streamed one.
    if tail and not tail.startswith("}") and not _AUXILIARY_TAIL.match(tail):
        return None
    return reply


def decode_optional_dialogue(raw):
    """Accept complete dialogue; never display an invalid annotation envelope."""
    _valid_reply(raw)
    candidate = raw.strip().lstrip("\ufeff").lstrip()
    declared_json = False
    if fence := _CODE_FENCE.fullmatch(candidate):
        declared_json = fence["language"].lower() == "json"
        candidate = fence["body"].strip()
    elif start := _JSON_FENCE_START.match(candidate):
        declared_json = candidate[: start.end()].strip().lower() == "```json"
        candidate = candidate[start.end() :].lstrip()
    if not declared_json and not _ENVELOPE_START.match(candidate):
        return AnnotatedDialogue(raw)
    try:
        return decode_dialogue(candidate)
    except DialogueFormatError as error:
        if error.reason != "invalid_json":
            raise
        reply = completed_reply(candidate)
        if reply is None:
            raise
        # Keep only the already complete body; discard every untrusted auxiliary field.
        return AnnotatedDialogue(reply)


def decode_dialogue(raw):
    try:
        value = json.loads(raw, object_pairs_hook=_unique_json, parse_constant=_reject_non_finite)
    except DialogueFormatError:
        raise
    except (ValueError, TypeError, RecursionError):
        raise DialogueFormatError("invalid_json") from None
    if not isinstance(value, dict):
        raise DialogueFormatError("invalid_envelope")
    if "reply" not in value:
        raise DialogueFormatError("missing_reply")
    reply = _valid_reply(value["reply"])
    candidates = value.get("events", [])
    if not isinstance(candidates, list) or len(candidates) > 3:
        candidates = []
    result = []
    for candidate in candidates:
        try:
            item = ChatEventAnnotation.model_validate(candidate)
            if (
                not item.title.strip()
                or not item.quote.strip()
                or item.quote not in reply
                or item.time_text is not None
                and item.time_text not in item.quote
            ):
                continue
            result.append(item)
        except (ValueError, TypeError):
            continue  # Metadata never triggers a paid repair request.
    memories = []
    proposals = value.get("memories", [])
    if isinstance(proposals, list) and len(proposals) <= 4:
        for proposal in proposals:
            try:
                item = MemoryAnnotation.model_validate(proposal)
                if not item.content.strip() or not item.topic.strip() or not item.quote.strip():
                    continue
                if item.source == "reply" and item.quote not in reply:
                    continue
                memories.append(item)
            except (ValueError, TypeError):
                continue
    media = None
    if isinstance(value.get("media"), dict):
        try:
            media = MediaIntent.model_validate_json(json.dumps(value["media"]))
        except (ValueError, TypeError):
            pass
    return AnnotatedDialogue(reply, tuple(result), tuple(memories), media)
