"""World-owned chat identities; opening a contact is not a world action."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol
from uuid import UUID, uuid5

from livingworld.application.command_handler import CommandHandler
from livingworld.application.commands import CreateCharacter
from livingworld.application.errors import EntityNotFoundError, IdempotencyConflictError
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
    read_only: bool = False


@dataclass(frozen=True, slots=True)
class GroupChatParticipant:
    character_id: CharacterId
    root_import_id: UUID
    character_name: str


@dataclass(frozen=True, slots=True)
class GroupChatConversation:
    conversation_id: ConversationId
    player_id: PlayerId
    participants: tuple[GroupChatParticipant, ...]
    read_only: bool = False


class ChatConversationStore(Protocol):
    async def dissolve_group(
        self, conversation_id: ConversationId, player_id: PlayerId
    ) -> None: ...
    async def bind_contact(self, character_id: CharacterId, root_import_id: UUID) -> None: ...
    async def activity_contacts(self, world_id: WorldId) -> tuple[GroupChatParticipant, ...]: ...
    async def open_direct(
        self,
        conversation_id: ConversationId,
        player_id: PlayerId,
        character_id: CharacterId,
        root_import_id: UUID,
    ) -> ChatConversation: ...

    async def list_for_player(self, player_id: PlayerId) -> tuple[ChatConversation, ...]: ...

    async def find_group(
        self, conversation_id: ConversationId, player_id: PlayerId
    ) -> GroupChatConversation | None: ...

    async def open_group(
        self,
        conversation_id: ConversationId,
        player_id: PlayerId,
        participants: tuple[GroupChatParticipant, ...],
    ) -> GroupChatConversation: ...

    async def list_groups_for_player(
        self, player_id: PlayerId
    ) -> tuple[GroupChatConversation, ...]: ...


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

    async def dissolve_group(self, world_id: WorldId, conversation_id: UUID) -> None:
        player = await self._players.selected_player(world_id)
        if player is None:
            raise EntityNotFoundError("selected_player_required")
        await self._store.dissolve_group(ConversationId(world_id, conversation_id), player)

    async def _ensure_character(self, world_id: WorldId, root: AcceptedWorldContent) -> CharacterId:
        character_id = CharacterId(world_id, uuid5(root.import_id, "livingworld:chat-character:v1"))
        await self._execute_command(
            CreateCharacter(
                request_id=RequestId(
                    uuid5(root.import_id, "livingworld:chat-character-command:v1")
                ),
                world_id=world_id,
                character_id=character_id,
                name=_character(root).display_name,
            )
        )
        await self._store.bind_contact(character_id, root.import_id)
        return character_id

    async def ensure_contact(self, world_id: WorldId, import_id: UUID) -> GroupChatParticipant:
        item = await self._imports.find(import_id)
        if (
            item is None
            or item.world_id != world_id
            or item.kind != "character"
            or not await self._imports.is_current(import_id)
        ):
            raise EntityNotFoundError("contact_not_found")
        root = await self._root(item)
        return GroupChatParticipant(
            await self._ensure_character(world_id, root),
            root.import_id,
            _character(item).display_name,
        )

    async def activity_contacts(self, world_id: WorldId) -> tuple[GroupChatParticipant, ...]:
        return await self._store.activity_contacts(world_id)

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
        character_id = await self._ensure_character(world_id, root)
        conversation_id = ConversationId(
            world_id, uuid5(player.value, f"livingworld:direct-chat:v1:{root.import_id}")
        )
        conversation = await self._store.open_direct(
            conversation_id, player, character_id, root.import_id
        )
        return replace(conversation, character_name=current_character.display_name)

    async def _current_names(self, world_id: WorldId, *, include_removed=False) -> dict[UUID, str]:
        names: dict[UUID, str] = {}
        for item in await self._imports.list_imports(world_id, include_removed=include_removed):
            if item.kind == "character":
                names[(await self._root(item)).import_id] = _character(item).display_name
        return names

    @staticmethod
    def _named_group(group: GroupChatConversation, names: dict[UUID, str]) -> GroupChatConversation:
        if any(item.root_import_id not in names for item in group.participants):
            raise EntityNotFoundError("contact_not_found")
        return replace(
            group,
            participants=tuple(
                replace(item, character_name=names[item.root_import_id])
                for item in group.participants
            ),
        )

    async def create_group(
        self, world_id: WorldId, request_id: RequestId, import_ids: tuple[UUID, ...]
    ) -> GroupChatConversation:
        if len(import_ids) < 2 or len(set(import_ids)) != len(import_ids):
            raise ValueError("group_members_invalid")
        player = await self._players.selected_player(world_id)
        if player is None:
            raise EntityNotFoundError("selected_player_required")
        conversation_id = ConversationId(
            world_id, uuid5(request_id.value, "livingworld:group-chat:v1")
        )
        selected: dict[UUID, tuple[AcceptedWorldContent, AcceptedWorldContent]] = {}
        for import_id in import_ids:
            item = await self._imports.find(import_id)
            if item is None or item.world_id != world_id or item.kind != "character":
                raise EntityNotFoundError("contact_not_found")
            root = await self._root(item)
            if root.import_id in selected:
                raise ValueError("group_members_invalid")
            selected[root.import_id] = (item, root)
        roots = tuple(sorted(selected, key=str))
        existing = await self._store.find_group(conversation_id, player)
        if existing is not None:
            if tuple(item.root_import_id for item in existing.participants) != roots:
                raise IdempotencyConflictError("group_request_conflict")
            return self._named_group(existing, await self._current_names(world_id))
        for item, _ in selected.values():
            if not await self._imports.is_current(item.import_id):
                raise EntityNotFoundError("contact_not_found")
        participants = []
        for root_id in roots:
            participants.append(
                GroupChatParticipant(
                    await self._ensure_character(world_id, selected[root_id][1]),
                    root_id,
                    _character(selected[root_id][0]).display_name,
                )
            )
        group = await self._store.open_group(conversation_id, player, tuple(participants))
        return self._named_group(group, await self._current_names(world_id))

    async def list_groups_for_world(self, world_id: WorldId) -> tuple[GroupChatConversation, ...]:
        player = await self._players.selected_player(world_id)
        if player is None:
            return ()
        names = await self._current_names(world_id, include_removed=True)
        active_names = await self._current_names(world_id)
        return tuple(
            replace(
                self._named_group(group, names),
                read_only=any(
                    member.root_import_id not in active_names for member in group.participants
                ),
            )
            for group in await self._store.list_groups_for_player(player)
        )

    async def list_for_world(self, world_id: WorldId) -> tuple[ChatConversation, ...]:
        player = await self._players.selected_player(world_id)
        if player is None:
            return ()
        conversations = await self._store.list_for_player(player)
        if not conversations:
            return ()
        current_names = await self._current_names(world_id, include_removed=True)
        active_names = await self._current_names(world_id)
        return tuple(
            replace(
                conversation,
                character_name=current_names[conversation.root_import_id],
                read_only=conversation.root_import_id not in active_names,
            )
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

    async def current_group_characters(
        self, conversation_id: ConversationId
    ) -> tuple[tuple[GroupChatParticipant, CharacterDefinition], ...]:
        """Resolve only this Player's current accepted personas for group context."""
        group = next(
            (
                item
                for item in await self.list_groups_for_world(conversation_id.world_id)
                if item.conversation_id == conversation_id
            ),
            None,
        )
        if group is None or group.read_only:
            raise EntityNotFoundError("conversation_not_found")
        required = {participant.root_import_id for participant in group.participants}
        current: dict[UUID, CharacterDefinition] = {}
        for item in await self._imports.list_imports(conversation_id.world_id):
            if item.kind != "character":
                continue
            root_id = (await self._root(item)).import_id
            if root_id in required:
                current[root_id] = _character(item)
        if set(current) != required:
            raise EntityNotFoundError("contact_not_found")
        return tuple(
            (participant, current[participant.root_import_id]) for participant in group.participants
        )
