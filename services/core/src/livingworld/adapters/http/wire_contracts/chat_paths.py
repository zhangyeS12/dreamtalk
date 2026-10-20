from typing import Literal, TypedDict

from pydantic import ConfigDict, with_config

from livingworld.application.chat_paths import PathDraft


@with_config(ConfigDict(extra="forbid"))
class ChatPath(TypedDict):
    path_id: str
    parent_id: str | None
    name: str
    kind: Literal["main", "branch", "checkpoint", "candidate", "edit"]
    created_at: str
    fork_message_id: str | None


@with_config(ConfigDict(extra="forbid"))
class ChatPathSnapshot(TypedDict):
    active: ChatPath
    revision: int
    paths: list[ChatPath]
    next_before: str | None


@with_config(ConfigDict(extra="forbid"))
class ChatPathPreview(TypedDict):
    reviewed_hash: str
    draft: PathDraft
    original_text: str | None
    calls_model: bool
    creates_path: bool


@with_config(ConfigDict(extra="forbid"))
class ChatPathResult(TypedDict):
    path_id: str
    revision: int
    turn_id: str | None
