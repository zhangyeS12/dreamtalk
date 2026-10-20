"""Typed HTTP composition. Partial embeddings are explicit; production fails on missing services."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, fields
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from livingworld.application.character_activity_setup import CharacterActivitySetupService
    from livingworld.application.chat_conversations import ChatConversationService
    from livingworld.application.chat_export import ChatExportService
    from livingworld.application.chat_media import ChatMediaService
    from livingworld.application.chat_messages import ChatMessageService
    from livingworld.application.chat_paths import ChatPathService
    from livingworld.application.chat_recall import EarlierChatRecall
    from livingworld.application.chat_reply import DirectChatReplyService
    from livingworld.application.content import ContentRepository
    from livingworld.application.content_builder import ContentBuilder
    from livingworld.application.conversation_memory import ConversationMemoryService
    from livingworld.application.developer_inspector import DeveloperInspectorService
    from livingworld.application.director import DirectorService
    from livingworld.application.example_worlds import ExampleWorldService
    from livingworld.application.group_chat_reply import GroupChatReplyService
    from livingworld.application.local_profile import LocalProfileStore
    from livingworld.application.long_chat_memory import LongChatMemoryService
    from livingworld.application.offline_contact import OfflineContactService
    from livingworld.application.player_event_feed import PlayerEventFeedService
    from livingworld.application.player_onboarding import LocalPlayerOnboardingService
    from livingworld.application.player_persona import PlayerPersonaService
    from livingworld.application.proactive_contact import ProactiveContactService
    from livingworld.application.speech import SpeechService
    from livingworld.application.update_maintenance import UpdateMaintenance
    from livingworld.application.world_content import WorldContentService
    from livingworld.application.world_content_export import WorldContentExportService
    from livingworld.application.world_covers import WorldCoverService
    from livingworld.application.world_deletion import WorldDeletionService
    from livingworld.application.world_locations import WorldLocationsService
    from livingworld.application.world_model_config import WorldModelValue
    from livingworld.application.world_settings import WorldSettingsService
    from livingworld.application.world_story import WorldStoryService
    from livingworld.application.world_style import WorldStyleService
    from livingworld.infrastructure.persistence.factions import SqlAlchemyFactionStore


@dataclass(frozen=True, kw_only=True)
class HttpServices:
    """Optional services for focused embeddings; require_product checks the desktop composition."""

    developer_inspector: DeveloperInspectorService | None = None
    world_settings: WorldSettingsService | None = None
    player_event_feed: PlayerEventFeedService | None = None
    local_profiles: LocalProfileStore | None = None
    world_style: WorldStyleService | None = None
    player_persona: PlayerPersonaService | None = None
    world_content: WorldContentService | None = None
    player_onboarding: LocalPlayerOnboardingService | None = None
    chat_conversations: ChatConversationService | None = None
    chat_messages: ChatMessageService | None = None
    chat_paths: ChatPathService | None = None
    chat_reply: DirectChatReplyService | WorldModelValue[DirectChatReplyService | None] | None = (
        None
    )
    group_chat_reply: (
        GroupChatReplyService | WorldModelValue[GroupChatReplyService | None] | None
    ) = None
    content_builder: ContentBuilder | None = None
    content_repository: ContentRepository | None = None
    chat_recall: EarlierChatRecall | None = None
    conversation_memory: ConversationMemoryService | None = None
    long_chat_memory: LongChatMemoryService | None = None
    director: DirectorService | None = None
    world_story: WorldStoryService | None = None
    offline_contact: OfflineContactService | None = None
    proactive_contact: ProactiveContactService | None = None
    world_locations: WorldLocationsService | None = None
    character_activity_setup: CharacterActivitySetupService | None = None
    world_covers: WorldCoverService | None = None
    factions: SqlAlchemyFactionStore | None = None
    maintenance: UpdateMaintenance | None = None
    world_deletion: WorldDeletionService | None = None
    content_exports: WorldContentExportService | None = None
    chat_exports: ChatExportService | None = None
    speech: SpeechService | None = None
    chat_media: ChatMediaService | None = None
    storage_metadata: Callable[[], dict[str, object]] | None = None
    storage_observer: Callable[[], None] | None = None
    example_worlds: ExampleWorldService | None = None

    def require_product(self) -> None:
        optional = {
            "developer_inspector",
            "storage_metadata",
            "storage_observer",
            "chat_reply",
            "group_chat_reply",
        }
        missing = [
            field.name
            for field in fields(self)
            if field.name not in optional and getattr(self, field.name) is None
        ]
        if missing:
            raise ValueError("Missing product HTTP services: " + ", ".join(missing))
