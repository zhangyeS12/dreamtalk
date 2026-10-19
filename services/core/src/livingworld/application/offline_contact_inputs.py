"""Bound one frozen offline input; never edit authored content or invoke a model."""

import json
from typing import NotRequired, TypedDict
from uuid import UUID

from livingworld.application.input_budget import (
    bounded_persona as bounded_persona,
)
from livingworld.application.input_budget import (
    bounded_text as bounded_text,
)
from livingworld.application.input_budget import (
    encode_input as encode_input,
)
from livingworld.application.input_budget import (
    json_size as _size,
)

MAX_CONTACTS = 16
MAX_CONTACT_SCAN = 64
MAX_INPUT_BYTES = 64 * 1024
PERSONA_POOL_BYTES = 32 * 1024
PERSONA_READ_BYTES = 8192
PREPARATION_ERRORS = frozenset(
    {
        "offline_input_capacity",
        "offline_snapshot_capacity",
        "offline_input_unavailable",
        "offline_character_mapping_invalid",
        "offline_background_capacity",
        "offline_background_invalid",
        "offline_candidates_unavailable",
    }
)


class ContactInput(TypedDict):
    character_id: str
    conversation_id: str
    name: str
    accepted_import_id: str
    persona: dict[str, str]
    persona_truncated: NotRequired[bool]


def capture_cursor(raw: str | None, *, advance: bool) -> UUID | None:
    """Old snapshots have no selection metadata and start at the first batch."""
    try:
        snapshot = json.loads(raw) if raw else {}
        selection = snapshot.get("input_selection", {})
        preparation = snapshot.get("input_preparation", {})
        # A completely unusable local cohort may yield to the next cohort on a
        # heartbeat; this prepares future input only, without a paid recovery.
        if (
            preparation.get("selected") == 0
            and preparation.get("excluded", 0)
            and preparation.get("batched") is True
        ):
            advance = True
        value = selection.get("next_after" if advance else "after")
        return UUID(value) if isinstance(value, str) else None
    except (ValueError, TypeError, AttributeError):
        return None


def pack_snapshot(
    metadata: dict[str, object],
    characters: list[ContactInput],
    background: list[dict[str, str]],
    intentions: list[dict[str, object]],
    preparation: dict[str, int | bool],
) -> str:
    """Roles get a shared local budget; optional context only uses remaining bytes."""
    if len(characters) > MAX_CONTACTS:
        raise ValueError("offline_snapshot_capacity")
    per_role = min(8192, PERSONA_POOL_BYTES // max(1, len(characters)))
    projected: list[ContactInput] = []
    clipped = 0
    for character in characters:
        persona = bounded_persona(character["persona"], per_role)
        limited = character.get("persona_truncated", False) or persona != character["persona"]
        name = bounded_text(character["name"], 512)
        limited = limited or name != character["name"]
        projected.append(
            {**character, "name": name, "persona": persona, "persona_truncated": limited}
        )
        clipped += int(limited)
    preparation["clipped"] = clipped
    snapshot: dict[str, object] = {
        **metadata,
        "characters": projected,
        "eligible": bool(projected),
        "common_world_background": [],
        "existing_intentions": [],
        "input_preparation": preparation,
    }
    for key, items in (
        ("common_world_background", background),
        ("existing_intentions", intentions),
    ):
        selected: list[object] = []
        snapshot[key] = selected
        for item in items:
            selected.append(item)
            if _size(snapshot) > MAX_INPUT_BYTES:
                selected.pop()
                preparation["context_limited"] = True
    text = encode_input(snapshot)
    if len(text.encode("utf-8")) > MAX_INPUT_BYTES:
        raise ValueError("offline_snapshot_capacity")
    return text
