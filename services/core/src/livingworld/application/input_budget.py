"""Local reference budgets, measured after JSON escaping; authored data stays intact."""

import json
from copy import deepcopy

PERSONA_FIELDS = ("personality", "description", "background")


def encode_input(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def json_size(value: object) -> int:
    return len(encode_input(value).encode("utf-8"))


def bounded_text(value: str, json_bytes: int) -> str:
    if json_size(value) <= json_bytes:
        return value
    low, high = 0, len(value)
    while low < high:
        middle = (low + high + 1) // 2
        if json_size(value[:middle]) <= json_bytes:
            low = middle
        else:
            high = middle - 1
    return value[:low]


def bounded_persona(persona: dict[str, str], byte_limit: int) -> dict[str, str]:
    result = {field: "" for field in PERSONA_FIELDS}
    if json_size(persona) <= byte_limit:
        return dict(persona)
    available = max(0, byte_limit - json_size(result))
    for field, weight in zip(PERSONA_FIELDS, (2, 2, 1), strict=True):
        result[field] = bounded_text(persona[field], 2 + available * weight // 5)
    for field in PERSONA_FIELDS:
        spare = max(0, byte_limit - json_size(result))
        result[field] = bounded_text(persona[field], json_size(result[field]) + spare)
    return result


def planning_references(snapshot: dict, limit: int = 64 * 1024) -> dict:
    """Keep every identity, route and source; optional prose uses remaining space."""
    result = deepcopy(snapshot)
    if "name" in result:
        result["name"] = bounded_text(result["name"], 1024)
    characters = result.get("characters", [])
    share = min(8192, 32 * 1024 // max(1, len(characters)))
    for character in characters:
        original = character.get("persona", {})
        if original:
            character["persona"] = bounded_persona(original, share)
            character["persona_truncated"] = (
                character.get("persona_truncated", False) or character["persona"] != original
            )
        for key in ("name", "current_location_path"):
            if key in character:
                character[key] = bounded_text(character[key], 1024)
    for location in result.get("locations", []):
        for key in ("name", "path"):
            if key in location:
                location[key] = bounded_text(location[key], 1024)
    # The shared invitation's location must still match the actual source during
    # delivery; preserve that field verbatim instead of changing its semantics.
    background = result.pop("common_world_background", [])
    result["common_world_background"] = []
    if json_size(result) > limit:
        raise ValueError("planning_identity_capacity")
    for item in background:
        result["common_world_background"].append(item)
        if json_size(result) > limit:
            result["common_world_background"].pop()
    return result
