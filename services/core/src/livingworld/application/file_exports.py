"""Read-only file exports; no model calls or runtime state mutation."""

import re
from dataclasses import dataclass
from hashlib import sha256
from urllib.parse import quote


def export_filename(name: str, suffix: str) -> str:
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', "_", name).strip(" .")[:80] or "dreamtalk"
    if stem.split(".")[0].upper() in {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *[f"COM{i}" for i in range(1, 10)],
        *[f"LPT{i}" for i in range(1, 10)],
    }:
        stem = "_" + stem
    return stem + suffix


def attachment_headers(filename: str) -> dict[str, str]:
    return {
        "Content-Disposition": 'attachment; filename="dreamtalk-export"; '
        f"filename*=UTF-8''{quote(filename)}",
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    }


@dataclass(frozen=True, slots=True)
class ExportedFile:
    filename: str
    payload: bytes
    media_type: str = "application/json"
    warnings: tuple = ()

    @property
    def digest(self) -> str:
        return sha256(self.payload).hexdigest()
