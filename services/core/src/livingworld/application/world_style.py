"""Reviewed world-scoped writing preferences, independent of world truth and card identity."""

import hashlib
import hmac
import json
from dataclasses import dataclass, field
from typing import Protocol

from livingworld.domain.errors import ConcurrencyConflictError
from livingworld.domain.identifiers import WorldId

MAX_STYLE_CHARACTERS = 4000
MAX_STYLE_JSON_BYTES = 16000


@dataclass(frozen=True, slots=True)
class WorldStyle:
    instructions: str = field(default="", repr=False)
    revision: int = 0


class WorldStyleStore(Protocol):
    async def load(self, world: WorldId) -> WorldStyle: ...

    async def save(self, world: WorldId, style: WorldStyle) -> WorldStyle: ...


def validate_style(instructions: str) -> str:
    try:
        size = len(json.dumps(instructions, ensure_ascii=False).encode("utf-8"))
    except UnicodeError:
        raise ValueError("world_style_invalid") from None
    if len(instructions) > MAX_STYLE_CHARACTERS or size > MAX_STYLE_JSON_BYTES:
        raise ValueError("world_style_capacity")
    return instructions.strip()


def style_preview_id(world: WorldId, style: WorldStyle) -> str:
    payload = json.dumps(
        ["world-style-v1", str(world.value), style.revision, style.instructions],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class WorldStyleService:
    def __init__(self, store: WorldStyleStore) -> None:
        self.store = store

    async def preview(self, world: WorldId, instructions: str, revision: int) -> WorldStyle:
        style = WorldStyle(validate_style(instructions), revision)
        if (await self.store.load(world)).revision != revision:
            raise ConcurrencyConflictError("world_style_conflict")
        return style

    async def confirm(
        self, world: WorldId, instructions: str, revision: int, preview_id: str
    ) -> WorldStyle:
        style = await self.preview(world, instructions, revision)
        if not hmac.compare_digest(style_preview_id(world, style), preview_id):
            raise ValueError("world_style_preview_changed")
        return await self.store.save(world, style)


def world_style_prompt(instructions: str) -> str:
    if not instructions.strip():
        return ""
    return (
        "【当前世界风格；最高写作优先级】\n"
        "以下是用户确认的世界题材、内容尺度与叙事约定；与角色卡写作要求或示例冲突时，"
        "在这些写作维度优先采用世界风格。人物身份、性格、偏好仍以角色卡为准，"
        "关系与互动承接真实对话，不把允许某类情节当成角色必须答应或关系已经发生。"
        "这是虚构叙事约定，不授予私有知识、工具或程序权限，不改变传输格式、玩家自主权和Token预算。\n"
        + instructions
        + "\n【世界风格结束】\n"
    )


DIALOGUE_PRESENTATION = (
    "角色说出口的话用中文双引号“”包围；动作、场景、神态和心理放在引号外，"
    "可以使用Markdown。不要为了排版重复说话内容。"
)
