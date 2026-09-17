"""Bounded strict JSON input shared by independent external content adapters."""

import json

from livingworld.application.imports import ContentImportError
from livingworld.domain.content.serialization import stable_json
from livingworld.domain.errors import DomainInvariantError


def read_json_object(
    payload: bytes, *, max_bytes: int, max_depth: int, prefix: str, root_path: str
) -> dict:
    if len(payload) > max_bytes:
        raise ContentImportError(f"{prefix}_json_size_limit")

    def unique(pairs: list[tuple[str, object]]) -> dict:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ContentImportError(f"duplicate_{prefix}_json_key")
            result[key] = value
        return result

    try:
        text = payload.decode("utf-8")
        depth = 0
        quoted = escaped = False
        for char in text:
            if quoted:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    quoted = False
            elif char == '"':
                quoted = True
            elif char in "[{":
                depth += 1
                if depth > max_depth:
                    raise ContentImportError(f"{prefix}_json_depth_limit")
            elif char in "]}":
                depth -= 1
        document = json.loads(text, object_pairs_hook=unique)
        stable_json(document)  # Reject nonfinite numbers and escaped lone surrogates.
    except ContentImportError:
        raise
    except (ValueError, UnicodeError, RecursionError, DomainInvariantError):
        raise ContentImportError(f"invalid_{prefix}_json") from None
    if type(document) is not dict:
        raise ContentImportError(f"invalid_{prefix}_structure", root_path)
    return document
