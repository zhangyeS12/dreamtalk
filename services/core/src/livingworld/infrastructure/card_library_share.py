"""CCv3 CHARX with a bounded, lossless authored-content package and local card art.

Independent implementation of CCv3 3.0 (MIT specification). No remote fetches,
filesystem extraction, plugins, world state or conversations enter this codec.
"""

import io
import json
import zipfile
import zlib
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid5

from pydantic import ValidationError

from livingworld.application.card_design import DesignWrite, referenced_images
from livingworld.application.content import ContentDraft
from livingworld.application.content_packages import PackageDraft, PackageError, PackageId
from livingworld.application.exports import ExportRequest, ExportTarget, V3CharacterBookOptions
from livingworld.application.imports import ContentImportError
from livingworld.application.world_covers import MAX_IMAGE_BYTES
from livingworld.domain.content.models import CharacterDefinition, LoreCollection, LoreEntry
from livingworld.domain.content.serialization import stable_json
from livingworld.domain.errors import DomainInvariantError
from livingworld.infrastructure.exports.json_content import JsonContentExporter
from livingworld.infrastructure.imports.charx import read_charx
from livingworld.infrastructure.imports.json_input import read_json_object
from livingworld.infrastructure.packages.lwcontent import LwContentAdapter

MAX_SHARE_BYTES = 32 * 1024 * 1024
IDENTITY = "dreamtalk.character-card"


@dataclass(frozen=True)
class SharedCard:
    draft: ContentDraft
    design: dict | None
    images: tuple[tuple[bytes, dict], ...]


def portable_draft(draft):
    # Old revisions' raw evidence is local history, not part of the current template.
    raw_ids = {root.provenance.raw_import_id for root in draft.contents}
    raw_ids.update(
        raw.import_id
        for raw in draft.raw_imports
        if any(
            asset.extensions.get("raw_import_id") == raw.import_id.value.hex
            for asset in draft.assets
        )
    )
    return replace(
        draft, raw_imports=tuple(raw for raw in draft.raw_imports if raw.import_id in raw_ids)
    )


def character_json(draft):
    character = next(root for root in draft.contents if isinstance(root, CharacterDefinition))
    normalized = replace(
        draft,
        contents=tuple(
            replace(root, example_dialogue=("\n\n".join(root.example_dialogue),))
            if isinstance(root, CharacterDefinition) and len(root.example_dialogue) > 1
            else root
            for root in draft.contents
        ),
    )
    result = JsonContentExporter().serialize(
        ExportRequest(
            draft=normalized,
            content_id=character.content_id,
            target_format=ExportTarget.CHARACTER_CARD_V3,
            embedded_collection_id=character.lore_collection_ids[0]
            if character.lore_collection_ids
            else None,
            v3_book_options=V3CharacterBookOptions(use_regex=False),
            preserve_native_fields=True,
        )
    )
    document = json.loads(result.serialized_bytes)
    document["data"]["extensions"]["dreamtalk.export"] = {
        "version": 1,
        "background": character.background,
        "speech_guidance": character.speech_guidance,
        "aliases": list(character.aliases),
        "example_dialogue": list(character.example_dialogue),
    }
    return stable_json(document).encode("utf-8")


