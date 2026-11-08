"""Select bounded PNG card metadata; report any explicitly reviewed V2 fallback."""

import base64
import binascii

from livingworld.application.imports import ContentImportError, ImportWarning
from livingworld.infrastructure.imports.card_compatibility import normalize_card
from livingworld.infrastructure.imports.card_schema import V3_SPEC, _validate
from livingworld.infrastructure.imports.json_input import read_json_object


def select_card(
    chunks: tuple[tuple[str, bytes], ...], *, max_bytes: int, max_depth: int
) -> tuple[dict, dict, list[ImportWarning], str, dict[str, int]]:
    candidates: dict[str, tuple[dict, dict, list[ImportWarning]]] = {}
    failures: dict[str, ContentImportError] = {}
    counts: dict[str, int] = {}
    originals: dict[str, bytes] = {}
    for name, encoded in chunks:
        counts[name] = counts.get(name, 0) + 1
        if name in originals:
            if originals[name] != encoded:
                raise ContentImportError("ambiguous_character_card_chunks", name)
            continue
        originals[name] = encoded
        try:
            if len(encoded) > 4 * ((max_bytes + 2) // 3) + 4096:
                raise ContentImportError("character_card_json_size_limit", name)
            compact = b"".join(encoded.split())
            decoded = base64.b64decode(compact + b"=" * (-len(compact) % 4), validate=True)
            document = read_json_object(
                decoded,
                max_bytes=max_bytes,
                max_depth=max_depth,
                prefix="character_card",
                root_path=name,
                allow_bom=True,
            )
            warnings: list[ImportWarning] = []
            if name == "ccv3" and document.get("spec") != V3_SPEC:
                raise ContentImportError("invalid_ccv3_payload_identity", name)
            normalized, compatibility = normalize_card(document, warnings)
            _validate(normalized, warnings)
            if base64.b64encode(decoded) != encoded:
                warnings.append(
                    ImportWarning(
                        "character_card_base64_normalized", "Base64 framing normalized.", name
                    )
                )
            candidates[name] = (normalized, compatibility, warnings)
        except (ValueError, binascii.Error) as error:
            failures[name] = (
                error
                if isinstance(error, ContentImportError)
                else ContentImportError("invalid_character_card_base64", name)
            )
    selected = "ccv3" if "ccv3" in candidates else "chara"
    if selected not in candidates:
        if failures:
            raise failures.get("ccv3", next(iter(failures.values())))
        raise ContentImportError("missing_character_card_chunk")
    document, compatibility, warnings = candidates[selected]
    if "ccv3" in failures and selected == "chara":
        warnings.append(
            ImportWarning(
                "character_card_v2_fallback_review_required",
                "V3 unreadable; confirm use of this V2 preview explicitly.",
                "ccv3",
            )
        )
    elif failures:
        warnings.append(
            ImportWarning(
                "character_card_unused_chunk_unreadable",
                "Unused card metadata retained in original PNG.",
                "chara",
            )
        )
    if len(originals) == 2 and selected == "ccv3":
        warnings.append(
            ImportWarning(
                "character_card_chara_shadowed", "V3 selected; V2 retained in source.", "chara"
            )
        )
    if any(count > 1 for count in counts.values()):
        warnings.append(
            ImportWarning(
                "character_card_identical_chunks", "Identical duplicate metadata retained."
            )
        )
    return document, compatibility, warnings, selected, counts
