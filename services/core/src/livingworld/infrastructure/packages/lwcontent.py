"""Bounded ZIP container. Manifest membership is authoritative, filenames are not."""

import stat
import struct
import zipfile
import zlib
from datetime import datetime
from hashlib import sha256
from io import BytesIO
from uuid import UUID

from livingworld.application.content import ContentDraft, RawImportEnvelope
from livingworld.application.content_packages import (
    LWCONTENT_IDENTITY,
    LWCONTENT_PACKAGE_FORMAT,
    AssetBlobBinding,
    PackagedBlob,
    PackageDraft,
    PackageError,
    PackageId,
    PackageLimits,
)
from livingworld.application.imports import ContentImportError
from livingworld.domain.content import LIVINGWORLD_CONTENT_VERSION
from livingworld.domain.content.identifiers import (
    CharacterDefinitionId,
    ContentAssetId,
    LoreCollectionId,
    LoreEntryId,
    RawImportId,
    WorldContentId,
)
from livingworld.domain.content.models import (
    CharacterDefinition,
    LoreEntry,
    WorldContent,
)
from livingworld.domain.content.serialization import (
    content_kind,
    decode_asset,
    decode_provenance,
    deserialize_content,
    json_value,
    semantic_hash,
    serialize_content,
    stable_json,
)
from livingworld.domain.errors import DomainInvariantError
from livingworld.infrastructure.imports.json_input import read_json_object

_IDENTITIES = {
    "character_definition": CharacterDefinitionId,
    "world_content": WorldContentId,
    "lore_collection": LoreCollectionId,
    "lore_entry": LoreEntryId,
    "asset": ContentAssetId,
    "source": RawImportId,
}
_FOLDERS = {
    "character_definition": "characters",
    "world_content": "worlds",
    "lore_collection": "lore_collections",
    "lore_entry": "lore",
}


def identity(value, kind):
    if type(value) is not str or type(kind) is not str or kind not in _IDENTITIES:
        raise PackageError("invalid_manifest_identity")
    try:
        parsed = UUID(hex=value)
        if parsed.hex != value:
            raise ValueError
        return _IDENTITIES[kind](parsed)
    except (ValueError, TypeError, AttributeError):
        raise PackageError("invalid_manifest_identity") from None


def _keys(value, expected):
    if type(value) is not dict or set(value) != set(expected):
        raise PackageError("malformed_package_manifest")
    return value


def _list(value):
    if type(value) is not list:
        raise PackageError("malformed_package_manifest")
    return value


def _ref(kind, value):
    return {"kind": kind, "id": value.value.hex}


def canonical_bindings(draft: ContentDraft) -> list[dict]:
    bindings = []
    for root in draft.contents:
        source = _ref(content_kind(root), root.content_id)
        references = []
        if isinstance(root, LoreEntry):
            if root.collection_id is not None:
                references.append(("collection_owner", _ref("lore_collection", root.collection_id)))
        else:
            references.extend(
                ("lore_entry", _ref("lore_entry", value)) for value in root.lore_entry_ids
            )
            if isinstance(root, (CharacterDefinition, WorldContent)):
                references.extend(
                    ("lore_collection", _ref("lore_collection", value))
                    for value in root.lore_collection_ids
                )
                references.extend(("asset", _ref("asset", value.asset_id)) for value in root.assets)
        if root.provenance.raw_import_id is not None:
            references.append(("source", _ref("source", root.provenance.raw_import_id)))
        bindings.extend(
            {"from": source, "to": target, "relation": relation} for relation, target in references
        )
    for asset in draft.assets:
        raw = asset.extensions.get("raw_import_id")
        if raw is not None:
            bindings.append(
                {
                    "from": _ref("asset", asset.asset_id),
                    "to": {"kind": "source", "id": raw},
                    "relation": "source",
                }
            )
    return sorted(bindings, key=stable_json)


