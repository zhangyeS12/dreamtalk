"""Message-span audiences. UTF-16 offsets match the browser's native selection API."""

import json
import re
from dataclasses import replace
from uuid import UUID

_INTERNAL_MARKERS = re.compile(r"【(?:仅你与玩家可见|私密片段结束)】")


def valid_reply_parts(parts, text=None):
    return (
        isinstance(parts, (tuple, list))
        and 0 < len(parts) <= 64
        and all(
            isinstance(part, dict)
            and set(part) == {"text", "private"}
            and isinstance(part["text"], str)
            and type(part["private"]) is bool
            for part in parts
        )
        and (text is None or "".join(part["text"] for part in parts) == text)
    )


def text_parts(text, spans):
    positions, offset, parts = boundaries(text), 0, []
    for span in spans:
        start, end = positions[span["start"]], positions[span["end"]]
        if start > offset:
            parts.append({"text": text[offset:start], "private": False})
        if end > start:
            parts.append({"text": text[start:end], "private": True})
        offset = end
    if offset < len(text):
        parts.append({"text": text[offset:], "private": False})
    return tuple(parts)


def strip_internal_markers(text, spans=()):
    """Remove only retired transport tokens, mapping audiences onto unchanged prose."""
    matches = list(_INTERNAL_MARKERS.finditer(text))
    if not matches:
        return text, tuple(spans)
    offsets = {index: offset for offset, index in boundaries(text).items()}
    removed = [(offsets[m.start()], offsets[m.end()]) for m in matches]

    def mapped(offset):
        return offset - sum(max(0, min(offset, end) - start) for start, end in removed)

    cleaned = _INTERNAL_MARKERS.sub("", text)
    retained = []
    for span in spans:
        start, end = mapped(span["start"]), mapped(span["end"])
        if end > start:
            retained.append({**span, "start": start, "end": end})
    return cleaned, normalize_privacy(cleaned, retained)


def rebase_reply_parts(before, after, parts):
    """Known speaker-header removal must preserve valid visibility classification."""
    if valid_reply_parts(parts, after):
        return tuple(parts)
    if not valid_reply_parts(parts, before) or not before.endswith(after):
        return None
    removed, result = len(before) - len(after), []
    for part in parts:
        count = min(removed, len(part["text"]))
        removed -= count
        if text := part["text"][count:]:
            result.append({**part, "text": text})
    return tuple(result) if valid_reply_parts(result, after) else None


def boundaries(text):
    result, offset = {0: 0}, 0
    for index, character in enumerate(text):
        offset += 2 if ord(character) > 0xFFFF else 1
        result[offset] = index + 1
    return result


def normalize_privacy(text, spans):
    if not isinstance(spans, (tuple, list)) or len(spans) > 32:
        raise ValueError("chat_privacy_invalid")
    positions, previous, result = boundaries(text), 0, []
    for span in spans:
        if not isinstance(span, dict) or set(span) != {"start", "end", "character_id"}:
            raise ValueError("chat_privacy_invalid")
        start, end, owner = span["start"], span["end"], span["character_id"]
        if (
            type(start) is not int
            or type(end) is not int
            or start < previous
            or start >= end
            or start not in positions
            or end not in positions
            or not isinstance(owner, str)
        ):
            raise ValueError("chat_privacy_invalid")
        try:
            if str(UUID(owner)) != owner:
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise ValueError("chat_privacy_invalid") from None
        result.append(dict(start=start, end=end, character_id=owner))
        previous = end
    return tuple(result)


def private_slice(text, span):
    positions = boundaries(text)
    return text[positions[span["start"]] : positions[span["end"]]]


def move_privacy(before, after, spans):
    """An edit that touches a secret keeps the replacement inside its audience."""
    spans = normalize_privacy(before, spans)
    start, old_end, new_end = 0, len(before), len(after)
    while start < old_end and start < new_end and before[start] == after[start]:
        start += 1
    while old_end > start and new_end > start and before[old_end - 1] == after[new_end - 1]:
        old_end -= 1
        new_end -= 1
    start, old_end, new_end = (
        max(boundaries(value)) for value in (before[:start], before[:old_end], after[:new_end])
    )
    delta, result = new_end - old_end, []
    for span in spans:
        if span["end"] < start or span["end"] == start and old_end != start:
            result.append(span)
        elif span["start"] > old_end or span["start"] == old_end and old_end != start:
            result.append({**span, "start": span["start"] + delta, "end": span["end"] + delta})
        else:
            end = span["end"] + delta if span["end"] > old_end else new_end
            begin = min(span["start"], start)
            if end > begin:
                result.append({**span, "start": begin, "end": end})
    return normalize_privacy(after, result)


def mentions(text, name):
    return bool(re.search(rf"(?<!\S)@{re.escape(name)}(?=$|\s|[,.!?，。！？：:（(])", text))


def validate_targets(text, spans, participants):
    """Resolve by durable ID; names are checked only against the selected text."""
    for span in normalize_privacy(text, spans):
        selected = private_slice(text, span)
        targets = [identity for identity, name in participants if mentions(selected, name)]
        if targets != [span["character_id"]]:
            raise ValueError("chat_privacy_target_required")


