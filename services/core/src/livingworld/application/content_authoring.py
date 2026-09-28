"""Native authored drafts, preserving the closed graph of an edited import."""

from dataclasses import replace
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from livingworld.application.content import ContentDraft
from livingworld.application.imports import ContentImportError
from livingworld.domain.content.identifiers import (
    CharacterDefinitionId,
    LoreCollectionId,
    LoreEntryId,
)
from livingworld.domain.content.models import (
    CharacterDefinition,
    ContentProvenance,
    ContentRevision,
    ContentSourceKind,
    LoreCollection,
    LoreEntry,
)
from livingworld.domain.content.serialization import json_value


class EditorEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_entry_id: UUID | None = None
    title: str = Field(default="", max_length=300)
    content: str = Field(min_length=1, max_length=16000)
    keywords: list[str] = Field(default_factory=list, max_length=64)
    secondary_keywords: list[str] = Field(default_factory=list, max_length=64)
    enabled: bool = True
    constant: bool = False
    selective_logic: str = Field(default="AND_ANY", pattern="^(AND_ANY|AND_ALL|NOT_ANY|NOT_ALL)$")
    priority: int = Field(default=0, ge=-1000000, le=1000000)
    order: int = Field(default=0, ge=-1000000, le=1000000)

    @model_validator(mode="after")
    def valid_entry(self):
        if (
            not self.content.strip()
            or any(
                not key.strip() or len(key) > 300 for key in self.keywords + self.secondary_keywords
            )
            or self.secondary_keywords
            and not self.keywords
        ):
            raise ValueError("editor_entry_invalid")
        return self


class EditorDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: str = Field(pattern="^(character|lorebook)$")
    name: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=16000)
    personality: str = Field(default="", max_length=16000)
    background: str = Field(default="", max_length=16000)
    scenario: str = Field(default="", max_length=16000)
    speech_guidance: str = Field(default="", max_length=16000)
    first_message: str = Field(default="", max_length=16000)
    creator_notes: str = Field(default="", max_length=16000)
    tags: list[str] = Field(default_factory=list, max_length=64)
    example_dialogue: list[str] = Field(default_factory=list, max_length=32)
    entries: list[EditorEntry] = Field(default_factory=list, max_length=128)

    @model_validator(mode="after")
    def valid_draft(self):
        if not self.name.strip() or any(
            not x.strip() or len(x) > 8000 for x in self.tags + self.example_dialogue
        ):
            raise ValueError("editor_draft_invalid")
        if self.kind == "character" and self.entries:
            raise ValueError("character_embedded_entries_are_preserved")
        if len(self.model_dump_json().encode("utf-8")) > 256 * 1024:
            raise ValueError("editor_draft_too_large")
        return self


def editable(item) -> EditorDraft:
    if item.kind == "character":
        root = next(x for x in item.contents if isinstance(x, CharacterDefinition))
        card = json_value(root.authored_instructions.get("character_card", {}))
        first = card.get("first_mes", "") if isinstance(card, dict) else ""
        return EditorDraft(
            kind="character",
            name=root.display_name,
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
            first_message=first if isinstance(first, str) else "",
            tags=list(root.tags),
            example_dialogue=list(root.example_dialogue),
        )
    books = [x for x in item.contents if isinstance(x, LoreCollection)]
    if len(books) != 1:
        raise ContentImportError("editor_multiple_books_unsupported")
    root = books[0]
    return EditorDraft(
        kind="lorebook",
        name=root.name or "世界书",
        description=root.description,
        entries=[
            EditorEntry(
                source_entry_id=x.content_id.value,
                title=x.title,
                content=x.content,
                keywords=list(x.keywords),
                secondary_keywords=list(x.secondary_keywords),
                enabled=x.enabled,
                constant=x.activation_metadata.get("constant") is True,
                selective_logic=x.activation_metadata.get("selective_logic", "AND_ANY")
                if x.activation_metadata.get("selective_logic", "AND_ANY")
                in ("AND_ANY", "AND_ALL", "NOT_ANY", "NOT_ALL")
                else "AND_ANY",
                priority=x.priority,
                order=x.order,
            )
            for x in item.contents
            if isinstance(x, LoreEntry)
        ],
    )


