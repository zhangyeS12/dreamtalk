"""Current canonical content to public JSON formats; source bytes are never the output."""

from collections.abc import Mapping
from hashlib import sha256
from math import isfinite

from livingworld.application.exports import (
    CharacterBookVersion,
    ContentExportError,
    ExportDecisionRequiredError,
    ExportRequest,
    ExportResult,
    ExportTarget,
    ExportWarning,
)
from livingworld.application.imports import (
    IMPORT_METADATA_KEY,
    LOREBOOK_METADATA_KEY,
    ContentImportError,
)
from livingworld.domain.content.identifiers import ContentId
from livingworld.domain.content.models import (
    CanonicalContent,
    CharacterDefinition,
    LoreCollection,
    LoreEntry,
)
from livingworld.domain.content.serialization import json_value, stable_json
from livingworld.domain.errors import DomainInvariantError
from livingworld.infrastructure.imports.character_cards import (
    _V2_FIELDS,
    _V3_FIELDS,
    CARD_METADATA_KEY,
    V2_SPEC,
    V2_VERSION,
    V3_SPEC,
    V3_VERSION,
    _validate,
)
from livingworld.infrastructure.imports.lorebooks import (
    _BOOK_FIELDS,
    _CARD_ENTRY_FIELDS,
    _SELECTIVE_LOGIC,
    _ST_BOOLEANS,
    _ST_ENTRY_FIELDS,
    _ST_NULLABLE_BOOLEANS,
    _ST_NULLABLE_COUNTS,
    _ST_POSITIONS,
    LorebookLimits,
    _book,
    _validate_entry,
)

_ST_LOGIC_CODES = {symbol: number for number, symbol in _SELECTIVE_LOGIC.items()}
_ST_POSITION_CODES = {symbol: number for number, symbol in _ST_POSITIONS.items()}
_V3_ONLY = _V3_FIELDS - _V2_FIELDS
_ST_ACTIVATION = (
    _ST_BOOLEANS
    | _ST_NULLABLE_BOOLEANS
    | _ST_NULLABLE_COUNTS
    | {
        "probability",
        "groupWeight",
        "delayUntilRecursion",
        "triggers",
        "characterFilter",
        "automationId",
    }
) - {"disable"}
_BOOK_SETTINGS = {"scan_depth", "token_budget", "recursive_scanning"}
_WARNING_MESSAGES = {
    "v3_use_regex_supplied_by_export_policy": (
        "Unspecified use_regex supplied by explicit caller export policy; content unchanged."
    ),
    "lore_title_not_representable_in_st_world_info": (
        "ST comment uses canonical comment; independent title cannot be represented."
    ),
    "source_uid_reassigned": "Source UID replaced with a deterministic export-local UID.",
    "multiple_lore_collections_require_selection": (
        "Collections were not merged; explicitly select one collection to embed."
    ),
    "export_asset_reference_not_packaged": "JSON carries the descriptor, not its referenced files.",
    "source_unsupported_semantic_preserved": (
        "Unsupported source enum preserved in the same format without interpretation."
    ),
}


def _object(value: object, path: str) -> dict:
    if not isinstance(value, Mapping):
        raise ContentExportError("invalid_export_metadata", path)
    return json_value(value)


def _warning(warnings: list[ExportWarning], code: str, path: str) -> None:
    warnings.append(
        ExportWarning(
            code,
            _WARNING_MESSAGES.get(
                code, "Target conversion omits this semantic; content remains preserved internally."
            ),
            path,
        )
    )


def _unknown(
    metadata: dict, *, same: bool, reserved: set[str], path: str, warnings: list[ExportWarning]
) -> dict:
    result = _object(metadata, path)
    if not same:
        if result:
            _warning(warnings, "target_format_does_not_preserve_source_extension", path)
        return {}
    # Only this schema boundary is merged; never recursively merge source dictionaries.
    return {key: result[key] for key in sorted(result) if key not in reserved}


def _losses(metadata: dict, understood: set[str], path: str, warnings: list[ExportWarning]) -> None:
    for key in sorted(metadata.keys() - understood):
        _warning(warnings, "target_format_does_not_represent_semantic", f"{path}.{key}")


def _uid(value: object) -> int | None:
    if type(value) is int:
        return value if 0 <= value <= 2**53 - 1 else None
    if type(value) is float and isfinite(value) and value.is_integer():
        return int(value) if 0 <= value <= 2**53 - 1 else None
    return None


