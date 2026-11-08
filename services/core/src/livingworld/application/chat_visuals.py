"""World-scoped chat backgrounds and character expression presentation."""

from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from livingworld.domain.identifiers import WorldId

ExpressionName = Literal[
    "neutral",
    "joy",
    "content",
    "sad",
    "angry",
    "surprised",
    "scared",
    "disgusted",
    "confused",
    "love",
    "embarrassed",
    "thinking",
]


@dataclass(frozen=True, slots=True)
class ChatCharacterExpression:
    root_import_id: UUID
    expression: ExpressionName
    digest: str


@dataclass(frozen=True, slots=True)
class ChatVisuals:
    common_background_digest: str | None
    character_backgrounds: dict[UUID, str]
    expressions: tuple[ChatCharacterExpression, ...]


class ChatVisualStore(Protocol):
    async def load(self, world: WorldId) -> ChatVisuals: ...

    async def set_common_background(self, world: WorldId, digest: str | None) -> ChatVisuals: ...

    async def set_character_background(
        self, world: WorldId, root_import_id: UUID, digest: str | None
    ) -> ChatVisuals: ...

    async def set_expression(
        self, world: WorldId, root_import_id: UUID, expression: ExpressionName, digest: str | None
    ) -> ChatVisuals: ...


class ChatVisualService:
    def __init__(self, store: ChatVisualStore) -> None:
        self.store = store

    async def load(self, world: WorldId) -> ChatVisuals:
        return await self.store.load(world)

    async def set_common_background(self, world: WorldId, digest: str | None) -> ChatVisuals:
        return await self.store.set_common_background(world, _digest(digest))

    async def set_character_background(
        self, world: WorldId, root_import_id: UUID, digest: str | None
    ) -> ChatVisuals:
        return await self.store.set_character_background(world, root_import_id, _digest(digest))

    async def set_expression(
        self, world: WorldId, root_import_id: UUID, expression: ExpressionName, digest: str | None
    ) -> ChatVisuals:
        return await self.store.set_expression(world, root_import_id, expression, _digest(digest))


def _digest(value: str | None) -> str | None:
    if value is None:
        return None
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("chat_visual_digest_invalid")
    return value