def make_manifest(package: PackageDraft) -> tuple[dict, dict[str, bytes]]:
    files, members, assets, sources = {}, [], [], []
    for root in sorted(
        package.content.contents, key=lambda root: (content_kind(root), root.content_id.value.hex)
    ):
        kind = content_kind(root)
        path = f"content/{_FOLDERS[kind]}/{root.content_id.value.hex}.json"
        payload = serialize_content(root).encode("utf-8")
        files[path] = payload
        members.append(
            {
                "kind": kind,
                "id": root.content_id.value.hex,
                "revision": root.revision.value,
                "semantic_hash": semantic_hash(root),
                "path": path,
                "size": len(payload),
                "sha256": sha256(payload).hexdigest(),
            }
        )
    blobs = {blob.binding.asset_id: blob for blob in package.blobs}
    for asset in sorted(package.content.assets, key=lambda asset: asset.asset_id.value.hex):
        blob = blobs.get(asset.asset_id)
        descriptor = None
        if blob is not None:
            path = f"assets/sha256/{blob.binding.digest}"
            files[path] = blob.data
            descriptor = {"sha256": blob.binding.digest, "size": blob.binding.size, "path": path}
        assets.append({"metadata": json_value(asset), "blob": descriptor})
    for raw in sorted(package.content.raw_imports, key=lambda raw: raw.import_id.value.hex):
        path = f"sources/{raw.import_id.value.hex}/original"
        files[path] = raw.original_payload
        sources.append(
            {
                "id": raw.import_id.value.hex,
                "provenance": json_value(raw.provenance),
                "unknown_extensions": json_value(raw.unknown_extensions),
                "path": path,
                "size": len(raw.original_payload),
                "sha256": sha256(raw.original_payload).hexdigest(),
            }
        )
    roots = sorted(
        (
            _ref(
                content_kind(
                    next(root for root in package.content.contents if root.content_id == value)
                ),
                value,
            )
            for value in package.root_ids
        ),
        key=stable_json,
    )
    return {
        "format": LWCONTENT_IDENTITY,
        "format_version": LWCONTENT_PACKAGE_FORMAT,
        "package_id": package.package_id.value.hex,
        "created_at_utc": json_value(package.created_at_utc),
        "canonical_content_version": {
            "min": LIVINGWORLD_CONTENT_VERSION,
            "max": LIVINGWORLD_CONTENT_VERSION,
        },
        "roots": roots,
        "members": members,
        "assets": assets,
        "sources": sources,
        "bindings": canonical_bindings(package.content),
        "integrity": {"algorithm": "sha256", "semantic_package_hash": package.semantic_hash},
    }, files


def _path(name: str, *, directory: bool = False) -> str:
    if (
        type(name) is not str
        or not name
        or "\x00" in name
        or "\\" in name
        or ":" in name
        or name.startswith("/")
        or any(ord(char) < 32 for char in name)
    ):
        raise PackageError("unsafe_archive_path")
    value = name[:-1] if directory and name.endswith("/") else name
    if any(part in ("", ".", "..") for part in value.split("/")):
        raise PackageError("unsafe_archive_path")
    return value


