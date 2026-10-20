"""Editable subset of lore rules; unrelated imported metadata is retained."""

from pydantic import BaseModel, ConfigDict, Field


class LoreControls(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    probability: int = Field(default=100, ge=0, le=100)
    use_probability: bool = False
    sticky: int = Field(default=0, ge=0, le=1000000)
    cooldown: int = Field(default=0, ge=0, le=1000000)
    delay: int = Field(default=0, ge=0, le=1000000)
    recursion_level: int = Field(default=0, ge=0, le=32)
    exclude_recursion: bool = False
    prevent_recursion: bool = False
    scan_depth: int | None = Field(default=None, ge=0, le=32)
    insertion_depth: int | None = Field(default=None, ge=0, le=32)
    group: str = Field(default="", max_length=200)


KEYS = {
    "use_probability": "useProbability",
    "recursion_level": "delayUntilRecursion",
    "exclude_recursion": "excludeRecursion",
    "prevent_recursion": "preventRecursion",
    "scan_depth": "scanDepth",
}


def editable_controls(entry):
    meta = entry.activation_metadata
    defaults = LoreControls().model_dump()
    values = {}
    for name, default in defaults.items():
        if name in {"group", "insertion_depth"}:
            continue
        value = meta.get(KEYS.get(name, name), default)
        if name == "recursion_level" and type(value) is bool:
            value = int(value)
        try:
            # Validate individual values without normalizing opaque metadata on save.
            values[name] = LoreControls.model_validate({name: value}).model_dump()[name]
        except ValueError:
            values[name] = default
    values["group"] = (entry.group or meta.get("group") or "")[:200]
    insertion = entry.insertion_metadata
    depth = insertion.get("depth")
    values["insertion_depth"] = (
        depth
        if insertion.get("position") in (4, "at_depth", "in_chat")
        and type(depth) is int
        and 0 <= depth <= 32
        else None
    )
    return LoreControls.model_validate(values)


def apply_controls(entry, controls, meta, insertion):
    old = editable_controls(entry)
    for name, value in controls.model_dump().items():
        if getattr(old, name) == value or name in {"group", "insertion_depth"}:
            continue
        key = KEYS.get(name, name)
        if value is None:
            meta.pop(key, None)
        else:
            meta[key] = value
    group = entry.group
    if old.group != controls.group:
        group = controls.group.strip() or None
        meta.pop("group", None)
    if old.insertion_depth != controls.insertion_depth:
        if controls.insertion_depth is None:
            insertion.pop("depth", None)
            insertion.pop("position", None)
        else:
            insertion.update(position=4, depth=controls.insertion_depth)
    return group