def visible_text(text, spans, owner=None, *, mark=False):
    spans = normalize_privacy(text, spans)
    positions, cursor, pieces, parts = boundaries(text), 0, [], []
    owner = str(getattr(owner, "value", owner)) if owner is not None else None
    for span in spans:
        start, end = positions[span["start"]], positions[span["end"]]
        pieces.append(text[cursor:start])
        if start > cursor:
            parts.append({"text": text[cursor:start], "private": False})
        if span["character_id"] == owner:
            part = text[start:end]
            pieces.append(part)
            parts.append({"text": part, "private": True})
        cursor = end
    if cursor < len(text):
        parts.append({"text": text[cursor:], "private": False})
    if mark and any(span["character_id"] == owner for span in spans):
        return json.dumps({"message_parts": parts}, ensure_ascii=False, separators=(",", ":"))
    return "".join((*pieces, text[cursor:]))


def project_message(message, owner=None):
    message = clean_private_message(message)
    if not getattr(message, "privacy", ()):
        return message
    owner_id = str(getattr(owner, "value", owner)) if owner is not None else None
    return replace(
        message,
        text=visible_text(message.text, message.privacy, owner, mark=True),
        privacy=(),
        private_context=any(s["character_id"] == owner_id for s in message.privacy),
    )


def clean_private_message(message, *, sensitive=False):
    from livingworld.domain.identifiers import CharacterId

    spans = getattr(message, "privacy", ())
    if not (sensitive or spans) or not isinstance(getattr(message, "sender_id", None), CharacterId):
        return message
    text, spans = strip_internal_markers(message.text, spans)
    return replace(message, text=text, privacy=spans)


def clean_private_dialogue(dialogue, owner):
    fallback = dialogue.privacy_fallback is True or not valid_reply_parts(
        dialogue.privacy_parts, dialogue.text
    )
    spans = reply_privacy(dialogue, owner)
    text, spans = strip_internal_markers(dialogue.text, spans)
    return replace(
        dialogue,
        text=text,
        privacy_parts=text_parts(text, spans),
        private_context=True,
        privacy_fallback=fallback,
        events=(),
        character_updates=(),
        media=None,
    )


def row_text(row, owner=None):
    """Project stored sources before ranking, extraction or shared summarization."""
    spans = json.loads(row.privacy_json) if getattr(row, "privacy_json", None) else ()
    text = row.text
    if (
        getattr(row, "privacy_json", None) is not None
        and getattr(row, "sender_character_id", None) is not None
    ):
        text, spans = strip_internal_markers(text, spans)
    return visible_text(text, spans, owner)


PRIVATE_REPLY_INSTRUCTIONS = (
    "首先完成自然完整的角色回复，本轮必须使用分段JSON返回，不能直接返回未分类的正文。"
    "历史message_parts是来源数据：text是原话，private=true仅你与玩家知道；不要复制来源结构或标签。"
    "回复仍是群聊。收到过私密内容不代表整条回应都私密；按实际受众标注最小连续片段，"
    "可以短到一句中的几个字，同一句和同一段可以多次公开、私密交替，不能因为相邻就合并不同受众。"
    "按原文顺序连贯写作，分类不要求另起段落；只有全文确实都不应让其他成员知道时才全部标私密。"
    "判断依据是这段新回复本身的可见／可听范围，以及是否泄露受限信息，不按话题来源、"
    "回复对象或触发原因分类。面向群聊公开说出的正常话语，以及当前场景其他在场者确实能"
    "观察且不泄密的外在动作、神态和移动，标private=false。公开对一个人说话也不等于私密。"
    "即使由私密内容引起，公开可见的脸红、停顿、拿菜单、坐下和招呼大家仍可公开，"
    "不能仅因与私密交流有关就连带遮住。群成员不等于物理同场，不凭群成员身份编造现场观察。"
    "只有明确仅玩家与本角色可听／可见的隐蔽交流、低声话语、未表露的内心，或会泄露"
    "私密来源的文字标private=true。受限的是具体秘密时，只标对应的最小连续片段，"
    "不要连带标记其前后的公开动作和正常台词。疑似泄密且无法确定的部分仍保守保护，"
    "但必须先分离已能确认公开的内容，不把局部不确定扩大为整段或整条私密。"
    "玩家已标私密的动作与话语保持原受众，不能因看起来可观察而重新公开或在公开段复述。"
    "只输出一个完整JSON对象：reply_parts是按正文顺序排列的数组，每项仅含text和private布尔值。"
    "完整正文由所有text依次拼接，不要再重复写reply，不添加接收者ID或正文之外的解释。"
    '格式示例（只演示受众边界，不照抄动作或台词）：{"reply_parts":['
    '{"text":"她拿起菜单，","private":false},'
    '{"text":"只让你听见地说：‘暗号我记住了。’","private":true},'
    '{"text":"随后向大家问：‘还要加菜吗？’","private":false}],"memories":[]}。'
    "最多64段，不为分类删减角色正文。可附memories，其reply来源指各段拼接后的完整正文。"
    "不附events、character_updates或media。未提供有效分段会被整条私密保存，不会额外调用模型修复。"
    "公开段不得透露私密原文、分类标记或凭私密来源得出的秘密推断；"
    "未公开的私下动作或交流本身也不能被公开段确认。text中只能写角色正文。"
)


def reply_privacy(dialogue, owner):
    text, parts = dialogue.text, dialogue.privacy_parts
    if valid_reply_parts(parts, text):
        offset, spans = 0, []
        for part in parts:
            end = offset + max(boundaries(part["text"]))
            if part["private"] and end > offset:
                if spans and spans[-1]["end"] == offset:
                    spans[-1]["end"] = end
                else:
                    spans.append(dict(start=offset, end=end, character_id=str(owner.value)))
            offset = end
        if len(spans) <= 32:
            return tuple(spans)
    return (dict(start=0, end=max(boundaries(text)), character_id=str(owner.value)),)
