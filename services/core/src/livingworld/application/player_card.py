"""Parse a player-owned card without creating any world character or accepted import."""

import re
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from livingworld.application.imports import ContentImporter, ContentImportError
from livingworld.domain.content.models import CharacterDefinition
from livingworld.domain.content.serialization import serialize_content


@dataclass(frozen=True, slots=True)
class PlayerCardImport:
    card_id: UUID
    content_id: UUID
    reviewed_hash: str
    title: str
    summary: str = field(repr=False)
    excerpt: bool
    warnings: tuple[str, ...]
    payload: bytes = field(repr=False)
    snapshot_json: str = field(repr=False)


def parse_player_card(
    importer: ContentImporter, payload: bytes, imported_at: datetime
) -> PlayerCardImport:
    imported = importer.parse(payload, imported_at=imported_at)
    characters = [c for c in imported.draft.contents if isinstance(c, CharacterDefinition)]
    if len(characters) != 1:
        raise ContentImportError("player_card_character_required")
    character = characters[0]
    summary = "\n\n".join(
        text
        for text in (character.description, character.personality, character.background)
        if text
    )
    # In a player card, the original card owner becomes the player. Never evaluate templates.
    summary = re.sub(
        r"\{\{(char|user)\}\}",
        lambda match: character.display_name if match[1].lower() == "char" else "对话对象",
        summary,
        flags=re.IGNORECASE,
    )
    return PlayerCardImport(
        uuid4(),
        character.content_id.value,
        imported.draft.preview_hash(),
        character.display_name,
        summary[:2000],
        len(summary) > 2000,
        tuple(dict.fromkeys(warning.code for warning in imported.warnings)),
        payload,
        "[" + ",".join(serialize_content(c) for c in imported.draft.contents) + "]",
    )
