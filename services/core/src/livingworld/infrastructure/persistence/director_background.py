"""Read only exposed lore fields; never deserialize a whole book for Director."""

from uuid import UUID

from sqlalchemy import LargeBinary, case, cast, func, select, true, tuple_
from sqlalchemy.orm import aliased

from livingworld.application.director import DirectorError
from livingworld.application.imports import LOREBOOK_METADATA_KEY
from livingworld.application.lore_activation import (
    MAX_COMMON_LORE_BYTES,
    MAX_COMMON_LORE_ITEMS,
    BackgroundCollection,
    BackgroundEntry,
    BackgroundItem,
)
from livingworld.domain.content.identifiers import LoreEntryId
from livingworld.domain.content.serialization import parse_json
from livingworld.infrastructure.persistence.models import (
    WorldCommonLoreRecord as Exposure,
)
from livingworld.infrastructure.persistence.models import (
    WorldContentImportRecord as Imported,
)

MAX_PUBLIC_ENTRIES = 512
MAX_METADATA_BYTES = 16 * 1024


def _current_import_scope(world):
    successor = aliased(Imported)
    return (
        Imported.world_id == world.value,
        Imported.kind == "lorebook",
        ~select(successor.import_id)
        .where(
            successor.world_id == world.value,
            successor.replaces_import_id == Imported.import_id,
        )
        .exists(),
    )


def _public_scope(world):
    return (Exposure.world_id == world.value, *_current_import_scope(world))


def _safe_json(value, default):
    return case((func.json_valid(value), value), else_=default)


async def read_director_background(session, world):
    # The array contains JSON-string canonical envelopes. Restrict each exposed
    # entry in SQL before returning any payload to Python. Opaque source_book,
    # creator notes, instructions, comments and unrelated entries are not read.
    parts = func.json_each(_safe_json(Imported.snapshot_json, "[]")).table_valued("key", "value")
    part = _safe_json(parts.c.value, "{}")

    def get(name):
        return func.json_extract(part, f"$.data.{name}")

    collection_parts = (
        func.json_each(_safe_json(Imported.snapshot_json, "[]"))
        .table_valued("key", "value")
        .alias("director_background_collections")
    )
    collection = _safe_json(collection_parts.c.value, "{}")
    scan_depth = (
        select(func.json_extract(collection, "$.data.activation_metadata.scan_depth"))
        .select_from(collection_parts)
        .where(
            func.json_extract(collection, "$.kind") == "lore_collection",
            func.json_extract(collection, "$.data.content_id") == get("collection_id"),
        )
        .correlate(Imported, parts)
        .limit(1)
        .scalar_subquery()
    )
    unknown_logic = func.json_type(
        part, '$.data.extensions."livingworld.lorebook".source_entry.selectiveLogic'
    ).is_not(None)
    metadata = func.json_object(
        "keywords",
        get("keywords"),
        "secondary_keywords",
        get("secondary_keywords"),
        "priority",
        get("priority"),
        "order",
        get("order"),
        "group",
        get("group"),
        "activation_metadata",
        get("activation_metadata"),
        "scan_depth",
        scan_depth,
        "unknown_selective_logic",
        unknown_logic,
    )
    text_fits = (
        func.length(cast(get("title"), LargeBinary))
        + func.length(cast(get("content"), LargeBinary))
        <= MAX_COMMON_LORE_BYTES
    )
    # Traverse a book once, then use the exposure primary key as the per-entry
    # authorization filter. Joining exposure first would repeatedly expand the
    # same snapshot for every public entry in that book.
    authorized = (
        select(Exposure.entry_id)
        .where(
            Exposure.world_id == world.value,
            Exposure.import_id == Imported.import_id,
            Exposure.entry_id == get("content_id"),
        )
        .correlate(Imported, parts)
        .exists()
    )
    rows = (
        await session.execute(
            select(
                Imported.import_id,
                get("content_id"),
                case(
                    (func.length(cast(metadata, LargeBinary)) <= MAX_METADATA_BYTES, metadata),
                    else_=None,
                ),
                case((text_fits, get("title")), else_=None),
                case((text_fits, get("content")), else_=None),
            )
            .select_from(Imported)
            .join(parts, true())
            .where(
                *_current_import_scope(world),
                authorized,
                func.json_extract(part, "$.kind") == "lore_entry",
                func.json_type(part, "$.data.enabled") == "true",
            )
            .order_by(Imported.import_id, get("content_id"))
            .limit(MAX_PUBLIC_ENTRIES + 1)
        )
    ).all()
    if len(rows) > MAX_PUBLIC_ENTRIES or any(row[2] is None for row in rows):
        raise DirectorError("director_background_capacity")
    selected = []
    identities = set()
    for import_id, entry_hex, raw_metadata, title, content in rows:
        try:
            entry_id = UUID(hex=entry_hex)
            if entry_id.hex != entry_hex:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise DirectorError("director_background_invalid") from None
        identity = (import_id, entry_id)
        if identity in identities:
            raise DirectorError("director_background_invalid")
        identities.add(identity)
        if title is None or content is None:
            continue  # Too large for the existing shared background text budget.
        try:
            meta = parse_json(raw_metadata)
            if (
                not isinstance(title, str)
                or not isinstance(content, str)
                or not isinstance(meta, dict)
                or any(type(meta[key]) is not int for key in ("priority", "order"))
                or not isinstance(meta["activation_metadata"], dict)
                or meta["group"] is not None
                and not isinstance(meta["group"], str)
            ):
                raise ValueError()
            for key in ("keywords", "secondary_keywords"):
                if not isinstance(meta[key], list) or any(
                    not isinstance(value, str) for value in meta[key]
                ):
                    raise ValueError()
            # Preserve only presence of unknown source selectiveLogic, the sole
            # compatibility field used by activation. Never load opaque extensions.
            extensions = (
                {LOREBOOK_METADATA_KEY: {"source_entry": {"selectiveLogic": None}}}
                if meta["unknown_selective_logic"]
                else {}
            )
            selected.append(
                BackgroundItem(
                    import_id,
                    BackgroundEntry(
                        LoreEntryId(entry_id),
                        title,
                        content,
                        tuple(meta["keywords"]),
                        tuple(meta["secondary_keywords"]),
                        True,
                        meta["priority"],
                        meta["order"],
                        meta["group"],
                        meta["activation_metadata"],
                        extensions,
                    ),
                    BackgroundCollection(
                        {"scan_depth": meta["scan_depth"]} if meta["scan_depth"] is not None else {}
                    ),
                )
            )
        except (ValueError, TypeError, KeyError):
            raise DirectorError("director_background_invalid") from None
    return tuple(selected)


async def background_is_current(session, world, input_json):
    """Recheck selected references only; no payload reread and no provider retry."""
    try:
        snapshot = parse_json(input_json)
        items = snapshot.get("common_world_background", [])
        if not isinstance(items, list) or len(items) > MAX_COMMON_LORE_ITEMS:
            return False
        references = {(UUID(item["import_id"]), UUID(item["entry_id"])) for item in items}
        if len(references) != len(items):
            return False
    except (ValueError, TypeError, KeyError, AttributeError):
        return False
    if not references:
        return True  # Includes old plans created before public background support.
    count = await session.scalar(
        select(func.count())
        .select_from(Exposure)
        .join(Imported, Exposure.import_id == Imported.import_id)
        .where(
            *_public_scope(world),
            tuple_(Exposure.import_id, Exposure.entry_id).in_(references),
        )
    )
    return count == len(references)