class LwContentAdapter:
    def __init__(self, limits: PackageLimits | None = None) -> None:
        if limits is None:
            limits = PackageLimits()
        if not isinstance(limits, PackageLimits):
            raise PackageError("invalid_package_limits")
        self.limits = limits

    def write(self, package: PackageDraft) -> bytes:
        manifest, files = make_manifest(package)
        files["manifest.json"] = stable_json(manifest).encode("utf-8")
        target = BytesIO()
        # Stored entries avoid rejecting highly repetitive authored text by our own ratio policy.
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_STORED) as archive:
            for path in sorted(files):
                info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o600) << 16
                archive.writestr(info, files[path])
        payload = target.getvalue()
        self.read(payload)  # Same centralized limits/manifest rules on our own exports.
        return payload

    def _json(self, payload: bytes) -> dict:
        try:
            return read_json_object(
                payload,
                max_bytes=self.limits.max_entry_bytes,
                max_depth=self.limits.max_json_depth,
                prefix="native_package",
                root_path="manifest",
            )
        except ContentImportError as error:
            raise PackageError(error.code) from None

    def read(self, payload: bytes) -> PackageDraft:
        if type(payload) is not bytes:
            raise PackageError("package_requires_bytes")
        if len(payload) > self.limits.max_archive_bytes:
            raise PackageError("archive_size_limit")
        # Bound the central-directory count before ZipFile allocates its member list.
        tail = payload[-(65535 + 22) :]
        end = tail.rfind(b"PK\x05\x06")
        if end < 0 or len(tail) - end < 22:
            raise PackageError("malformed_zip_container")
        _, disk, start_disk, disk_count, count, central_size, central_start, comment = (
            struct.unpack_from("<4s4H2LH", tail, end)
        )
        if (
            len(tail) - end != 22 + comment
            or disk
            or start_disk
            or disk_count != count
            or count == 65535
        ):
            raise PackageError("unsupported_zip_container")
        if count > self.limits.max_entries:
            raise PackageError("archive_entry_count_limit")
        central_end = central_start + central_size
        if central_end != len(payload) - len(tail) + end or central_start < 0:
            raise PackageError("unsupported_zip_container")
        cursor, actual_count = central_start, 0
        while cursor < central_end:
            if cursor + 46 > central_end or payload[cursor : cursor + 4] != b"PK\x01\x02":
                raise PackageError("malformed_zip_container")
            name_size, extra_size, comment_size = struct.unpack_from("<3H", payload, cursor + 28)
            cursor += 46 + name_size + extra_size + comment_size
            actual_count += 1
            if actual_count > self.limits.max_entries:
                raise PackageError("archive_entry_count_limit")
        if cursor != central_end or actual_count != count:
            raise PackageError("malformed_zip_container")
        try:
            with zipfile.ZipFile(BytesIO(payload)) as archive:
                return self._read_archive(archive, len(payload))
        except PackageError:
            raise
        except (
            zipfile.BadZipFile,
            zlib.error,
            OSError,
            EOFError,
            RuntimeError,
            ValueError,
            UnicodeError,
            DomainInvariantError,
            RecursionError,
        ):
            raise PackageError("malformed_native_package") from None

    def _read_archive(self, archive: zipfile.ZipFile, archive_size: int) -> PackageDraft:
        entries, total_declared = {}, 0
        infos = archive.infolist()
        if len(infos) > self.limits.max_entries:
            raise PackageError("archive_entry_count_limit")
        for info in infos:
            directory = info.is_dir()
            path = _path(info.orig_filename, directory=directory)
            if path in entries:
                raise PackageError("duplicate_archive_path")
            mode = stat.S_IFMT(info.external_attr >> 16)
            if (
                mode not in (0, stat.S_IFREG, stat.S_IFDIR)
                or (mode == stat.S_IFDIR) != directory
                and mode != 0
            ):
                raise PackageError("unsupported_archive_member_type")
            if info.flag_bits & 1 or info.compress_type not in (
                zipfile.ZIP_STORED,
                zipfile.ZIP_DEFLATED,
            ):
                raise PackageError("unsupported_archive_member_encoding")
            if directory and info.file_size:
                raise PackageError("invalid_archive_directory")
            if info.file_size > self.limits.max_entry_bytes:
                raise PackageError("archive_single_entry_limit")
            if info.file_size / max(1, info.compress_size) > self.limits.max_compression_ratio:
                raise PackageError("archive_compression_ratio_limit")
            total_declared += info.file_size
            if total_declared > self.limits.max_total_bytes:
                raise PackageError("archive_total_size_limit")
            entries[path] = info
        if "manifest.json" not in entries or entries["manifest.json"].is_dir():
            raise PackageError("missing_package_manifest")
        cache, total_read = {}, 0

        def bounded(path):
            nonlocal total_read
            path = _path(path)
            if path in cache:
                return cache[path]
            info = entries.get(path)
            if info is None or info.is_dir():
                raise PackageError("missing_manifest_member")
            cap = min(
                self.limits.max_entry_bytes,
                self.limits.max_manifest_bytes
                if path == "manifest.json"
                else self.limits.max_entry_bytes,
            )
            if info.file_size > cap:
                raise PackageError(
                    "manifest_size_limit"
                    if path == "manifest.json"
                    else "archive_single_entry_limit"
                )
            data = bytearray()
            with archive.open(info) as source:
                while True:
                    chunk = source.read(
                        min(
                            self.limits.read_chunk_bytes,
                            cap - len(data) + 1,
                            self.limits.max_total_bytes - total_read + 1,
                        )
                    )
                    if not chunk:
                        break
                    total_read += len(chunk)
                    data.extend(chunk)
                    if len(data) > cap or total_read > self.limits.max_total_bytes:
                        raise PackageError("archive_streaming_size_limit")
            if len(data) != info.file_size:
                raise PackageError("archive_member_size_mismatch")
            cache[path] = bytes(data)
            return cache[path]

        manifest = self._json(bounded("manifest.json"))
        # A future version may add fields. Diagnose unsupported semantics before v1 shape checks.
        if (
            manifest.get("format") == LWCONTENT_IDENTITY
            and type(manifest.get("format_version")) is int
        ):
            if manifest["format_version"] > LWCONTENT_PACKAGE_FORMAT:
                raise PackageError("unsupported_newer_package_version")
        _keys(
            manifest,
            {
                "format",
                "format_version",
                "package_id",
                "created_at_utc",
                "canonical_content_version",
                "roots",
                "members",
                "assets",
                "sources",
                "bindings",
                "integrity",
            },
        )
        if manifest["format"] != LWCONTENT_IDENTITY or type(manifest["format_version"]) is not int:
            raise PackageError("malformed_package_identity")
        if manifest["format_version"] > LWCONTENT_PACKAGE_FORMAT:
            raise PackageError("unsupported_newer_package_version")
        if manifest["format_version"] != LWCONTENT_PACKAGE_FORMAT:
            raise PackageError("unsupported_package_version")
        versions = _keys(manifest["canonical_content_version"], {"min", "max"})
        if any(
            type(value) is not int or value != LIVINGWORLD_CONTENT_VERSION
            for value in versions.values()
        ):
            raise PackageError("unsupported_package_content_version")
        try:
            raw_package_id = manifest["package_id"]
            package_uuid = UUID(hex=raw_package_id)
            if package_uuid.hex != raw_package_id:
                raise ValueError
            package_id = PackageId(package_uuid)
            created = datetime.fromisoformat(manifest["created_at_utc"])
        except (ValueError, TypeError, AttributeError):
            raise PackageError("malformed_package_identity") from None
        used, descriptors = {"manifest.json"}, {}

        def member(item):
            path = _path(item["path"])
            if path == "manifest.json":
                raise PackageError("invalid_manifest_member_path")
            digest, size = item["sha256"], item["size"]
            if type(size) is not int or size < 0 or type(digest) is not str:
                raise PackageError("malformed_member_descriptor")
            if path in descriptors and descriptors[path] != (digest, size):
                raise PackageError("conflicting_member_descriptors")
            descriptors[path] = (digest, size)
            data = bounded(path)
            if len(data) != size or sha256(data).hexdigest() != digest:
                raise PackageError("package_integrity_mismatch", path)
            used.add(path)
            return data

        contents, assets, raws, blobs, content_paths = [], [], [], [], set()
        for item in _list(manifest["members"]):
            _keys(item, {"kind", "id", "revision", "semantic_hash", "path", "size", "sha256"})
            data = member(item)
            if item["path"] in content_paths:
                raise PackageError("duplicate_content_member_path")
            content_paths.add(item["path"])
            self._json(data)  # Bounded depth/strict UTF-8 before canonical decoding.
            root = deserialize_content(data.decode("utf-8"))
            if (
                content_kind(root) != item["kind"]
                or root.content_id != identity(item["id"], item["kind"])
                or type(item["revision"]) is not int
                or root.revision.value != item["revision"]
                or semantic_hash(root) != item["semantic_hash"]
            ):
                raise PackageError("canonical_member_descriptor_mismatch")
            if data != serialize_content(root).encode("utf-8"):
                raise PackageError("noncanonical_member_serialization")
            contents.append(root)
        for item in _list(manifest["assets"]):
            _keys(item, {"metadata", "blob"})
            asset = decode_asset(item["metadata"])
            assets.append(asset)
            if item["blob"] is not None:
                descriptor = _keys(item["blob"], {"sha256", "size", "path"})
                data = member(descriptor)
                blobs.append(
                    PackagedBlob(
                        AssetBlobBinding(asset.asset_id, descriptor["sha256"], descriptor["size"]),
                        data,
                    )
                )
        for item in _list(manifest["sources"]):
            _keys(item, {"id", "provenance", "unknown_extensions", "path", "size", "sha256"})
            raws.append(
                RawImportEnvelope(
                    import_id=identity(item["id"], "source"),
                    provenance=decode_provenance(item["provenance"]),
                    original_payload=member(item),
                    unknown_extensions=item["unknown_extensions"],
                )
            )
        draft = ContentDraft(
            contents=tuple(contents), assets=tuple(assets), raw_imports=tuple(raws)
        )
        roots = []
        for item in _list(manifest["roots"]):
            _keys(item, {"kind", "id"})
            roots.append(identity(item["id"], item["kind"]))
        if manifest["bindings"] != canonical_bindings(draft):
            raise PackageError("manifest_bindings_disagree_with_canonical")
        if {path for path, info in entries.items() if not info.is_dir()} != used:
            raise PackageError("unmanifested_archive_member")
        package = PackageDraft(
            package_id=package_id,
            created_at_utc=created,
            root_ids=tuple(roots),
            content=draft,
            blobs=tuple(blobs),
            archive_size=archive_size,
            uncompressed_size=total_read,
        )
        integrity = _keys(manifest["integrity"], {"algorithm", "semantic_package_hash"})
        if (
            integrity["algorithm"] != "sha256"
            or integrity["semantic_package_hash"] != package.semantic_hash
        ):
            raise PackageError("package_semantic_integrity_mismatch")
        return package
