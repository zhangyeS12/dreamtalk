"""Bounded chronological export of a fixed, owner-authorized transcript prefix."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256

from livingworld.application.errors import EntityNotFoundError
from livingworld.application.file_exports import export_filename
from livingworld.domain.identifiers import ConversationId, PlayerId


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class ChatExportSnapshot:
    conversation_id: ConversationId
    player_id: PlayerId
    world_name: str
    kind: str
    player_name: str
    characters: tuple[tuple[str, str], ...]
    through_position: int
    message_count: int

    def metadata(self):
        return {
            "world_id": str(self.conversation_id.world_id.value),
            "world_name": self.world_name,
            "conversation_id": str(self.conversation_id.value),
            "kind": self.kind,
            "player": {"id": str(self.player_id.value), "name": self.player_name},
            "characters": [{"id": identity, "name": name} for identity, name in self.characters],
            "through_position": self.through_position,
            "message_count": self.message_count,
        }

    @property
    def digest(self):
        return sha256(_json(self.metadata()).encode()).hexdigest()

    @property
    def title(self):
        return "、".join(name for _, name in self.characters)

    def filename(self, format):
        return export_filename(f"{self.world_name}-{self.title}-聊天记录", f".{format}")


class ChatExportService:
    def __init__(self, store, players):
        self._store, self._players = store, players

    async def snapshot(self, conversation, through_position=None, expected_player=None):
        player = await self._players.selected_player(conversation.world_id)
        if player is None or (expected_player is not None and player.value != expected_player):
            raise EntityNotFoundError("export_identity_changed")
        return await self._store.snapshot(conversation, player, through_position)

    async def stream(self, snapshot, format):
        metadata = {
            "format": "dreamtalk.chat",
            "version": 1,
            "exported_at_utc": datetime.now(UTC).isoformat(),
            **snapshot.metadata(),
        }
        if format == "json":
            yield (_json(metadata)[:-1] + ',"messages":[').encode("utf-8")
        else:
            yield (
                f"\ufeffdreamtalk 聊天记录\r\n世界：{snapshot.world_name}\r\n"
                f"会话：{snapshot.title}（{'群聊' if snapshot.kind == 'group' else '私聊'}）\r\n"
                f"消息数：{snapshot.message_count}\r\n"
                "真实时间使用 UTC；剧情发送时间单独保留。\r\n\r\n"
            ).encode()
        names = dict(snapshot.characters)
        cursor, count = 0, 0
        while cursor < snapshot.through_position:
            page = await self._store.page(snapshot, cursor)
            if not page:
                raise EntityNotFoundError("export_transcript_changed")
            for message in page:
                player = isinstance(message.sender_id, PlayerId)
                name = snapshot.player_name if player else names.get(str(message.sender_id.value))
                if name is None:
                    raise EntityNotFoundError("export_sender_unavailable")
                created = message.created_at_utc.astimezone(UTC).isoformat()
                story = (
                    message.story_sent_at_utc.astimezone(UTC).isoformat()
                    if message.story_sent_at_utc
                    else None
                )
                if format == "json":
                    value = {
                        "message_id": str(message.message_id.value),
                        "turn_id": str(message.turn_id.value),
                        "position": message.position,
                        "sender_kind": "player" if player else "character",
                        "sender_id": str(message.sender_id.value),
                        "sender_name": name,
                        "created_at_utc": created,
                        "story_sent_at_utc": story,
                        "text": message.text,
                    }
                    yield (("," if count else "") + _json(value)).encode("utf-8")
                else:
                    extra = f" · 剧情发送：{story}" if story else ""
                    yield (f"[{created}{extra}] {name}\r\n{message.text}\r\n\r\n").encode()
                count += 1
                cursor = message.position
        if count != snapshot.message_count:
            raise EntityNotFoundError("export_transcript_changed")
        if format == "json":
            yield b"]}\n"