async def authored_graph(fields: EditorDraft, previous, repository, research=None) -> ContentDraft:
    if fields.kind == "lorebook" and not fields.entries:
        raise ContentImportError("lorebook_entries_required")
    old = previous.contents if previous else ()
    # Every revision is an independent graph; previous snapshots remain immutable.
    ids = {x.content_id: type(x.content_id)(uuid4()) for x in old}
    copied = []
    for root in old:
        changes = {"content_id": ids[root.content_id], "revision": ContentRevision()}
        if isinstance(root, LoreEntry):
            changes["collection_id"] = ids.get(root.collection_id, root.collection_id)
        if isinstance(root, (CharacterDefinition, LoreCollection)):
            changes["lore_entry_ids"] = tuple(ids[x] for x in root.lore_entry_ids)
        if isinstance(root, CharacterDefinition):
            changes["lore_collection_ids"] = tuple(ids[x] for x in root.lore_collection_ids)
        copied.append(replace(root, **changes))
    provenance = ContentProvenance(
        source_kind=ContentSourceKind.BUILDER if research else ContentSourceKind.NATIVE,
        source_format="dreamtalk-editor",
    )
    if fields.kind == "character":
        root = next((x for x in copied if isinstance(x, CharacterDefinition)), None)
        if root is None:
            root = CharacterDefinition(
                content_id=CharacterDefinitionId(uuid4()),
                display_name=fields.name,
                provenance=provenance,
            )
        extensions = json_value(root.extensions)
        instructions = json_value(root.authored_instructions)
        card = instructions.get("character_card", {})
        if not isinstance(card, dict):
            card = {}
        instructions["character_card"] = {**card, "first_mes": fields.first_message}
        root = replace(
            root,
            provenance=provenance,
            display_name=fields.name,
            **{
                key: getattr(fields, key)
                for key in (
                    "description",
                    "personality",
                    "background",
                    "scenario",
                    "speech_guidance",
                    "creator_notes",
                )
            },
            tags=tuple(fields.tags),
            example_dialogue=tuple(fields.example_dialogue),
            authored_instructions=instructions,
        )
        copied = [x for x in copied if not isinstance(x, CharacterDefinition)]
    else:
        root = next((x for x in copied if isinstance(x, LoreCollection)), None)
        if root is None:
            root = LoreCollection(
                content_id=LoreCollectionId(uuid4()), name=fields.name, provenance=provenance
            )
        extensions = json_value(root.extensions)
        old_entries = {x.content_id.value: x for x in old if isinstance(x, LoreEntry)}
        entries, seen = [], set()
        for field in fields.entries:
            original = old_entries.get(field.source_entry_id)
            if field.source_entry_id is not None:
                if original is None or field.source_entry_id in seen:
                    raise ContentImportError("editor_entry_target_invalid")
                seen.add(field.source_entry_id)
            entry = (
                replace(
                    original,
                    content_id=ids[original.content_id],
                    revision=ContentRevision(),
                    collection_id=root.content_id,
                )
                if original
                else LoreEntry(
                    content_id=LoreEntryId(uuid4()),
                    collection_id=root.content_id,
                    content=field.content,
                    provenance=provenance,
                )
            )
            meta = json_value(entry.activation_metadata)
            if original is None:
                meta.update(
                    constant=field.constant,
                    selective=bool(field.secondary_keywords),
                    selective_logic=field.selective_logic,
                )
            else:
                # An untouched basic control must not reinterpret opaque imported conditions.
                if field.constant != (original.activation_metadata.get("constant") is True):
                    meta["constant"] = field.constant
                if tuple(field.secondary_keywords) != original.secondary_keywords:
                    meta["selective"] = bool(field.secondary_keywords)
                old_logic = original.activation_metadata.get("selective_logic", "AND_ANY")
                if old_logic not in ("AND_ANY", "AND_ALL", "NOT_ANY", "NOT_ALL"):
                    old_logic = "AND_ANY"
                if field.selective_logic != old_logic:
                    meta["selective_logic"] = field.selective_logic
            entries.append(
                replace(
                    entry,
                    provenance=provenance,
                    title=field.title,
                    content=field.content,
                    keywords=tuple(field.keywords),
                    secondary_keywords=tuple(field.secondary_keywords),
                    enabled=field.enabled,
                    priority=field.priority,
                    order=field.order,
                    activation_metadata=meta,
                )
            )
        root = replace(
            root,
            provenance=provenance,
            name=fields.name,
            description=fields.description,
            lore_entry_ids=tuple(x.content_id for x in entries),
        )
        copied = entries
    if research:
        extensions["dreamtalk.research"] = research
    elif isinstance(extensions.get("dreamtalk.research"), dict):
        extensions["dreamtalk.research"]["user_edited"] = True
    if previous:
        extensions["dreamtalk.edit"] = {
            "previous_import_id": str(previous.import_id),
            "original_provenance": json_value(
                next(x for x in old if isinstance(x, type(root))).provenance
            ),
        }
    root = replace(root, extensions=extensions)
    contents = (root, *copied)
    asset_ids = {a.asset_id for x in contents for a in getattr(x, "assets", ())}
    raw_ids = {x.provenance.raw_import_id for x in contents if x.provenance.raw_import_id}
    assets, raws = [], []
    for identity in asset_ids:
        asset = await repository.load_asset(identity)
        if asset is None:
            raise ContentImportError("editor_asset_missing")
        assets.append(asset)
    for identity in raw_ids:
        envelope = await repository.load_raw_import(identity)
        if envelope is None:
            raise ContentImportError("editor_source_missing")
        raws.append(envelope)
    return ContentDraft(contents, tuple(assets), tuple(raws))
