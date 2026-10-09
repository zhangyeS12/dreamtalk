"""Export exactly the reviewed current card/book snapshot in its owning world."""

import json
from dataclasses import replace
from uuid import UUID

from livingworld.application.content import ContentConflictError, ContentDraft
from livingworld.application.errors import EntityNotFoundError
from livingworld.application.exports import (
    ExportRequest,
    ExportService,
    ExportTarget,
    ExportWarning,
    V3CharacterBookOptions,
)
from livingworld.application.file_exports import ExportedFile, export_filename
from livingworld.domain.content.identifiers import RawImportId
from livingworld.domain.content.models import CharacterDefinition, LoreCollection


class WorldContentExportService:
    def __init__(self, imports, repository, exporter):
        self._imports, self._repository = imports, repository
        self._exporter = ExportService(exporter)

    async def prepare(self, world, import_id, reviewed_hash, target, content_id, use_regex=False):
        item = await self._imports.find(import_id)
        if item is None or item.world_id != world:
            raise EntityNotFoundError("export_content_unavailable")
        if item.reviewed_hash != reviewed_hash or not await self._imports.is_current(import_id):
            raise ContentConflictError("export_content_changed")
        wanted = (
            CharacterDefinition
            if target
            in {
                ExportTarget.CHARACTER_CARD_V2,
                ExportTarget.CHARACTER_CARD_V3,
            }
            else LoreCollection
        )
        selected = next(
            (
                root
                for root in item.contents
                if isinstance(root, wanted) and root.content_id.value == content_id
            ),
            None,
        )
        if selected is None:
            raise EntityNotFoundError("export_content_unavailable")
        assets, raws = [], []
        for identity in {
            ref.asset_id for root in item.contents for ref in getattr(root, "assets", ())
        }:
            asset = await self._repository.load_asset(identity)
            if asset is None:
                raise EntityNotFoundError("export_asset_unavailable")
            assets.append(asset)
        raw_ids = {
            root.provenance.raw_import_id for root in item.contents if root.provenance.raw_import_id
        }
        raw_ids.update(
            RawImportId(UUID(hex=asset.extensions["raw_import_id"]))
            for asset in assets
            if "raw_import_id" in asset.extensions
        )
        for identity in raw_ids:
            raw = await self._repository.load_raw_import(identity)
            if raw is None:
                raise EntityNotFoundError("export_source_unavailable")
            raws.append(raw)
        # The public card field is a single string. The complete authored list and
        # extra native fields are preserved by the explicit dreamtalk extension.
        contents = tuple(
            replace(root, example_dialogue=("\n\n".join(root.example_dialogue),))
            if isinstance(root, CharacterDefinition) and len(root.example_dialogue) > 1
            else root
            for root in item.contents
        )
        draft = ContentDraft(contents=contents, assets=tuple(assets), raw_imports=tuple(raws))
        result = self._exporter.export(
            ExportRequest(
                draft=draft,
                content_id=selected.content_id,
                target_format=target,
                v3_book_options=V3CharacterBookOptions(use_regex=use_regex)
                if target is ExportTarget.CHARACTER_CARD_V3
                else V3CharacterBookOptions(),
                preserve_native_fields=True,
            )
        )
        payload, warnings = result.serialized_bytes, result.warnings
        if isinstance(selected, CharacterDefinition):
            document = json.loads(payload)
            document["data"]["extensions"]["dreamtalk.export"] = {
                "version": 1,
                "background": selected.background,
                "speech_guidance": selected.speech_guidance,
                "aliases": list(selected.aliases),
                "example_dialogue": list(selected.example_dialogue),
            }
            payload = json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
            warnings = tuple(
                w
                for w in warnings
                if w.path
                not in {
                    "character.background",
                    "character.speech_guidance",
                    "character.aliases",
                }
            )
            if (
                selected.background
                or selected.speech_guidance
                or selected.aliases
                or len(selected.example_dialogue) > 1
            ):
                warnings += (
                    ExportWarning(
                        "dreamtalk_fields_in_extension", "", "data.extensions.dreamtalk.export"
                    ),
                )
        return ExportedFile(
            export_filename(
                selected.display_name
                if isinstance(selected, CharacterDefinition)
                else selected.name,
                "-角色卡.json" if isinstance(selected, CharacterDefinition) else "-世界书.json",
            ),
            payload,
            result.content_type,
            warnings,
        )
