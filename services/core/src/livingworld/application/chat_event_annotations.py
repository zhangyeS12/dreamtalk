"""Same-call dialogue annotations are reported claims, never world facts."""

import json
import re
from dataclasses import dataclass, replace
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic_core import from_json

from livingworld.application.chat_diagnostics import chat_reply_shape, chat_warning
from livingworld.application.chat_media import MediaIntent
from livingworld.application.chat_privacy import PRIVATE_REPLY_INSTRUCTIONS, valid_reply_parts
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
_ENVELOPE_START = re.compile(
    r'\A(?:\{\s*(?:["}]|(?:reply|events|memories|media|character_updates)\s*:)|\[\s*\{\s*")'
)
_LEADING_BODY = re.compile(r'\A\{\s*"(?P<field>reply|reply_parts)"\s*:\s*')
_AUXILIARY_TAIL = re.compile(
    r'\A,\s*"(?:events|memories|media|character_updates|privacy_parts|reply_parts)"\s*:'
)
_BODY_MEMBER = re.compile(r'(?<!\\)"(?:reply|reply_parts)"\s*:')

ANNOTATION_SCHEMA = {
    "type": "object",
    "properties": {
        "reply": {"type": "string", "minLength": 1},
        "events": {},
        "memories": {},
        "character_updates": {},
    },
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
    "character_updates是可选的角色卡动态变化，不是世界事实；只记录reply明确体现、且长期稳定的角色变化。"
    "每条包含field(description/personality/background/scenario/speech_guidance)、scope(global或player)、"
    "change_kind(addition表示增加原本没有的特点，replacement表示修改已有内容)、"
    "text(该字段变化后的完整当前版本，最多4000字，保留仍有效的原有内容)、"
    "quote(reply中的逐字证据)、confidence(0到1)。"
    "新增不要求原字段为空；新增特点应补入已有内容，不丢弃其他仍有效的特点。"
    "通过校验后会在回复保存成功后自动生效，用户可回退或锁定；不为产生变化而编造证据。"
    "最多4条，每个field与scope组合最多一条；不确定或只是一次性情绪时留空。"
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


class CharacterEvolutionProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    field: Literal["description", "personality", "background", "scenario", "speech_guidance"]
    scope: Literal["global", "player"] = "global"
    change_kind: Literal["addition", "replacement"] = "replacement"
    text: str = Field(min_length=1, max_length=4000)
    quote: str = Field(min_length=3, max_length=1000)
    confidence: float = Field(ge=0, le=1)


@dataclass(frozen=True, slots=True)
class AnnotatedDialogue:
    text: str
    events: tuple[ChatEventAnnotation, ...] = ()
    memories: tuple[MemoryAnnotation, ...] = ()
    media: MediaIntent | None = None
    character_updates: tuple[CharacterEvolutionProposal, ...] = ()
    privacy_parts: tuple[dict, ...] | None = None
    private_context: bool = False
    privacy_fallback: bool | None = None


class DialogueFormatError(ValueError):
    """A fixed category only; never retain the rejected dialogue or JSON values."""

    def __init__(self, reason):
        super().__init__("chat_reply_invalid")
        self.reason = reason


def annotate_request(request, *, private=False):
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
                + (
                    TextContent(
                        "\n\n"
                        + (PRIVATE_REPLY_INSTRUCTIONS if private else ANNOTATION_INSTRUCTIONS)
                        + MEMORY_INSTRUCTIONS
                    ),
                ),
            ),
        )
        + tuple(m for m in request.messages if m.role is not MessageRole.SYSTEM),
        # Annotations are optional dialogue data, not a mandatory provider
        # structured-output result. Complete normal dialogue may still succeed.
        structured_output=None,
        metadata={
            **request.metadata,
            "chat_reply_encoding": CHAT_ANNOTATION_ENCODING,
            **({"chat_privacy": True} if private else {}),
        },
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


def partial_optional_reply(raw, *, defer_envelope=False):
    """Stream unambiguous prose; withhold possible envelopes and code fences."""
    candidate = raw.lstrip("\ufeff \t\r\n")
    if candidate and candidate[0] not in "{[`":
        return raw
    return None if defer_envelope else partial_reply(raw)


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


