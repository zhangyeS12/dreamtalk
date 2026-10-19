"""Public-spec CCv2/CCv3 adapter, implemented independently of SillyTavern."""

from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
from uuid import uuid4

from livingworld.application.content import ContentDraft, RawImportEnvelope
from livingworld.application.imports import (
    IMPORT_METADATA_KEY,
    ContentImportError,
    ImportDraft,
    ImportWarning,
)
from livingworld.domain.content.identifiers import (
    CharacterDefinitionId,
    ContentAssetId,
    RawImportId,
)
from livingworld.domain.content.models import (
    AssetReference,
    CharacterDefinition,
    ContentAsset,
    ContentProvenance,
    ContentSourceKind,
)
from livingworld.infrastructure.imports.card_compatibility import normalize_card
from livingworld.infrastructure.imports.card_png import select_card
from livingworld.infrastructure.imports.card_schema import (
    _TEXTS as _TEXTS,
)
from livingworld.infrastructure.imports.card_schema import (
    _V2_FIELDS as _V2_FIELDS,
)
from livingworld.infrastructure.imports.card_schema import (
    _V3_FIELDS as _V3_FIELDS,
)
from livingworld.infrastructure.imports.card_schema import (
    CARD_METADATA_KEY as CARD_METADATA_KEY,
)
from livingworld.infrastructure.imports.card_schema import (
    V2_SPEC as V2_SPEC,
)
from livingworld.infrastructure.imports.card_schema import (
    V2_VERSION as V2_VERSION,
)
from livingworld.infrastructure.imports.card_schema import (
    V3_SPEC as V3_SPEC,
)
from livingworld.infrastructure.imports.card_schema import (
    V3_VERSION as V3_VERSION,
)
from livingworld.infrastructure.imports.card_schema import (
    _object as _object,
)
from livingworld.infrastructure.imports.card_schema import (
    _strings as _strings,
)
from livingworld.infrastructure.imports.card_schema import (
    _validate as _validate,
)
from livingworld.infrastructure.imports.charx import read_charx
from livingworld.infrastructure.imports.json_input import read_json_object
from livingworld.infrastructure.imports.png import PNG_SIGNATURE, read_png


@dataclass(frozen=True, slots=True)
class CharacterCardLimits:
    """Local parser resource policy, configurable without changing content semantics."""

    max_input_bytes: int = 32 * 1024 * 1024
    max_json_bytes: int = 32 * 1024 * 1024
    max_json_depth: int = 64
    max_png_chunks: int = 10000

    def __post_init__(self) -> None:
        if any(type(value) is not int or value <= 0 for value in asdict(self).values()):
            raise ValueError("Character card parser limits must be positive integers")


def _json(payload: bytes, limits: CharacterCardLimits) -> dict:
    return read_json_object(
        payload,
        max_bytes=limits.max_json_bytes,
        max_depth=limits.max_json_depth,
        prefix="character_card",
        root_path="card",
        allow_bom=True,
    )


