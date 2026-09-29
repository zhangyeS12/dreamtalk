"""Literal Lorebook activation inside an already-authorized common-background set."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from livingworld.application.imports import LOREBOOK_METADATA_KEY
from livingworld.application.world_content import CommonLoreEntry
from livingworld.domain.content.identifiers import LoreEntryId
from livingworld.domain.content.models import LoreCollection, LoreEntry


@dataclass(frozen=True, slots=True)
class BackgroundEntry:
    """Authorized read projection, never an editable canonical content snapshot."""

    content_id: LoreEntryId
    title: str
    content: str
    keywords: tuple[str, ...]
    secondary_keywords: tuple[str, ...]
    enabled: bool
    priority: int
    order: int
    group: str | None
    activation_metadata: Mapping
    extensions: Mapping


@dataclass(frozen=True, slots=True)
class BackgroundCollection:
    activation_metadata: Mapping


@dataclass(frozen=True, slots=True)
class BackgroundItem:
    import_id: UUID
    entry: BackgroundEntry
    collection: BackgroundCollection | None = None


_DEFAULT_SCAN_DEPTH = 2
_MAX_SCAN_MESSAGES = 32
_MAX_SCAN_CHARS = 16 * 1024
_LOGIC_NAMES = {
    "AND_ANY": "任一命中",
    "AND_ALL": "全部命中",
    "NOT_ANY": "全部不命中",
    "NOT_ALL": "不能全部命中",
}


def _scan_depth(
    entry: LoreEntry | BackgroundEntry, collection: LoreCollection | BackgroundCollection | None
) -> int | None:
    default = (
        collection.activation_metadata.get("scan_depth", _DEFAULT_SCAN_DEPTH)
        if collection is not None
        else _DEFAULT_SCAN_DEPTH
    )
    depth = entry.activation_metadata.get("scanDepth")
    if depth is None:
        depth = default
    return min(depth, _MAX_SCAN_MESSAGES) if type(depth) is int and depth >= 0 else None


def _unsupported_reason(
    entry: LoreEntry | BackgroundEntry,
    collection: LoreCollection | BackgroundCollection | None,
    generation_kind: str = "normal",
) -> str | None:
    meta = entry.activation_metadata
    if _scan_depth(entry, collection) is None:
        return "扫描范围无效。"
    for key in (
        "constant",
        "selective",
        "case_sensitive",
        "caseSensitive",
        "matchWholeWords",
        "use_regex",
        "useProbability",
    ):
        if meta.get(key) is not None and type(meta[key]) is not bool:
            return "触发配置无效。"
    if (
        meta.get("case_sensitive") is not None
        and meta.get("caseSensitive") is not None
        and meta["case_sensitive"] != meta["caseSensitive"]
    ):
        return "大小写条件相互冲突。"
    if meta.get("useProbability") is True and meta.get("probability", 100) != 100:
        return "概率触发尚未支持。"
    if any(
        meta.get(key) not in (None, 0, False)
        for key in ("sticky", "cooldown", "delay", "delayUntilRecursion")
    ):
        return "持续、冷却、延迟或递归条件尚未支持。"
    if entry.group or meta.get("group"):
        return "互斥分组条件尚未支持。"
    filters = meta.get("characterFilter")
    if filters and (
        not isinstance(filters, Mapping) or filters.get("names") or filters.get("tags")
    ):
        return "角色筛选条件尚未支持。"
    triggers = meta.get("triggers")
    if triggers and (not isinstance(triggers, (tuple, list)) or generation_kind not in triggers):
        return (
            "来源未启用普通聊天触发。"
            if generation_kind == "normal"
            else "来源未启用后台生成触发。"
        )
    if any(
        meta.get(key) is True
        for key in (
            "matchPersonaDescription",
            "matchCharacterDescription",
            "matchCharacterPersonality",
            "matchCharacterDepthPrompt",
            "matchScenario",
            "matchCreatorNotes",
        )
    ):
        return "附加资料扫描尚未支持。"
    if meta.get("constant") is True:
        return None
    keys = entry.keywords + (entry.secondary_keywords if meta.get("selective") is True else ())
    if meta.get("use_regex") is True or any(key.startswith("/") or "{{" in key for key in keys):
        return "正则或模板关键词尚未支持。"
    if meta.get("selective") is True and entry.secondary_keywords:
        source = entry.extensions.get(LOREBOOK_METADATA_KEY, {})
        raw = source.get("source_entry", {}) if isinstance(source, Mapping) else {}
        if "selective_logic" not in meta and isinstance(raw, Mapping) and "selectiveLogic" in raw:
            return "来源次级条件无法识别。"
        logic = meta.get("selective_logic", "AND_ANY")
        if not isinstance(logic, str) or logic not in _LOGIC_NAMES:
            return "次级条件无法识别。"
    return None


def lore_activation_summary(
    entry: LoreEntry, collection: LoreCollection | None, *, generation_kind: str = "normal"
) -> str:
    """Explain the same policy used by chat and world planning, without dispatch."""
    if generation_kind not in ("normal", "quiet"):
        raise ValueError("unsupported_lore_generation_kind")
    target = "聊天" if generation_kind == "normal" else "日常规划"
    if not entry.enabled:
        return f"来源中已禁用，不参与{target}。"
    if reason := _unsupported_reason(entry, collection, generation_kind):
        return f"暂不参与{target}：" + reason
    if entry.activation_metadata.get("constant") is True:
        return f"公开后始终提供，受{target}背景容量限制。"
    if not entry.keywords:
        return f"没有关键词且未设常驻，暂不参与{target}。"
    depth = _scan_depth(entry, collection)
    if depth == 0:
        return "扫描范围为零，关键词不会触发。"
    meta = entry.activation_metadata
    summary = (
        f"公开后匹配最近 {depth} 条会话消息中的关键词。"
        if generation_kind == "normal"
        else "公开且已开启自动活动时，匹配角色名称和各自当前地点名称；下一批规划生效。"
    )
    if meta.get("case_sensitive", meta.get("caseSensitive")) is True:
        summary += "区分大小写。"
    if meta.get("matchWholeWords") is True:
        summary += "单词关键词要求完整词匹配。"
    if meta.get("selective") is True and entry.secondary_keywords:
        summary += "次级关键词需" + _LOGIC_NAMES[meta.get("selective_logic", "AND_ANY")] + "。"
    if meta.get("vectorized") is True:
        summary += "向量触发尚未接入。"
    return summary


def _matches(key: str, buffer: str, sensitive: bool, whole: bool) -> bool:
    if not key.strip():
        return False
    literal = key if sensitive else key.casefold()
    if whole and not any(c.isspace() for c in literal):
        return re.search(rf"(?<!\w){re.escape(literal)}(?!\w)", buffer) is not None
    return literal in buffer


def active_common_lore(
    entries: tuple[CommonLoreEntry | BackgroundItem, ...],
    texts: tuple[str, ...],
    *,
    generation_kind: str = "normal",
) -> tuple[CommonLoreEntry | BackgroundItem, ...]:
    """No hidden text, card fields, templates, regexes or recursive scans are read."""
    if generation_kind not in ("normal", "quiet"):
        raise ValueError("unsupported_lore_generation_kind")
    messages = texts[-_MAX_SCAN_MESSAGES:]
    buffers: dict[tuple[int, bool], str] = {}

    def scan(depth: int, sensitive: bool) -> str:
        cache_key = (depth, sensitive)
        if cache_key not in buffers:
            parts = []
            remaining = _MAX_SCAN_CHARS
            for text in reversed(messages[-depth:]):
                if remaining <= 0:
                    break
                part = text[-remaining:]
                parts.append(part)
                remaining -= len(part) + 1
            buffer = "\n".join(reversed(parts))
            buffers[cache_key] = buffer if sensitive else buffer.casefold()
        return buffers[cache_key]

    selected = []
    for item in entries:
        entry, meta = item.entry, item.entry.activation_metadata
        if not entry.enabled or _unsupported_reason(entry, item.collection, generation_kind):
            continue
        if meta.get("constant") is True:
            selected.append(item)
            continue
        depth = _scan_depth(entry, item.collection)
        if not depth or not entry.keywords:
            continue
        sensitive = meta.get("case_sensitive", meta.get("caseSensitive")) is True
        buffer = scan(depth, sensitive)

        whole = meta.get("matchWholeWords") is True
        if not any(_matches(key, buffer, sensitive, whole) for key in entry.keywords):
            continue
        if meta.get("selective") is True and entry.secondary_keywords:
            hits = [_matches(key, buffer, sensitive, whole) for key in entry.secondary_keywords]
            logic = meta.get("selective_logic", "AND_ANY")
            active = {
                "AND_ANY": any(hits),
                "AND_ALL": all(hits),
                "NOT_ANY": not any(hits),
                "NOT_ALL": not all(hits),
            }[logic]
            if not active:
                continue
        selected.append(item)
    return tuple(selected)


MAX_COMMON_LORE_BYTES = 12 * 1024
MAX_COMMON_LORE_ITEMS = 16


def select_common_background(
    entries: tuple[CommonLoreEntry | BackgroundItem, ...],
    texts: tuple[str, ...],
    *,
    generation_kind: str = "normal",
    include_references: bool = False,
) -> list[dict[str, str]]:
    """One activation/ranking/budget policy for chat and consented world planning."""
    active = active_common_lore(entries, texts, generation_kind=generation_kind)
    ordered = sorted(
        active,
        key=lambda item: (
            -int(item.entry.activation_metadata.get("constant") is not True),
            -item.entry.priority,
            item.entry.order,
            str(item.entry.content_id.value),
        ),
    )
    selected = []
    used = 0
    for item in ordered:
        size = len(item.entry.content.encode("utf-8")) + len(item.entry.title.encode("utf-8"))
        if size > MAX_COMMON_LORE_BYTES - used:
            continue
        value = {"title": item.entry.title, "content": item.entry.content}
        if include_references:
            value.update(import_id=str(item.import_id), entry_id=str(item.entry.content_id.value))
        selected.append(value)
        used += size
        if len(selected) == MAX_COMMON_LORE_ITEMS:
            break
    return selected