def completed_dialogue(raw, *, private=False):
    """Keep only a complete body and its audiences; never finish partial JSON values."""
    candidate = raw.strip().lstrip("\ufeff").lstrip()
    if fence := _CODE_FENCE.fullmatch(candidate):
        candidate = fence["body"].strip()
    elif start := _JSON_FENCE_START.match(candidate):
        candidate = candidate[start.end() :].lstrip()
    try:
        decoded = decode_dialogue(candidate, private=private)
        return AnnotatedDialogue(
            decoded.text,
            privacy_parts=decoded.privacy_parts,
            private_context=decoded.private_context,
        )
    except DialogueFormatError as error:
        if error.reason != "invalid_json":
            return None
    start = _LEADING_BODY.match(candidate)
    if start is None or start["field"] == "reply_parts" and not private:
        return None
    try:
        # strict=False permits literal newlines in an otherwise complete string.
        # Python owns quote/escape decoding and returns the exact end boundary.
        value, end = json.JSONDecoder(
            strict=False, object_pairs_hook=_unique_json, parse_constant=_reject_non_finite
        ).raw_decode(candidate, start.end())
        decoded = decode_dialogue(json.dumps({start["field"]: value}), private=private)
    except (ValueError, TypeError, RecursionError):
        return None
    tail = candidate[end:].lstrip()
    if _BODY_MEMBER.search(tail):
        return None  # An ambiguous second reply must never replace the streamed one.
    if tail and tail != "}" and not _AUXILIARY_TAIL.match(tail):
        return None
    return decoded


def completed_reply(raw):
    """Compatibility entrypoint for ordinary complete-body recovery."""
    decoded = completed_dialogue(raw)
    return decoded.text if decoded is not None else None


def decode_optional_dialogue(raw, *, private=False):
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
        chat_reply_shape("prose")
        return AnnotatedDialogue(raw)
    try:
        return decode_dialogue(candidate, private=private)
    except DialogueFormatError as error:
        if error.reason != "invalid_json":
            raise
        recovered = completed_dialogue(candidate, private=private)
        if recovered is None:
            raise
        # Keep only the already complete body; discard every untrusted auxiliary field.
        chat_warning("chat_reply_recovered", reason="auxiliary_discarded")
        return recovered


def decode_dialogue(raw, *, private=False):
    try:
        value = json.loads(raw, object_pairs_hook=_unique_json, parse_constant=_reject_non_finite)
    except DialogueFormatError:
        raise
    except (ValueError, TypeError, RecursionError):
        chat_reply_shape("invalid_json")
        raise DialogueFormatError("invalid_json") from None
    if not isinstance(value, dict):
        chat_reply_shape("non_object")
        raise DialogueFormatError("invalid_envelope")
    chat_reply_shape(
        "reply_parts"
        if "reply_parts" in value
        else "legacy_parts"
        if "privacy_parts" in value
        else "reply_text"
        if "reply" in value
        else "history_parts"
        if "message_parts" in value
        else "text_body"
        if "text" in value or "content" in value
        else "missing_body"
    )
    if private and "reply_parts" in value:
        parts = value["reply_parts"]
        if valid_reply_parts(parts):
            body = _valid_reply("".join(part["text"] for part in parts))
            if "reply" not in value or value["reply"] == body:
                value = {**value, "reply": body, "privacy_parts": parts}
            else:
                value = {**value, "privacy_parts": None}
        elif "reply" in value:
            value = {**value, "privacy_parts": None}
        elif (
            isinstance(parts, list)
            and 0 < len(parts) <= 64
            and all(isinstance(part, dict) and isinstance(part.get("text"), str) for part in parts)
        ):
            # Complete prose is still recoverable even when only classification is bad.
            value = {
                **value,
                "reply": _valid_reply("".join(part["text"] for part in parts)),
                "privacy_parts": None,
            }
        else:
            raise DialogueFormatError("invalid_private_parts")
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
    updates = []
    update_keys = set()
    proposals = value.get("character_updates", [])
    if isinstance(proposals, list) and len(proposals) <= 4:
        for proposal in proposals:
            try:
                item = CharacterEvolutionProposal.model_validate(proposal)
                key = (item.field, item.scope)
                if item.quote not in reply or item.confidence < 0.6 or key in update_keys:
                    continue
                updates.append(item)
                update_keys.add(key)
            except (ValueError, TypeError):
                continue
    for key, accepted in (
        ("events", result),
        ("memories", memories),
        ("character_updates", updates),
    ):
        proposed = value.get(key, [])
        if not isinstance(proposed, list) or len(proposed) != len(accepted):
            chat_warning("chat_annotation_discarded", reason=key + "_invalid")
    if value.get("media") is not None and media is None:
        chat_warning("chat_annotation_discarded", reason="media_invalid")
    parts = value.get("privacy_parts")
    declared_parts = "reply_parts" in value or "privacy_parts" in value
    needs_private = (
        private
        and declared_parts
        and (not valid_reply_parts(parts, reply) or any(part["private"] for part in (parts or ())))
    )
    return AnnotatedDialogue(
        reply,
        tuple(result),
        tuple(memories),
        media,
        tuple(updates),
        tuple(parts) if isinstance(parts, list) and len(parts) <= 64 else None,
        private_context=needs_private,
    )
