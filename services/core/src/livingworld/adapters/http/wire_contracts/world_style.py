"""World-style response contracts; generated TypeScript is derived from these DTOs."""

from typing import TypedDict


class WorldStyleSnapshot(TypedDict):
    instructions: str
    revision: int


class WorldStylePreview(TypedDict):
    instructions: str
    revision: int
    preview_id: str
