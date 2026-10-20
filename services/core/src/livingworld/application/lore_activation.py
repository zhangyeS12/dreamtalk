"""Literal Lorebook activation inside an already-authorized common-background set."""

import hashlib
import json
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
    insertion_metadata: Mapping | None = None


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
    for key, maximum in (
        ("probability", 100),
        ("sticky", 1000000),
        ("cooldown", 1000000),
        ("delay", 1000000),
        ("delayUntilRecursion", 32),
    ):
        value = meta.get(key)
        if key == "delayUntilRecursion" and type(value) is bool:
            continue
        if value is not None and (type(value) is not int or not 0 <= value <= maximum):
            return "概率或消息计数条件无效。"
    if meta.get("group") is not None and not isinstance(meta["group"], str):
        return "互斥组名称无效。"
    if generation_kind != "normal" and any(
        meta.get(key) for key in ("sticky", "cooldown", "delay")
    ):
        return "消息计数条件仅用于聊天。"
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
        return f"公开后参与常驻选择，仍受概率、延迟、冷却及{target}背景容量限制。"
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
        summary += "次级关键词需" + _LOGIC_NAMES[str(meta.get("selective_logic", "AND_ANY"))] + "。"
    summary += " 支持概率、递归、持续／冷却／延迟（按本路线消息数）；互斥组按优先级选择。"
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


@dataclass(frozen=True, slots=True)
class ActivationContext:
    seed: str = ""
    message_count: int = 0
    elapsed: Mapping[str, int] | None = None
    already: frozenset[str] = frozenset()


def entry_key(item) -> str:
    from livingworld.domain.content.serialization import json_value

    entry = item.entry
    value = [
        str(item.import_id),
        str(entry.content_id.value),
        entry.content,
        list(entry.keywords),
        list(entry.secondary_keywords),
        entry.priority,
        entry.order,
        entry.group,
        json_value(entry.activation_metadata),
        json_value(getattr(entry, "insertion_metadata", None) or {}),
        json_value(item.collection.activation_metadata) if item.collection else {},
    ]
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def _count(meta, key: str, default: int = 0) -> int:
    value = meta.get(key)
    if key == "delayUntilRecursion" and type(value) is bool:
        return int(value)
    return value if type(value) is int else default


def active_common_lore(
    entries: tuple[CommonLoreEntry | BackgroundItem, ...],
    texts: tuple[str, ...],
    *,
    generation_kind: str = "normal",
    context: ActivationContext | None = None,
) -> tuple[CommonLoreEntry | BackgroundItem, ...]:
    """Recursive scans only consume entries already authorized by the caller."""
    if generation_kind not in ("normal", "quiet"):
        raise ValueError("unsupported_lore_generation_kind")
    context = context or ActivationContext(
        seed=hashlib.sha256("\n".join(texts).encode()).hexdigest(), message_count=len(texts)
    )
    elapsed = context.elapsed or {}
    selected, recursive = {}, []
    remaining = sorted(
        (
            item
            for item in entries
            if item.entry.enabled
            and not _unsupported_reason(item.entry, item.collection, generation_kind)
        ),
        key=lambda item: (-item.entry.priority, item.entry.order, str(item.entry.content_id.value)),
    )
    keyed = [(entry_key(item), item) for item in remaining]
    occupied = set()
    # Each entry is selected at most once. A fixed recursion limit bounds work,
    # and recursive text has its own character budget instead of growing quadratically.
    for level in range(33):
        added = []
        for identity, item in keyed:
            entry, meta = item.entry, item.entry.activation_metadata
            if identity in selected:
                continue
            group = entry.group or meta.get("group")
            if group and group in occupied:
                continue
            if context.message_count < _count(meta, "delay"):
                continue
            age = elapsed.get(identity)
            sticky = age is not None and age < _count(meta, "sticky")
            reused = identity in context.already
            if (
                not sticky
                and not reused
                and age is not None
                and age < _count(meta, "sticky") + _count(meta, "cooldown")
            ):
                continue
            if not sticky and not reused:
                if level < _count(meta, "delayUntilRecursion"):
                    continue
                if (
                    level
                    and item.collection is not None
                    and item.collection.activation_metadata.get("recursive_scanning") is False
                ):
                    continue
                if level and meta.get("excludeRecursion") is True:
                    continue
                sensitive = meta.get("case_sensitive", meta.get("caseSensitive")) is True
                depth = _scan_depth(entry, item.collection)
                base = "\n".join(texts[-depth:])[-_MAX_SCAN_CHARS:] if depth else ""
                buffer = base if level == 0 else "\n".join(recursive)[-_MAX_SCAN_CHARS:]
                if not sensitive:
                    buffer = buffer.casefold()
                whole = meta.get("matchWholeWords") is True
                constant = meta.get("constant") is True
                if not constant and not any(
                    _matches(key, buffer, sensitive, whole) for key in entry.keywords
                ):
                    continue
                if not constant and meta.get("selective") is True and entry.secondary_keywords:
                    hits = [
                        _matches(key, buffer, sensitive, whole) for key in entry.secondary_keywords
                    ]
                    if not {
                        "AND_ANY": any(hits),
                        "AND_ALL": all(hits),
                        "NOT_ANY": not any(hits),
                        "NOT_ALL": not all(hits),
                    }[str(meta.get("selective_logic", "AND_ANY"))]:
                        continue
                probability = (
                    _count(meta, "probability", 100) if meta.get("useProbability") is True else 100
                )
                draw = (
                    int(hashlib.sha256((context.seed + identity).encode()).hexdigest()[:16], 16)
                    % 100
                )
                if draw >= probability:
                    continue
            selected[identity] = item
            if group:
                occupied.add(group)
            if meta.get("preventRecursion") is not True:
                added.append(entry.content[:_MAX_SCAN_CHARS])
        if not added:
            break
        recursive = (recursive + added)[-MAX_COMMON_LORE_ITEMS:]
    return tuple(selected.values())


MAX_COMMON_LORE_BYTES = 12 * 1024
MAX_COMMON_LORE_ITEMS = 16


def select_common_background(
    entries: tuple[CommonLoreEntry | BackgroundItem, ...],
    texts: tuple[str, ...],
    *,
    generation_kind: str = "normal",
    include_references: bool = False,
    context: ActivationContext | None = None,
) -> list[dict[str, str | int]]:
    """One activation/ranking/budget policy for chat and consented world planning."""
    active = active_common_lore(entries, texts, generation_kind=generation_kind, context=context)
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
        value: dict[str, str | int] = {"title": item.entry.title, "content": item.entry.content}
        insertion = getattr(item.entry, "insertion_metadata", None) or {}
        depth = insertion.get("depth")
        position = insertion.get("position")
        if (
            generation_kind == "normal"
            and (position in (4, "at_depth", "in_chat") or insertion.get("mode") == "at_depth")
            and type(depth) is int
            and 0 <= depth <= 32
        ):
            value["_chat_depth"] = depth
        if include_references:
            value.update(import_id=str(item.import_id), entry_id=str(item.entry.content_id.value))
        selected.append(value)
        used += size
        if len(selected) == MAX_COMMON_LORE_ITEMS:
            break
    return selected