def _uids(
    entries: list[LoreEntry], *, native: bool, same: bool, warnings: list[ExportWarning]
) -> list[int]:
    candidates, present = [], []
    for entry in entries:
        metadata = _object(entry.extensions.get(LOREBOOK_METADATA_KEY, {}), "entry.compatibility")
        source = _object(metadata.get("source_entry", {}), "entry.source_entry")
        compatible = same and (
            entry.provenance.source_format == "sillytavern_world_info"
            if native
            else entry.provenance.source_format in (V2_SPEC, V3_SPEC)
        )
        key = "uid" if native else "id"
        present.append(compatible and key in source)
        candidates.append(_uid(source.get(key)) if compatible else None)
    reserved = {value for value in candidates if value is not None}
    used, result, next_uid = set(), [], 0
    for index, candidate in enumerate(candidates):
        if candidate is not None and candidate not in used:
            assigned = candidate
        else:
            while next_uid in reserved or next_uid in used:
                next_uid += 1
            assigned = next_uid
            next_uid += 1
            if present[index]:
                _warning(
                    warnings,
                    "source_uid_reassigned",
                    f"book.entries[{index}].{'uid' if native else 'id'}",
                )
        used.add(assigned)
        result.append(assigned)
    return result


class JsonContentExporter:
    def serialize(self, request: ExportRequest) -> ExportResult:
        roots = {root.content_id: root for root in request.draft.contents}
        root = roots.get(request.content_id)
        warnings: list[ExportWarning] = []
        if request.target_format in (
            ExportTarget.CHARACTER_CARD_V2,
            ExportTarget.CHARACTER_CARD_V3,
        ):
            if not isinstance(root, CharacterDefinition):
                raise ContentExportError("export_target_content_mismatch")
            document = self._character(root, request, roots, warnings)
        else:
            if not isinstance(root, LoreCollection):
                raise ContentExportError("export_target_content_mismatch")
            if request.embedded_collection_id is not None:
                raise ContentExportError("unexpected_lore_selection")
            native = request.target_format is ExportTarget.SILLYTAVERN_WORLD_INFO
            document = self._lore(
                root,
                request,
                roots,
                warnings,
                native=native,
                v3=request.character_book_version is CharacterBookVersion.V3,
            )
        try:
            payload = stable_json(document).encode("utf-8")
        except DomainInvariantError:
            raise ContentExportError("invalid_export_json") from None
        ordered = tuple(
            sorted(set(warnings), key=lambda item: (item.path, item.code, item.message))
        )
        return ExportResult(
            request.target_format,
            payload,
            "application/json",
            ".json",
            ordered,
            sha256(payload).hexdigest(),
        )

    def _character(
        self,
        character: CharacterDefinition,
        request: ExportRequest,
        roots: dict[ContentId, CanonicalContent],
        warnings: list[ExportWarning],
    ) -> dict:
        v3 = request.target_format is ExportTarget.CHARACTER_CARD_V3
        spec, version = (V3_SPEC, V3_VERSION) if v3 else (V2_SPEC, V2_VERSION)
        same = character.provenance.source_format == spec
        if same and character.provenance.source_format_version not in (None, version):
            _warning(warnings, "source_schema_version_not_preserved", "spec_version")
        compatibility = _object(
            character.extensions.get(CARD_METADATA_KEY, {}), "character.compatibility"
        )
        _losses(
            _object(character.extensions, "character.extensions"),
            {CARD_METADATA_KEY, IMPORT_METADATA_KEY},
            "character.extensions",
            warnings,
        )
        instructions = _object(
            character.authored_instructions.get("character_card", {}),
            "character.authored_instructions.character_card",
        )
        document = _unknown(
            compatibility.get("unknown_top_level", {}),
            same=same,
            reserved={"spec", "spec_version", "data"},
            path="card",
            warnings=warnings,
        )
        data = _unknown(
            compatibility.get("unknown_data", {}),
            same=same,
            reserved=_V3_FIELDS,
            path="data",
            warnings=warnings,
        )
        if len(character.example_dialogue) > 1:
            # No delimiter/flattening semantics exist in the canonical model.
            raise ExportDecisionRequiredError(
                "example_dialogue_serialization_required", "data.mes_example"
            )
        data.update(
            name=character.display_name,
            description=character.description,
            personality=character.personality,
            scenario=character.scenario,
            creator_notes=character.creator_notes,
            mes_example=character.example_dialogue[0] if character.example_dialogue else "",
            tags=list(character.tags),
            creator=compatibility.get("creator", ""),
            character_version=compatibility.get("character_version", ""),
            first_mes=instructions.get("first_mes", ""),
            system_prompt=instructions.get("system_prompt", ""),
            post_history_instructions=instructions.get("post_history_instructions", ""),
            alternate_greetings=instructions.get("alternate_greetings", []),
            extensions=_unknown(
                compatibility.get("external_extensions", {}),
                same=same,
                reserved=set(),
                path="data.extensions",
                warnings=warnings,
            ),
        )
        for field in ("aliases", "background", "speech_guidance", "lore_entry_ids"):
            if getattr(character, field):
                _warning(
                    warnings, "target_format_does_not_represent_semantic", f"character.{field}"
                )
        _losses(
            _object(character.authored_instructions, "character.authored_instructions"),
            {"character_card"},
            "character.authored_instructions",
            warnings,
        )
        if v3:
            data["group_only_greetings"] = compatibility.get("group_only_greetings", [])
            for field in sorted(_V3_ONLY - {"assets", "group_only_greetings"}):
                if field in compatibility:
                    data[field] = compatibility[field]
            data["assets"] = self._assets(character, request, same, warnings)
        else:
            for field in sorted(_V3_ONLY - {"assets"}):
                if field in compatibility:
                    _warning(warnings, "v3_field_not_representable_in_v2", f"data.{field}")
            if character.assets:
                _warning(warnings, "v3_field_not_representable_in_v2", "data.assets")
        linked = character.lore_collection_ids
        selected = request.embedded_collection_id
        if selected is not None and selected not in linked:
            raise ContentExportError("invalid_lore_selection")
        if selected is None and len(linked) == 1:
            selected = linked[0]
        elif selected is None and len(linked) > 1:
            _warning(warnings, "multiple_lore_collections_require_selection", "data.character_book")
        if selected is not None:
            data["character_book"] = self._lore(
                roots[selected], request, roots, warnings, native=False, v3=v3
            )
        elif "character_book" in compatibility and not linked:
            _warning(
                warnings, "unnormalized_source_character_book_not_exported", "data.character_book"
            )
        document.update(spec=spec, spec_version=version, data=data)
        try:
            _validate(document, [])
        except ContentImportError as error:
            raise ContentExportError("invalid_character_card_export", error.path) from None
        return document

    def _assets(
        self,
        character: CharacterDefinition,
        request: ExportRequest,
        same: bool,
        warnings: list[ExportWarning],
    ) -> list[dict]:
        assets = {asset.asset_id: asset for asset in request.draft.assets}
        imports = {raw.import_id.value.hex: raw for raw in request.draft.raw_imports}
        result = []
        for index, reference in enumerate(character.assets):
            asset = assets[reference.asset_id]
            path = f"data.assets[{index}]"
            if "character_card_descriptor" not in asset.extensions:
                _warning(warnings, "target_format_does_not_represent_asset", path)
                continue
            descriptor = _object(asset.extensions["character_card_descriptor"], path)
            known = {key: descriptor.get(key) for key in ("type", "uri", "name", "ext")}
            uri = known["uri"]
            if isinstance(uri, dict):
                pointer = uri.get("raw_pointer")
                raw = imports.get(asset.extensions.get("raw_import_id"))
                segments = pointer.split("/") if type(pointer) is str else []
                if (
                    raw is None
                    or len(segments) != 5
                    or segments[:3] != ["", "data", "assets"]
                    or segments[4] != "uri"
                    or not segments[3].isdigit()
                ):
                    raise ContentExportError("export_asset_source_required", path + ".uri")
                descriptors = json_value(raw.unknown_extensions.get("assets", []))
                source_index = int(segments[3])
                if type(descriptors) is not list or source_index >= len(descriptors):
                    raise ContentExportError("export_asset_source_required", path + ".uri")
                known["uri"] = _object(descriptors[source_index], path + ".source_descriptor").get(
                    "uri"
                )
            exported = _unknown(
                {key: value for key, value in descriptor.items() if key not in known},
                same=same,
                reserved=set(),
                path=path,
                warnings=warnings,
            )
            exported.update(known)
            uri = exported["uri"]
            if type(uri) is str and (
                uri.startswith(("embeded://", "__asset:"))
                or "#container-image" in asset.resource_reference
            ):
                _warning(warnings, "export_asset_reference_not_packaged", path + ".uri")
            result.append(exported)
        return result

    def _lore(
        self,
        collection: LoreCollection,
        request: ExportRequest,
        roots: dict[ContentId, CanonicalContent],
        warnings: list[ExportWarning],
        *,
        native: bool,
        v3: bool,
    ) -> dict:
        _losses(
            _object(collection.extensions, "book.extensions"),
            {LOREBOOK_METADATA_KEY, IMPORT_METADATA_KEY},
            "book.extensions",
            warnings,
        )
        metadata = _object(
            collection.extensions.get(LOREBOOK_METADATA_KEY, {}), "book.compatibility"
        )
        same = (
            metadata.get("origin") == "standalone_world_info"
            if native
            else metadata.get("origin") == "embedded_character_book"
            and collection.provenance.source_format == (V3_SPEC if v3 else V2_SPEC)
        )
        document = _unknown(
            metadata.get("unknown_fields", {}),
            same=same,
            reserved=_BOOK_FIELDS,
            path="book",
            warnings=warnings,
        )
        document.update(
            name=collection.name,
            description=collection.description,
            extensions=_unknown(
                metadata.get("external_extensions", {}),
                same=same,
                reserved=set(),
                path="book.extensions",
                warnings=warnings,
            ),
        )
        settings = _object(collection.activation_metadata, "book.activation_metadata")
        document.update({key: settings[key] for key in sorted(_BOOK_SETTINGS) if key in settings})
        _losses(settings, _BOOK_SETTINGS, "book.activation_metadata", warnings)
        entries = [roots[identity] for identity in collection.lore_entry_ids]
        if any(
            not isinstance(entry, LoreEntry) or entry.collection_id != collection.content_id
            for entry in entries
        ):
            raise ContentExportError("export_lore_ownership_mismatch")
        uids = _uids(entries, native=native, same=same, warnings=warnings)
        if native and request.preserve_native_fields:
            document["extensions"]["dreamtalk.export"] = {
                "version": 1,
                "member_order": [str(uid) for uid in uids],
            }
        if native and uids != sorted(uids, key=str) and not request.preserve_native_fields:
            _warning(warnings, "lore_member_order_not_preserved_by_st_object_map", "book.entries")
        exported = [
            self._entry(
                entry,
                uids[index],
                request,
                warnings,
                native=native,
                v3=v3,
                same=same
                and entry.provenance.source_format
                == ("sillytavern_world_info" if native else V3_SPEC if v3 else V2_SPEC),
                path=f"book.entries[{index}]",
            )
            for index, entry in enumerate(entries)
        ]
        document["entries"] = (
            {str(uid): entry for uid, entry in zip(uids, exported, strict=True)}
            if native
            else exported
        )
        try:
            for key, entry in _book(document, native=native, limits=LorebookLimits()):
                _validate_entry(entry, f"book.entries[{key}]", native=native, v3=v3)
        except ContentImportError as error:
            raise ContentExportError("invalid_lorebook_export", error.path) from None
        return document

    def _entry(
        self,
        entry: LoreEntry,
        uid: int,
        request: ExportRequest,
        warnings: list[ExportWarning],
        *,
        native: bool,
        v3: bool,
        same: bool,
        path: str,
    ) -> dict:
        _losses(
            _object(entry.extensions, path + ".extensions"),
            {LOREBOOK_METADATA_KEY, IMPORT_METADATA_KEY},
            path + ".extensions",
            warnings,
        )
        metadata = _object(entry.extensions.get(LOREBOOK_METADATA_KEY, {}), path + ".compatibility")
        result = _unknown(
            metadata.get("unknown_fields", {}),
            same=same,
            reserved=_ST_ENTRY_FIELDS
            if native
            else (_CARD_ENTRY_FIELDS if v3 else _CARD_ENTRY_FIELDS - {"use_regex"}),
            path=path,
            warnings=warnings,
        )
        result.update(
            content=entry.content,
            extensions=_unknown(
                metadata.get("external_extensions", {}),
                same=same,
                reserved=set(),
                path=path + ".extensions",
                warnings=warnings,
            ),
        )
        activation = _object(entry.activation_metadata, path + ".activation_metadata")
        insertion = _object(entry.insertion_metadata, path + ".insertion_metadata")
        if (
            "case_sensitive" in activation
            and "caseSensitive" in activation
            and activation["case_sensitive"] != activation["caseSensitive"]
        ):
            raise ContentExportError("conflicting_activation_aliases", path + ".case_sensitive")
        if native:
            result.update(
                uid=uid,
                key=list(entry.keywords),
                keysecondary=list(entry.secondary_keywords),
                comment=(entry.comment or entry.title)
                if request.preserve_native_fields
                else entry.comment,
                disable=not entry.enabled,
                order=entry.order,
            )
            if request.preserve_native_fields:
                result["extensions"]["dreamtalk.export"] = {
                    "version": 1,
                    "title": entry.title,
                    "comment": entry.comment,
                    "priority": entry.priority,
                }
            if entry.title != entry.comment and not request.preserve_native_fields:
                _warning(warnings, "lore_title_not_representable_in_st_world_info", path + ".title")
            if entry.priority and not request.preserve_native_fields:
                _warning(warnings, "target_format_does_not_represent_semantic", path + ".priority")
            if entry.group is not None:
                result["group"] = entry.group
            result.update(
                {
                    key: activation[key]
                    for key in sorted(_ST_ACTIVATION - {"group"})
                    if key in activation
                }
            )
            if "case_sensitive" in activation:
                result["caseSensitive"] = activation["case_sensitive"]
            if "selective_logic" in activation:
                symbol = activation["selective_logic"]
                if type(symbol) is not str or symbol not in _ST_LOGIC_CODES:
                    raise ContentExportError("invalid_export_metadata", path + ".selective_logic")
                result["selectiveLogic"] = _ST_LOGIC_CODES[symbol]
            if "position" in insertion:
                symbol = insertion["position"]
                if type(symbol) is not str or symbol not in _ST_POSITION_CODES:
                    raise ContentExportError("invalid_export_metadata", path + ".position")
                result["position"] = _ST_POSITION_CODES[symbol]
            # Explicitly unsupported original enum values can survive this family.
            source = _object(metadata.get("source_entry", {}), path + ".source_entry")
            if same:
                for source_key, canonical_key, mapping, current in (
                    ("position", "position", _ST_POSITIONS, insertion),
                    ("selectiveLogic", "selective_logic", _SELECTIVE_LOGIC, activation),
                ):
                    value = source.get(source_key)
                    if (
                        canonical_key not in current
                        and type(value) in (int, float, str)
                        and value not in mapping
                    ):
                        result[source_key] = value
                        _warning(
                            warnings,
                            "source_unsupported_semantic_preserved",
                            path + "." + source_key,
                        )
            result.update(
                {key: insertion[key] for key in ("depth", "role", "outletName") if key in insertion}
            )
            _losses(
                activation,
                _ST_ACTIVATION | {"group", "case_sensitive", "selective_logic"},
                path + ".activation_metadata",
                warnings,
            )
            _losses(
                insertion,
                {"position", "depth", "role", "outletName"},
                path + ".insertion_metadata",
                warnings,
            )
        else:
            result.update(
                id=uid,
                keys=list(entry.keywords),
                secondary_keys=list(entry.secondary_keywords),
                name=entry.title,
                comment=entry.comment,
                enabled=entry.enabled,
                insertion_order=entry.order,
                priority=entry.priority,
            )
            supported = {"constant", "selective", "case_sensitive"}
            result.update({key: activation[key] for key in sorted(supported) if key in activation})
            if "caseSensitive" in activation and activation["caseSensitive"] is not None:
                result["case_sensitive"] = activation["caseSensitive"]
            elif "caseSensitive" in activation:
                _warning(
                    warnings, "target_format_does_not_represent_semantic", path + ".caseSensitive"
                )
            if v3:
                if "use_regex" in activation:
                    if type(activation["use_regex"]) is not bool:
                        raise ContentExportError("invalid_export_metadata", path + ".use_regex")
                    result["use_regex"] = activation["use_regex"]
                else:
                    policy = request.v3_book_options.use_regex
                    if policy is None:
                        raise ExportDecisionRequiredError(
                            "v3_use_regex_decision_required", path + ".use_regex"
                        )
                    result["use_regex"] = policy
                    _warning(
                        warnings, "v3_use_regex_supplied_by_export_policy", path + ".use_regex"
                    )
                supported.add("use_regex")
            if "position" in insertion:
                if insertion["position"] in ("before_char", "after_char"):
                    result["position"] = insertion["position"]
                else:
                    _warning(
                        warnings, "target_format_does_not_represent_semantic", path + ".position"
                    )
            if entry.group is not None:
                _warning(warnings, "target_format_does_not_represent_semantic", path + ".group")
            _losses(
                activation, supported | {"caseSensitive"}, path + ".activation_metadata", warnings
            )
            _losses(insertion, {"position"}, path + ".insertion_metadata", warnings)
        for field in ("scope", "category"):
            if getattr(entry, field) is not None:
                _warning(warnings, "target_format_does_not_represent_semantic", path + "." + field)
        return result
