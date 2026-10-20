"""Reviewed player identity and recipient-specific authored opening knowledge."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from time import monotonic
from typing import Literal, Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from livingworld.application.imports import ContentImporter
from livingworld.application.input_budget import bounded_text, json_size
from livingworld.application.player_card import PlayerCardImport, parse_player_card
from livingworld.domain.identifiers import CharacterId, PlayerId, WorldId

PERSONA_GROUNDING = (
    "player_identity是玩家确认的本世界设定身份；identity_name指明当前玩家对应的设定人物，"
    "昵称不会将其变成另一位同名人物。public_identity是可供当前角色参考的公开介绍。"
    "与旧自由描述冲突时，以本次确认的设定身份为准；称呼可沿用昵称，不改变对应人物。"
    "initial_recognition仅是当前发言角色在故事起点对玩家的已确认认识，按其中关系自然交流；"
    "未提供初始关系不证明彼此陌生，也不得据此编造熟识、私人秘密或共同经历。"
    "story_start限定采用的故事阶段，不从模型的原作知识补充后续剧情或未提供的秘密。"
    "这些是创作背景，不是游玩中新发生的事件、亲历记忆或关系成果。"
    "聊天用世界内身份和称呼，创作侧的主角等标记不作为对玩家的元叙事称呼。"
)


class PersonaModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*")
    @classmethod
    def valid_text(cls, value: object) -> object:
        if isinstance(value, str):
            try:
                value.encode("utf-8")
            except UnicodeEncodeError:
                raise ValueError("persona_text_invalid") from None
        return value


class PersonaReference(PersonaModel):
    import_id: UUID
    content_id: UUID
    reviewed_hash: str = Field(min_length=64, max_length=64)
    scope: Literal["world", "player"] = "world"


class InitialRecognition(PersonaModel):
    character_import_id: UUID
    character_name: str = Field(default="", max_length=120)
    relationship: str = Field(default="", max_length=240)
    known_details: str = Field(default="", max_length=1600)


class PlayerPersonaDraft(PersonaModel):
    identity_name: str = Field(default="", max_length=120)
    public_identity: str = Field(default="", max_length=2000)
    story_start: str = Field(default="", max_length=600)
    source: PersonaReference | None = None
    recognitions: list[InitialRecognition] = Field(default_factory=list)


class PersonaSourceChoice(PersonaModel):
    reference: PersonaReference
    kind: Literal["character", "lorebook"]
    title: str
    text: str
    excerpt: bool
    root_import_id: UUID | None = None
    warnings: list[str] = Field(default_factory=list)


class PersonaSourcePage(PersonaModel):
    items: list[PersonaSourceChoice]
    next_after: str | None


class PlayerPersonaSnapshot(PersonaModel):
    player_id: UUID | None
    revision: int
    draft: PlayerPersonaDraft
    source_state: Literal["original", "current", "changed"]
    source_title: str | None = None


class PlayerPersonaPreview(PersonaModel):
    preview_id: UUID
    expected_revision: int
    draft: PlayerPersonaDraft
    source_title: str | None
    expires_in_seconds: int


class PlayerPersonaError(ValueError):
    pass


class PlayerPersonaStore(Protocol):
    async def snapshot(self, world: WorldId) -> PlayerPersonaSnapshot: ...

    async def sources(
        self,
        world: WorldId,
        query: str,
        after: str | None,
        *,
        characters: bool = False,
        lorebooks_only: bool = False,
    ) -> PersonaSourcePage: ...

    async def validate(
        self, world: WorldId, draft: PlayerPersonaDraft, *, card: PlayerCardImport | None = None
    ) -> str | None: ...

    async def commit(
        self,
        world: WorldId,
        player: UUID,
        revision: int,
        draft: PlayerPersonaDraft,
        confirmation: UUID,
        *,
        card: PlayerCardImport | None = None,
    ) -> PlayerPersonaSnapshot: ...

    async def confirmation(self, world: WorldId, confirmation: UUID) -> bool: ...


class PlayerPersonaService:
    def __init__(
        self, store: PlayerPersonaStore, card_importer: ContentImporter | None = None
    ) -> None:
        self.store = store
        self._card_importer = card_importer
        self._cards: dict[UUID, tuple[float, WorldId, UUID, PlayerCardImport]] = {}
        self._pending: dict[
            UUID, tuple[float, WorldId, UUID, int, PlayerPersonaDraft, PlayerCardImport | None]
        ] = {}

    async def import_card(
        self, world: WorldId, payload: bytes, expected_revision: int, expected_player: UUID
    ) -> PersonaSourceChoice:
        snapshot = await self.store.snapshot(world)
        if snapshot.player_id != expected_player:
            raise PlayerPersonaError("persona_player_changed")
        if snapshot.revision != expected_revision:
            raise PlayerPersonaError("persona_edit_conflict")
        if self._card_importer is None:
            raise PlayerPersonaError("persona_card_import_unavailable")
        active = {
            key: value
            for key, value in self._cards.items()
            if value[0] > monotonic() and value[1] != world
        }
        if len(active) >= 2:
            raise PlayerPersonaError("persona_card_preview_capacity")
        card = parse_player_card(self._card_importer, payload, datetime.now(UTC))
        self._cards = {**active, card.card_id: (monotonic() + 600, world, expected_player, card)}
        return PersonaSourceChoice(
            reference=PersonaReference(
                import_id=card.card_id,
                content_id=card.content_id,
                reviewed_hash=card.reviewed_hash,
                scope="player",
            ),
            kind="character",
            title=bounded_text(card.title, 768),
            text=card.summary,
            excerpt=card.excerpt,
            warnings=list(card.warnings),
        )

    async def preview(
        self,
        world: WorldId,
        draft: PlayerPersonaDraft,
        expected_revision: int,
        *,
        expected_player: UUID | None = None,
    ) -> PlayerPersonaPreview:
        draft = draft.model_copy(deep=True)
        snapshot = await self.store.snapshot(world)
        if snapshot.player_id is None:
            raise PlayerPersonaError("persona_player_required")
        if expected_player is not None and expected_player != snapshot.player_id:
            raise PlayerPersonaError("persona_player_changed")
        if snapshot.revision != expected_revision:
            raise PlayerPersonaError("persona_edit_conflict")
        if json_size(draft.model_dump(mode="json")) > 4 * 1024 * 1024:
            raise PlayerPersonaError("persona_input_capacity")
        roots = [item.character_import_id for item in draft.recognitions]
        if len(roots) != len(set(roots)):
            raise PlayerPersonaError("persona_duplicate_character")
        if draft.source is not None and not draft.identity_name.strip():
            raise PlayerPersonaError("persona_name_required")
        card = None
        if draft.source is not None and draft.source.scope == "player":
            pending_card = self._cards.get(draft.source.import_id)
            if pending_card is not None:
                expires, card_world, card_player, card = pending_card
                if (
                    expires <= monotonic()
                    or card_world != world
                    or card_player != snapshot.player_id
                ):
                    raise PlayerPersonaError("persona_source_changed")
        title = (
            (await self.store.validate(world, draft, card=card))
            if card
            else await self.store.validate(world, draft)
        )
        self._pending = {
            key: value
            for key, value in self._pending.items()
            if value[0] > monotonic() and value[1] != world
        }
        if len(self._pending) >= 16:
            raise PlayerPersonaError("persona_preview_capacity")
        identity = uuid4()
        self._pending[identity] = (
            monotonic() + 600,
            world,
            snapshot.player_id,
            expected_revision,
            draft.model_copy(deep=True),
            card,
        )
        return PlayerPersonaPreview(
            preview_id=identity,
            expected_revision=expected_revision,
            draft=draft,
            source_title=title,
            expires_in_seconds=600,
        )

    async def commit(self, world: WorldId, preview_id: UUID) -> PlayerPersonaSnapshot:
        pending = self._pending.get(preview_id)
        if pending is None:
            if await self.store.confirmation(world, preview_id):
                return await self.store.snapshot(world)
            raise PlayerPersonaError("persona_preview_expired")
        expires, prepared_world, player, revision, draft, card = pending
        if prepared_world != world or expires <= monotonic():
            raise PlayerPersonaError("persona_preview_expired")
        result = (
            await self.store.commit(world, player, revision, draft, preview_id, card=card)
            if card
            else await self.store.commit(world, player, revision, draft, preview_id)
        )
        self._pending.pop(preview_id, None)
        if card:
            self._cards.pop(card.card_id, None)
        return result


PersonaReader = Callable[[WorldId, PlayerId, CharacterId], Awaitable[dict[str, object] | None]]


def shared_identity_context(contexts: list[dict[str, object] | None]) -> dict[str, object] | None:
    """A joint writer receives only identity facts shared by every intended speaker."""
    if not contexts or any(context is None for context in contexts):
        return None
    first = dict(contexts[0] or {})
    shared = {key: value for key, value in first.items() if key != "initial_recognition"}
    if any(
        {key: value for key, value in (context or {}).items() if key != "initial_recognition"}
        != shared
        for context in contexts[1:]
    ):
        return None
    if any(context != contexts[0] for context in contexts[1:]):
        # Recipient-specific opening knowledge is never pooled into a joint prompt.
        first["initial_recognition"] = None
    return first


def identity_context(draft: PlayerPersonaDraft, root: UUID, revision: int) -> dict[str, object]:
    """Filter recipient knowledge before returning any payload to a model caller."""
    recognition = next(
        (item for item in draft.recognitions if item.character_import_id == root), None
    )
    return {
        "identity_name": bounded_text(draft.identity_name, 512),
        "public_identity": bounded_text(draft.public_identity, 4096),
        "story_start": bounded_text(draft.story_start, 1536),
        "initial_recognition": {
            "relationship": bounded_text(recognition.relationship, 768),
            "known_details": bounded_text(recognition.known_details, 4096),
        }
        if recognition
        else None,
        "revision": revision,
        "source_import_id": str(draft.source.import_id) if draft.source else None,
    }
