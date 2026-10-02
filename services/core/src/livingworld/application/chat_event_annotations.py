"""Same-call dialogue annotations are reported claims, never world facts."""

import json
from dataclasses import dataclass, replace
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic_core import from_json

from livingworld.application.llm import (
    LLMMessage,
    MessageRole,
    StructuredOutputRequest,
    TextContent,
)
from livingworld.application.long_chat_memory import MEMORY_INSTRUCTIONS, MemoryAnnotation

ANNOTATION_SCHEMA = {
    "type": "object",
    "properties": {"reply": {"type": "string"}, "events": {}},
    "required": ["reply"],
    "additionalProperties": True,
}
ANNOTATION_INSTRUCTIONS = (
    "只返回一个json对象，先写reply，再写events。reply是正常角色台词，不向玩家显示字段。"
    "原有‘只输出聊天台词’规则只约束reply内容，不约束传输格式；不要返回纯台词或省略reply字段。"
    "events是本次reply明确告知玩家的具体活动、未来计划、传闻、邀请或计划改变，最多3条；"
    "寒暄、感受、性格习惯、假设、玩笑和重复闲聊不记录，允许events为空数组，不为记录而编造剧情。"
    "每条只含kind(activity/plan/rumor/invitation/change)、title(简短标题)、quote(reply中完整原句)、"
    "time_text(原句中的时间说法，无则null)、source_event_id(输入提供且本人有权知道的实际事件ID，无则null)、"
    "updates_entry_id(本会话提供的旧事件记录ID，只有明确取消/改变它才填写，否则null)。"
    "quote必须逐字出现在reply，time_text必须逐字出现在quote。计划不能说成已发生，传闻不能说成证实。"
    "活动回答仍以本人已提交的活动记录为依据，结构化字段不能增加台词没有告知的内容。"
    '示例json：{"reply":"我明天下午想去商店购物，你要一起吗？",'
    '"events":[{"kind":"plan","title":"铃计划购物",'
    '"quote":"我明天下午想去商店购物，你要一起吗？","time_text":"明天下午",'
    '"source_event_id":null,"updates_entry_id":null}]}。'
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
        structured_output=StructuredOutputRequest("chat_event_reply", ANNOTATION_SCHEMA),
    )


def annotation_request(request):
    return (
        request.structured_output is not None
        and request.structured_output.schema_name == "chat_event_reply"
    )


def partial_reply(raw):
    """Use the existing mature JSON parser; no handwritten escape/token parser."""
    try:
        value = from_json(raw.encode("utf-8"), allow_partial="trailing-strings")
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


def decode_dialogue(raw):
    try:
        value = json.loads(raw, object_pairs_hook=_unique_json)
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
