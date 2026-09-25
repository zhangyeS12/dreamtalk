"""World-owned chat identities; opening a contact is not a world action."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol
from uuid import UUID, uuid5

from livingworld.application.command_handler import CommandHandler
from livingworld.application.commands import CreateCharacter
from livingworld.application.errors import EntityNotFoundError
from livingworld.application.player_event_feed import PlayerEventFeedService
from livingworld.application.world_content import AcceptedWorldContent, WorldContentService
from livingworld.domain.content.models import CharacterDefinition
from livingworld.domain.contracts import RequestId
from livingworld.domain.identifiers import CharacterId, ConversationId, PlayerId, WorldId


@dataclass(frozen=True, slots=True)
class ChatConversation:
    conversation_id: ConversationId
    player_id: PlayerId
    character_id: CharacterId
    root_import_id: UUID
    character_name: str


class ChatConversationStore(Protocol):
    async def open_direct(
        self,
        conversation_id: ConversationId,
        player_id: PlayerId,
        character_id: CharacterId,
        root_import_id: UUID,
    ) -> ChatConversation: ...

    async def list_for_player(self, player_id: PlayerId) -> tuple[ChatConversation, ...]: ...


def _character(item: AcceptedWorldContent) -> CharacterDefinition:
    characters = [root for root in item.contents if isinstance(root, CharacterDefinition)]
    if item.kind != "character" or len(characters) != 1:
        raise EntityNotFoundError("contact_not_found")
    return characters[0]


class ChatConversationService:
    def __init__(
        self,
        store: ChatConversationStore,
        imports: WorldContentService,
        players: PlayerEventFeedService,
        commands: CommandHandler,
    ) -> None:
        self._store = store
        self._imports = imports.store
        self._players = players
        self._execute_command = commands.execute

    async def _root(self, item: AcceptedWorldContent) -> AcceptedWorldContent:
        seen: set[UUID] = set()
        while item.replaces_import_id is not None:
            if item.import_id in seen:
                raise EntityNotFoundError("contact_lineage_invalid")
            seen.add(item.import_id)
            previous = await self._imports.find(item.replaces_import_id)
            if (
                previous is None
                or previous.world_id != item.world_id
                or previous.kind != "character"
            ):
                raise EntityNotFoundError("contact_lineage_invalid")
            item = previous
        return item

    async def open_direct(self, world_id: WorldId, import_id: UUID) -> ChatConversation:
        player = await self._players.selected_player(world_id)
        if player is None:
            raise EntityNotFoundError("selected_player_required")
        item = await self._imports.find(import_id)
        if (
            item is None
            or item.world_id != world_id
            or item.kind != "character"
            or not await self._imports.is_current(import_id)
        ):
            raise EntityNotFoundError("contact_not_found")
        current_character = _character(item)
        root = await self._root(item)
        root_character = _character(root)
        character_id = CharacterId(world_id, uuid5(root.import_id, "livingworld:chat-character:v1"))
        conversation_id = ConversationId(
            world_id, uuid5(player.value, f"livingworld:direct-chat:v1:{root.import_id}")
        )
        await self._execute_command(
            CreateCharacter(
                request_id=RequestId(
                    uuid5(root.import_id, "livingworld:chat-character-command:v1")
                ),
                world_id=world_id,
                character_id=character_id,
                name=root_character.display_name,
            )
        )
        conversation = await self._store.open_direct(
            conversation_id, player, character_id, root.import_id
        )
        return replace(conversation, character_name=current_character.display_name)

    async def list_for_world(self, world_id: WorldId) -> tuple[ChatConversation, ...]:
        player = await self._players.selected_player(world_id)
        if player is None:
            return ()
        conversations = await self._store.list_for_player(player)
        if not conversations:
            return ()
        current_names: dict[UUID, str] = {}
        for item in await self._imports.list_imports(world_id):
            if item.kind == "character":
                current_names[(await self._root(item)).import_id] = _character(item).display_name
        return tuple(
            replace(conversation, character_name=current_names[conversation.root_import_id])
            for conversation in conversations
            if conversation.root_import_id in current_names
        )

    async def current_direct_character(
        self, conversation_id: ConversationId
    ) -> CharacterDefinition:
        """Resolve the current accepted persona for this Player's existing direct chat."""

        conversations = await self.list_for_world(conversation_id.world_id)
        conversation = next(
            (item for item in conversations if item.conversation_id == conversation_id), None
        )
        if conversation is None:
            raise EntityNotFoundError("conversation_not_found")
        for item in await self._imports.list_imports(conversation_id.world_id):
            if (
                item.kind == "character"
                and (await self._root(item)).import_id == conversation.root_import_id
            ):
                return _character(item)
        raise EntityNotFoundError("contact_not_found")
