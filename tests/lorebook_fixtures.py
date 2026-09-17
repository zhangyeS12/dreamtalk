"""Small controlled data helpers, not external community book downloads."""

import json
from datetime import UTC, datetime
from pathlib import Path

from card_fixtures import card_document, card_text, json_bytes, png_bytes
from livingworld.domain.content.models import CharacterDefinition, LoreCollection, LoreEntry
from livingworld.infrastructure.imports.character_cards import CharacterCardImporter
from livingworld.infrastructure.imports.lorebooks import LorebookImporter

IMPORTED_AT = datetime(2026, 9, 17, tzinfo=UTC)


def book_document(embedded=False):
    name = "embedded_character_book.json" if embedded else "world_info.json"
    return json.loads((Path(__file__).parent / "fixtures/lorebooks" / name).read_text("utf-8"))


def standalone(document=None):
    return LorebookImporter().parse(
        json_bytes(document if document is not None else book_document()),
        imported_at=IMPORTED_AT,
        original_name="arbitrary-source-name.json",
    )


def preserved_card(version=3, book=None, container="json"):
    card = card_document(version)
    card["data"]["character_book"] = book_document(True) if book is None else book
    payload = (
        json_bytes(card)
        if container == "json"
        else png_bytes(card_text("chara" if version == 2 else "ccv3", card))
    )
    return CharacterCardImporter().parse(payload, imported_at=IMPORTED_AT, original_name="card.png")


def roots(imported):
    return (
        next(root for root in imported.draft.contents if isinstance(root, LoreCollection)),
        tuple(root for root in imported.draft.contents if isinstance(root, LoreEntry)),
        tuple(root for root in imported.draft.contents if isinstance(root, CharacterDefinition)),
    )


def codes(imported):
    return {warning.code for warning in imported.preview().warnings}


async def commit(repository, imported, expected=None):
    from livingworld.application.content import ContentService

    preview = imported.preview().content
    await ContentService(repository).commit(
        preview,
        reviewed_hash=preview.preview_hash,
        expected_revisions=expected
        if expected is not None
        else {root.content_id: None for root in imported.draft.contents},
    )