class CardShareCodec:
    def __init__(self, processor):
        self.processor = processor
        self.packages = LwContentAdapter()

    def write(self, card, images):
        draft = portable_draft(card.draft)
        character = next(root for root in draft.contents if isinstance(root, CharacterDefinition))
        public = character_json(draft)
        package = self.packages.write(
            PackageDraft(
                package_id=PackageId(uuid5(card.card_id, f"card-share:1:{card.revision}")),
                created_at_utc=datetime(1980, 1, 1, tzinfo=UTC),
                root_ids=(character.content_id,),
                content=draft,
            )
        )
        files = {"card.json": public, "dreamtalk.lwcontent": package}
        manifest = {
            "format": IDENTITY,
            "version": 1,
            "design": card.design,
            "card_sha256": sha256(public).hexdigest(),
            "content_sha256": sha256(package).hexdigest(),
            "images": [],
        }
        for digest in referenced_images(card.design):
            data, _ = images[digest]
            path = f"assets/x_dreamtalk/images/{digest}"
            files[path] = data
            manifest["images"].append({"digest": digest, "path": path})
        files["dreamtalk.json"] = stable_json(manifest).encode("utf-8")
        target = io.BytesIO()
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_STORED) as archive:
            for path, data in sorted(files.items()):
                info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
                archive.writestr(info, data)
        payload = target.getvalue()
        if len(payload) > MAX_SHARE_BYTES:
            raise ContentImportError("card_share_size_limit")
        self.read(payload)
        return payload

    def read(self, payload):
        if not payload.startswith(b"PK\x03\x04"):
            return None
        # Reuse the existing whole-directory safety/size checks before reading members.
        read_charx(payload, max_json_bytes=MAX_SHARE_BYTES, max_entries=10000)
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                if "dreamtalk.json" not in archive.namelist():
                    return None
                if sum(item.file_size for item in archive.infolist()) > MAX_SHARE_BYTES:
                    raise ContentImportError("card_share_size_limit")

                def read(path, limit=MAX_SHARE_BYTES):
                    if archive.getinfo(path).file_size > limit:
                        raise ContentImportError("card_share_size_limit")
                    return archive.read(path)

                manifest = read_json_object(
                    read("dreamtalk.json", 1024 * 1024),
                    max_bytes=1024 * 1024,
                    max_depth=32,
                    prefix="card_share",
                    root_path="dreamtalk",
                )
                if (
                    manifest.get("format") != IDENTITY
                    or type(manifest.get("version")) is not int
                    or manifest["version"] != 1
                ):
                    raise ContentImportError("card_share_version_unsupported")
                if set(manifest) != {
                    "format",
                    "version",
                    "design",
                    "card_sha256",
                    "content_sha256",
                    "images",
                }:
                    raise ContentImportError("card_share_invalid")
                public, package = read("card.json"), read("dreamtalk.lwcontent")
                if (
                    sha256(public).hexdigest() != manifest["card_sha256"]
                    or sha256(package).hexdigest() != manifest["content_sha256"]
                ):
                    raise ContentImportError("card_share_integrity_mismatch")
                native = self.packages.read(package)
                if native.blobs or any(
                    not isinstance(root, (CharacterDefinition, LoreCollection, LoreEntry))
                    for root in native.content.contents
                ):
                    raise ContentImportError("card_share_character_required")
                characters = [
                    root
                    for root in native.content.contents
                    if isinstance(root, CharacterDefinition)
                ]
                if len(characters) != 1 or native.root_ids != (characters[0].content_id,):
                    raise ContentImportError("card_share_character_required")
                if character_json(native.content) != public:
                    raise ContentImportError("card_share_content_mismatch")
                design = (
                    None
                    if manifest["design"] is None
                    else DesignWrite.model_validate(manifest["design"], strict=True).model_dump()
                )
                expected = referenced_images(design)
                entries = manifest["images"]
                if type(entries) is not list or len(entries) != len(expected):
                    raise ContentImportError("card_share_image_missing")
                images, seen = [], set()
                allowed = {"card.json", "dreamtalk.json", "dreamtalk.lwcontent"}
                for item in entries:
                    if (
                        type(item) is not dict
                        or set(item) != {"digest", "path"}
                        or item["digest"] not in expected
                        or item["digest"] in seen
                    ):
                        raise ContentImportError("card_share_invalid")
                    digest, path = item["digest"], item["path"]
                    if path != f"assets/x_dreamtalk/images/{digest}":
                        raise ContentImportError("card_share_invalid")
                    if archive.getinfo(path).file_size > MAX_IMAGE_BYTES:
                        raise ContentImportError("card_share_image_size_limit")
                    data = archive.read(path)
                    if sha256(data).hexdigest() != digest:
                        raise ContentImportError("card_share_integrity_mismatch")
                    info = self.processor.inspect(data)
                    images.append((data, {**info, "digest": digest, "size": len(data)}))
                    seen.add(digest)
                    allowed.add(path)
                if set(archive.namelist()) != allowed:
                    raise ContentImportError("card_share_unexpected_files")
                return SharedCard(native.content, design, tuple(images))
        except ContentImportError:
            raise
        except (
            KeyError,
            TypeError,
            ValueError,
            OSError,
            ValidationError,
            PackageError,
            DomainInvariantError,
            zipfile.BadZipFile,
            zlib.error,
            EOFError,
            RuntimeError,
        ):
            raise ContentImportError("card_share_invalid") from None
