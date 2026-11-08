"""Reviewed chat edits and local path selection; generation remains an explicit attempt."""

from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatPathError(ValueError):
    pass


class PathDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["branch", "checkpoint", "edit", "candidate", "switch", "rename"]
    revision: int = Field(ge=0, strict=True)
    message_id: UUID | None = None
    path_id: UUID | None = None
    name: str = Field(default="", max_length=80, strict=True)
    text: str = Field(default="", max_length=65536, strict=True)
    token_ceiling: int = Field(default=16384, ge=1, le=1_000_000, strict=True)


class PathConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")
    draft: PathDraft
    reviewed_hash: str = Field(min_length=64, max_length=64)
    confirmed: Literal[True]
    request_id: UUID

    @field_validator("confirmed", mode="before")
    @classmethod
    def explicit_confirmation(cls, value):
        if value is not True:
            raise ValueError("chat_path_confirmation_required")
        return value


class ChatPathStore(Protocol):
    async def snapshot(
        self, world: UUID, conversation: UUID, player: UUID, before: UUID | None = None
    ) -> dict: ...
    async def preview(
        self, world: UUID, conversation: UUID, player: UUID, draft: PathDraft
    ) -> dict: ...
    async def commit(
        self, world: UUID, conversation: UUID, player: UUID, request: PathConfirm
    ) -> dict: ...


class ChatPathService:
    def __init__(self, store: ChatPathStore, players):
        self._store, self._players = store, players

    async def _player(self, world: UUID) -> UUID:
        from livingworld.domain.identifiers import WorldId

        player = await self._players.selected_player(WorldId(world))
        if player is None:
            from livingworld.application.errors import EntityNotFoundError

            raise EntityNotFoundError("selected_player_required")
        return player.value

    async def snapshot(self, world: UUID, conversation: UUID, before: UUID | None = None) -> dict:
        return await self._store.snapshot(world, conversation, await self._player(world), before)

    async def preview(self, world: UUID, conversation: UUID, draft: PathDraft) -> dict:
        return await self._store.preview(world, conversation, await self._player(world), draft)

    async def commit(self, world: UUID, conversation: UUID, request: PathConfirm) -> dict:
        return await self._store.commit(world, conversation, await self._player(world), request)