class CharacterCardImporter:
    def __init__(self, limits: CharacterCardLimits | None = None) -> None:
        self.limits = limits if limits is not None else CharacterCardLimits()

    def parse(
        self, payload: bytes, *, imported_at: datetime, original_name: str | None = None
    ) -> ImportDraft:
        if type(payload) is not bytes:
            raise ContentImportError("character_card_requires_bytes")
        if len(payload) > self.limits.max_input_bytes:
            raise ContentImportError("character_card_input_size_limit")
        warnings: list[ImportWarning] = []
        input_compatibility: dict = {}
        container = "json"
        selected = None
        chunk_counts = {}
        embedded_assets = ()
        if payload.startswith(PNG_SIGNATURE):
            metadata = read_png(payload, max_chunks=self.limits.max_png_chunks)
            container = metadata.container
            embedded_assets = metadata.embedded_assets
            document, input_compatibility, warnings, selected, chunk_counts = select_card(
                metadata.card_chunks,
                max_bytes=self.limits.max_json_bytes,
                max_depth=self.limits.max_json_depth,
            )
        elif payload.startswith(b"\x89PNG"):
            raise ContentImportError("invalid_png_signature")
        elif payload.startswith(b"PK\x03\x04"):
            container = "charx"
            document = _json(
                read_charx(
                    payload,
                    max_json_bytes=self.limits.max_json_bytes,
                    max_entries=self.limits.max_png_chunks,
                ),
                self.limits,
            )
        else:
            document = _json(payload, self.limits)
        if container not in ("png", "apng"):
            document, input_compatibility = normalize_card(document, warnings)
        if container == "charx":
            warnings.append(
                ImportWarning(
                    "character_card_charx_assets_reference_only",
                    "CHARX attachments retained in source archive; not extracted.",
                )
            )
        spec, version, data = _validate(document, [] if container in ("png", "apng") else warnings)
        unknown_top = {
            key: value
            for key, value in document.items()
            if key not in ("spec", "spec_version", "data")
        }
        unknown_data = {
            key: value
            for key, value in data.items()
            if key not in (_V3_FIELDS if spec == V3_SPEC else _V2_FIELDS)
        }
        if unknown_top or unknown_data:
            warnings.append(
                ImportWarning(
                    "character_card_unknown_fields",
                    "Unknown fields preserved without interpretation.",
                )
            )
        if data["extensions"]:
            warnings.append(
                ImportWarning(
                    "character_card_opaque_extensions",
                    "External extensions preserved as inert compatibility data.",
                    "data.extensions",
                )
            )
        if embedded_assets:
            warnings.append(
                ImportWarning(
                    "character_card_embedded_assets_deferred",
                    "Legacy embedded asset chunks retained only in raw container; "
                    "extraction deferred.",
                )
            )
        tags = tuple(tag for tag in data["tags"] if tag.strip())
        if len(tags) != len(data["tags"]):
            warnings.append(
                ImportWarning(
                    "character_card_blank_tags_omitted_from_canonical",
                    "Blank tags omitted only from canonical tags; "
                    "complete original tags remain in source compatibility data.",
                    "data.tags",
                )
            )
        raw_id = RawImportId(uuid4())
        provenance = ContentProvenance(
            source_kind=ContentSourceKind.IMPORT,
            source_format=spec,
            source_format_version=version,
            original_name=original_name,
            imported_at=imported_at,
            content_hash=sha256(payload).hexdigest(),
            raw_import_id=raw_id,
        )
        assets = []
        if spec == V3_SPEC:
            descriptors = data.get(
                "assets", [{"type": "icon", "uri": "ccdefault:", "name": "main", "ext": "png"}]
            )
            for index, descriptor in enumerate(descriptors):
                source_indices = input_compatibility.get("original_fields", {}).get(
                    "asset_source_indices", []
                )
                source_index = source_indices[index] if index < len(source_indices) else index
                pointer = (
                    f"/data/assets/{source_index}" if "assets" in data else "spec-default-assets/0"
                )
                kind, uri = descriptor["type"], descriptor["uri"]
                if kind not in ("icon", "background", "user_icon", "emotion"):
                    warnings.append(
                        ImportWarning(
                            "character_card_asset_type_deferred",
                            "Asset type retained without runtime behavior.",
                            pointer,
                        )
                    )
                if (
                    not uri.startswith(("https://", "http://", "data:", "embeded://", "__asset:"))
                    and uri != "ccdefault:"
                ):
                    warnings.append(
                        ImportWarning(
                            "character_card_asset_uri_deferred",
                            "Unknown URI retained as reference only; never accessed.",
                            pointer,
                        )
                    )
                container_image = (
                    uri == "ccdefault:" and kind == "icon" and container in ("png", "apng")
                )
                reference = f"raw-import:{raw_id.value.hex}#" + (
                    "container-image" if container_image else pointer
                )
                safe_descriptor = dict(descriptor)
                if uri.startswith("data:"):
                    safe_descriptor["uri"] = {"raw_pointer": pointer + "/uri"}
                assets.append(
                    ContentAsset(
                        asset_id=ContentAssetId(uuid4()),
                        media_type="image/png" if container_image else "application/octet-stream",
                        resource_reference=reference,
                        extensions={
                            "character_card_descriptor": safe_descriptor,
                            "raw_import_id": raw_id.value.hex,
                            "materialized": False,
                        },
                    )
                )
            if descriptors:
                warnings.append(
                    ImportWarning(
                        "character_card_assets_reference_only",
                        "Asset descriptors retained; "
                        "fetching, decoding and materialization are deferred.",
                        "data.assets",
                    )
                )
        compatibility: dict = {
            "input_compatibility": {
                key: value
                for key, value in input_compatibility.items()
                if key not in ("source_book", "source_assets")
            },
            **(
                {"character_book": input_compatibility["source_book"]}
                if "source_book" in input_compatibility
                else {}
            ),
            "original_tags": data["tags"],
            "creator": data["creator"],
            "character_version": data["character_version"],
            "external_extensions": data["extensions"],
            "unknown_top_level": unknown_top,
            "unknown_data": unknown_data,
            **{
                field: data[field]
                for field in (
                    "character_book",
                    "nickname",
                    "creator_notes_multilingual",
                    "source",
                    "group_only_greetings",
                    "creation_date",
                    "modification_date",
                )
                if field in data
            },
        }
        native = data["extensions"].get("dreamtalk.export", {})
        extra = {}
        if (
            isinstance(native, dict)
            and type(native.get("version")) is int
            and native["version"] == 1
        ):
            for field in ("background", "speech_guidance", "aliases", "example_dialogue"):
                if field not in native:
                    continue
                value = native[field]
                valid = (
                    type(value) is str
                    if field in ("background", "speech_guidance")
                    else (
                        type(value) is list
                        and all(type(item) is str and item.strip() for item in value)
                    )
                )
                if not valid:
                    warnings.append(
                        ImportWarning(
                            "character_card_optional_field_preserved",
                            "Invalid native extension retained without activation.",
                            f"data.extensions.dreamtalk.export.{field}",
                        )
                    )
                    continue
                if field == "example_dialogue" and "\n\n".join(value) != data["mes_example"]:
                    continue
                extra[field] = tuple(value) if type(value) is list else value
        import_metadata: dict = {
            "container": container,
            "selected_chunk": selected,
            "card_chunk_counts": chunk_counts,
            "embedded_asset_chunks": list(embedded_assets),
            "warnings": [asdict(warning) for warning in warnings],
        }
        character = CharacterDefinition(
            content_id=CharacterDefinitionId(uuid4()),
            display_name=data["name"],
            description=data["description"],
            personality=data["personality"],
            scenario=data["scenario"],
            creator_notes=data["creator_notes"],
            example_dialogue=extra.pop(
                "example_dialogue", (data["mes_example"],) if data["mes_example"].strip() else ()
            ),
            **extra,
            tags=tags,
            provenance=provenance,
            authored_instructions={
                "character_card": {
                    field: data[field]
                    for field in (
                        "system_prompt",
                        "post_history_instructions",
                        "first_mes",
                        "alternate_greetings",
                        "mes_example",
                    )
                }
            },
            assets=tuple(
                AssetReference(
                    asset_id=asset.asset_id,
                    role=asset.extensions["character_card_descriptor"]["type"]
                    if asset.extensions["character_card_descriptor"]["type"].strip()
                    else "character-card-asset",
                )
                for asset in assets
            ),
            extensions={CARD_METADATA_KEY: compatibility, IMPORT_METADATA_KEY: import_metadata},
        )

        raw = RawImportEnvelope(
            import_id=raw_id,
            provenance=provenance,
            original_payload=payload,
            unknown_extensions={
                "top_level": unknown_top,
                "data": unknown_data,
                "extensions": data["extensions"],
                "original_tags": data["tags"],
                **(
                    {"assets": input_compatibility.get("source_assets", data["assets"])}
                    if "assets" in data and spec == V3_SPEC
                    else {}
                ),
            },
        )
        return ImportDraft(
            ContentDraft(contents=(character,), assets=tuple(assets), raw_imports=(raw,))
        )
