"""Paged reads and sparse edits of an immutable, accepted content graph."""

from livingworld.application.content_authoring import EditorDraft, EditorEntry
from livingworld.application.imports import ContentImportError
from livingworld.application.lore_controls import LoreControls, editable_controls
from livingworld.domain.content.models import CharacterDefinition, LoreCollection, LoreEntry
from livingworld.domain.content.serialization import json_value


def entry_fields(entry):
    logic = entry.activation_metadata.get("selective_logic", "AND_ANY")
    return {
        "source_entry_id": entry.content_id.value,
        "title": entry.title,
        "content": entry.content,
        "keywords": list(entry.keywords),
        "secondary_keywords": list(entry.secondary_keywords),
        "enabled": entry.enabled,
        "constant": entry.activation_metadata.get("constant") is True,
        "advanced": editable_controls(entry).model_dump(),
        "selective_logic": logic
        if logic in ("AND_ANY", "AND_ALL", "NOT_ANY", "NOT_ALL")
        else "AND_ANY",
        "priority": entry.priority,
        "order": entry.order,
    }


def header_fields(item):
    if item.kind == "character":
        root = next(x for x in item.contents if isinstance(x, CharacterDefinition))
        card = json_value(root.authored_instructions.get("character_card", {}))
        return {
            "kind": "character",
            "name": root.display_name,
            **{
                key: getattr(root, key)
                for key in (
                    "description",
                    "personality",
                    "background",
                    "scenario",
                    "speech_guidance",
                    "creator_notes",
                )
            },
            "first_message": card.get("first_mes", "") if isinstance(card, dict) else "",
            "tags": list(root.tags),
            "example_dialogue": list(root.example_dialogue),
            "entries": [],
        }
    roots = [x for x in item.contents if isinstance(x, LoreCollection)]
    if len(roots) != 1:
        raise ContentImportError("editor_multiple_books_unsupported")
    return {
        "kind": "lorebook",
        "name": roots[0].name or "世界书",
        "description": roots[0].description,
        **{
            key: ""
            for key in (
                "personality",
                "background",
                "scenario",
                "speech_guidance",
                "first_message",
                "creator_notes",
            )
        },
        "tags": [],
        "example_dialogue": [],
        "entries": [],
    }


def editor_page(item, offset, limit=32):
    # Read projections are not new-authoring requests. An existing long field is
    # returned intact and need not be shortened just to edit a different field.
    entries = (
        [x for x in item.contents if isinstance(x, LoreEntry)] if item.kind == "lorebook" else []
    )
    draft = header_fields(item)
    draft["entries"] = [
        {**entry_fields(x), "source_entry_id": str(x.content_id.value)}
        for x in entries[offset : offset + limit]
    ]
    return {
        "draft": draft,
        "total_entries": len(entries),
        "offset": offset,
        "next_offset": offset + limit if offset + limit < len(entries) else None,
    }


def merge_editor_patch(item, header, updates, removed, added):
    fields = header_fields(item)
    if item.kind != "lorebook" and (updates or removed or added):
        raise ContentImportError("character_embedded_entries_are_preserved")
    fields.update(header)
    if not fields["name"].strip():
        raise ContentImportError("editor_draft_invalid")
    for key in ("tags", "example_dialogue"):
        if key in header and any(not text.strip() or len(text) > 8000 for text in header[key]):
            raise ContentImportError("editor_draft_invalid")
    originals = {x.content_id.value: x for x in item.contents if isinstance(x, LoreEntry)}
    removed = set(removed)
    update_ids = [key for key, _ in updates]
    if (
        len(set(update_ids)) != len(update_ids)
        or removed & set(update_ids)
        or not (removed | set(update_ids)) <= originals.keys()
    ):
        raise ContentImportError("editor_entry_target_invalid")
    changes = dict(updates)
    entries = []
    if item.kind == "lorebook":
        for identity, entry in originals.items():
            if identity in removed:
                continue
            raw = entry_fields(entry)
            patch = changes.get(identity, {})
            raw.update(patch)
            for key in ("keywords", "secondary_keywords"):
                if key in patch and any(not text.strip() or len(text) > 300 for text in raw[key]):
                    raise ContentImportError("editor_entry_invalid")
            if "content" in patch and not raw["content"].strip():
                raise ContentImportError("editor_entry_invalid")
            if (
                ("keywords" in patch or "secondary_keywords" in patch)
                and raw["secondary_keywords"]
                and not raw["keywords"]
            ):
                raise ContentImportError("editor_entry_invalid")
            # Only validated patch fields bypass old whole-draft limits; every
            # other value comes from this exact accepted immutable source.
            if isinstance(raw.get("advanced"), dict):
                raw["advanced"] = LoreControls.model_validate(raw["advanced"])
            entries.append(EditorEntry.model_construct(**raw))
        if any(entry.source_entry_id is not None for entry in added):
            raise ContentImportError("editor_entry_target_invalid")
        entries.extend(added)
        if not entries or len(entries) > 10000:
            raise ContentImportError("lorebook_entry_count_limit")
    fields["entries"] = entries
    return EditorDraft.model_construct(**fields)
