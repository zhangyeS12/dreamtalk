"""Same-call dialogue annotations are reported claims, never world facts."""

import json
import re
from dataclasses import dataclass, replace
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic_core import from_json

from livingworld.application.llm import (
    LLMMessage,
    MessageRole,
    TextContent,
)
from livingworld.application.long_chat_memory import MEMORY_INSTRUCTIONS, MemoryAnnotation

CHAT_ANNOTATION_ENCODING = "same_call_chat_annotations_v1"
_JSON_FENCE_START = re.compile(r"\A```(?:json)?[ \t]*\r?\n", re.IGNORECASE)
_JSON_FENCE = re.compile(
    r"\A```(?:json)?[ \t]*\r?\n(.*?)\r?\n```[ \t]*\Z", re.IGNORECASE | re.DOTALL
)
_METADATA_MEMBER = re.compile(r'"(?:reply|events|memories)"\s*:')

ANNOTATION_SCHEMA = {
    "type": "object",
    "properties": {"reply": {"type": "string", "minLength": 1}, "events": {}, "memories": {}},
    "required": ["reply"],
    "additionalProperties": True,
}
ANNOTATION_INSTRUCTIONS = (
    "输出完整的json对象，不加Markdown代码块、解释或对象外文字。先完成非空reply台词，"
    "再写events和memories。角色台词是首要任务，即使没有活动记录、事件或新记忆也必须正常回应。"
    "寒暄可以简短回应，events和memories为空数组；不要以空正文或空reply代替回答。"
    '完整寒暄格式示例：{"reply":"我在，怎么了？","events":[],"memories":[]}。'
    "reply是正常角色台词，不向玩家显示字段，不要求机械复述示例。"
    "events是本次reply明确告知玩家的具体活动、未来计划、传闻、邀请或计划改变，最多3条；"
    "寒暄、感受、性格习惯、纯假设、玩笑和重复闲聊不记录，允许events为空数组，不为记录而编造剧情。"
    "明确表达可约时间或带条件的实际邀约仍应记录：如今天有事、明天可约，或收工后若还早就来找你喝牛奶。"
    "它们分别是计划或邀请，不是纯假设；标题与quote必须保留条件和取消分支，不能写成确定赴约或已经见面。"
    "例如‘等我收工，若还早就来找你喝牛奶；若太晚，你也早点睡，别等’是一条条件邀请，"
    "quote须包含‘若还早’和‘若太晚’两部分，不拆成多条，不把守梦等修辞当事件。"
    "每条只含kind(activity/plan/rumor/invitation/change)、title(简短标题)、quote(reply中完整原句)、"
    "time_text(原句中的时间说法，无则null)、source_event_id(输入提供且本人有权知道的实际事件ID，无则null)、"
    "updates_entry_id(本会话提供的旧事件记录ID，只有明确取消/改变它才填写，否则null)。"
    "quote必须逐字出现在reply，time_text必须逐字出现在quote。计划不能说成已发生，传闻不能说成证实。"
    "活动回答仍以本人已提交的活动记录为依据，结构化字段不能增加台词没有告知的内容。"
    '示例json：{"reply":"我明天下午想去商店购物，你要一起吗？",'
    '"events":[{"kind":"plan","title":"铃计划购物",'
    '"quote":"我明天下午想去商店购物，你要一起吗？","time_text":"明天下午",'
    '"source_event_id":null,"updates_entry_id":null}],"memories":[]}。'
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


def annotate_request(request):
    return replace(
        request,
        # Put the transport contract after role instructions and before the
        # unchanged conversation. Past plain-text replies must not override JSON.
        messages=tuple(m for m in request.messages if m.role is MessageRole.SYSTEM)
        + (
            LLMMessage(
                MessageRole.SYSTEM, (TextContent(ANNOTATION_INSTRUCTIONS + MEMORY_INSTRUCTIONS),)
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


def _unique_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("chat_reply_invalid")
        result[key] = value
    return result


def _reject_non_finite(_):
    raise ValueError("chat_reply_invalid")


def decode_optional_dialogue(raw):
    """Accept complete dialogue; never display an invalid annotation envelope."""
    candidate = raw.strip()
    if fence := _JSON_FENCE.fullmatch(candidate):
        return decode_dialogue(fence[1])
    if candidate.startswith(("{", "[", "```")) or _METADATA_MEMBER.search(candidate):
        # A malformed/truncated envelope is not a plain-text chat fallback.
        return decode_dialogue(candidate)
    if not candidate or len(raw.encode("utf-8")) > 65536:
        raise ValueError("chat_reply_invalid")
    return AnnotatedDialogue(raw)


def decode_dialogue(raw):
    try:
        value = json.loads(raw, object_pairs_hook=_unique_json, parse_constant=_reject_non_finite)
        reply = value["reply"]
        if not isinstance(reply, str) or not reply.strip() or len(reply.encode("utf-8")) > 65536:
            raise ValueError()
    except (ValueError, TypeError, KeyError):
        raise ValueError("chat_reply_invalid") from None
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
    return AnnotatedDialogue(reply, tuple(result), tuple(memories))
