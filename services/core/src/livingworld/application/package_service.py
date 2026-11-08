"""Dependency closure and reviewed native imports through content-only ports."""

from collections.abc import Mapping
from datetime import datetime
from uuid import UUID

from livingworld.application.content import ContentDraft
from livingworld.application.content_packages import (
    AcceptedImportBaseline,
    ConflictDecision,
    ConflictState,
    ContentAssetStore,
    PackageAdapter,
    PackageConflict,
    PackagedBlob,
    PackageDraft,
    PackageError,
    PackageExportResult,
    PackageId,
    PackagePreview,
    PackageRepository,
    content_dependencies,
)
from livingworld.domain.content.identifiers import ContentId, RawImportId
from livingworld.domain.content.models import CharacterDefinition, WorldContent
from livingworld.domain.content.serialization import semantic_hash
from livingworld.domain.errors import DomainInvariantError
from livingworld.domain.values import utc_timestamp


def _ordered(values):
    return sorted(values, key=lambda identity: (type(identity).__name__, identity.value.hex))


def _add(target, identity, value):
    if value is None:
        raise PackageError("unresolved_package_dependency")
    if identity in target and target[identity] != value:
        raise PackageError("incompatible_shared_dependency")
    target[identity] = value


class PackageService:
    def __init__(
        self, repository: PackageRepository, assets: ContentAssetStore, adapter: PackageAdapter
    ):
        self._repository, self._assets, self._adapter = repository, assets, adapter

    async def _collect(self, identities, preferred=None):
        contents, pending = {}, list(identities)
        preferred = preferred or {}
        while pending:
            identity = pending.pop()
            if not isinstance(identity, ContentId.__value__):
                raise PackageError("invalid_package_content_identity")
            if identity in contents:
                continue
            root = preferred.get(identity)
            if root is None:
                root = await self._repository.load(identity)
            _add(contents, identity, root)
            pending.extend(content_dependencies(root))
        return contents

    async def _dependencies(self, contents, incoming=None, accepted=frozenset()):
        assets, sources = {}, {}
        incoming_assets = {asset.asset_id: asset for asset in incoming.assets} if incoming else {}
        incoming_sources = {raw.import_id: raw for raw in incoming.raw_imports} if incoming else {}
        for identity in _ordered(contents):
            root = contents[identity]
            from_incoming = identity in accepted
            if isinstance(root, (CharacterDefinition, WorldContent)):
                for reference in root.assets:
                    asset = incoming_assets.get(reference.asset_id) if from_incoming else None
                    if asset is None:
                        asset = await self._repository.load_asset(reference.asset_id)
                    _add(assets, reference.asset_id, asset)
                    raw_id = asset.extensions.get("raw_import_id")
                    if raw_id is not None:
                        try:
                            raw_uuid = UUID(hex=raw_id)
                            if raw_uuid.hex != raw_id:
                                raise ValueError
                            raw_identity = RawImportId(raw_uuid)
                        except (TypeError, ValueError, AttributeError):
                            raise PackageError("invalid_asset_source_identity") from None
                        raw = incoming_sources.get(raw_identity) if from_incoming else None
                        if raw is None:
                            raw = await self._repository.load_raw_import(raw_identity)
                        _add(sources, raw_identity, raw)
            if root.provenance.raw_import_id is not None:
                raw_id = root.provenance.raw_import_id
                raw = incoming_sources.get(raw_id) if from_incoming else None
                if raw is None:
                    raw = await self._repository.load_raw_import(raw_id)
                _add(sources, raw_id, raw)
        return tuple(assets[identity] for identity in _ordered(assets)), tuple(
            sources[identity] for identity in _ordered(sources)
        )

    async def export(
        self, root_ids: tuple[ContentId, ...], *, package_id: PackageId, created_at_utc: datetime
    ) -> PackageExportResult:
        if (
            not isinstance(root_ids, (tuple, list))
            or not root_ids
            or len(set(root_ids)) != len(root_ids)
        ):
            raise PackageError("invalid_package_roots")
        contents = await self._collect(root_ids)
        assets, sources = await self._dependencies(contents)
        blobs = []
        for asset in assets:
            binding = await self._repository.load_blob_binding(asset.asset_id)
            if binding is not None:
                blobs.append(PackagedBlob(binding, await self._assets.read(binding)))
        package = PackageDraft(
            package_id=package_id,
            created_at_utc=created_at_utc,
            root_ids=tuple(root_ids),
            content=ContentDraft(
                contents=tuple(contents[key] for key in _ordered(contents)),
                assets=assets,
                raw_imports=sources,
            ),
            blobs=tuple(blobs),
        )
        warnings = PackagePreview(package, ()).warnings
        return PackageExportResult(self._adapter.write(package), package, warnings)

    def parse(self, payload: bytes) -> PackageDraft:
        # The adapter completes all container/integrity/graph validation before any store call.
        return self._adapter.read(payload)

    async def preview(self, package: PackageDraft) -> PackagePreview:
        if not isinstance(package, PackageDraft):
            raise PackageError("invalid_package_draft")
        conflicts = []
        for incoming in package.content.contents:
            local = await self._repository.load(incoming.content_id)
            baseline = await self._repository.load_baseline(incoming.content_id)
            conflicts.append(PackageConflict(incoming, local, baseline))
        return PackagePreview(package, tuple(conflicts))

    async def commit(
        self,
        preview: PackagePreview,
        *,
        reviewed_hash: str,
        decisions: Mapping[ContentId, ConflictDecision],
        accepted_at_utc: datetime,
    ) -> None:
        if not isinstance(preview, PackagePreview) or reviewed_hash != preview.reviewed_hash:
            raise PackageError("package_review_required")
        incoming = {root.content_id: root for root in preview.package.content.contents}
        if (
            len(preview.conflicts) != len(incoming)
            or any(
                item.incoming != incoming.get(item.incoming.content_id)
                or item.local is not None
                and item.local.content_id != item.incoming.content_id
                or item.baseline is not None
                and item.baseline.content_id != item.incoming.content_id
                for item in preview.conflicts
            )
            or {item.incoming.content_id for item in preview.conflicts} != set(incoming)
        ):
            raise PackageError("invalid_package_preview")
        accepted_at_utc = utc_timestamp(accepted_at_utc, "accepted time")
        if not isinstance(decisions, Mapping):
            raise PackageError("invalid_conflict_decisions")
        ids = {item.incoming.content_id for item in preview.conflicts}
        if not set(decisions) <= ids or any(
            not isinstance(value, ConflictDecision) for value in decisions.values()
        ):
            raise PackageError("invalid_conflict_decisions")
        selected, accepted = {}, set()
        for item in preview.conflicts:
            identity = item.incoming.content_id
            decision = decisions.get(identity)
            if item.state not in (ConflictState.NEW, ConflictState.IDENTICAL) and decision is None:
                raise PackageError("conflict_decision_required")
            if decision is ConflictDecision.KEEP_LOCAL:
                if item.local is None:
                    raise PackageError("cannot_keep_missing_content")
                selected[identity] = item.local
            else:
                selected[identity] = item.incoming
                accepted.add(identity)
        contents = await self._collect(_ordered(selected), selected)
        expected = list(preview.conflicts)
        for identity in _ordered(set(contents) - ids):
            root = contents[identity]
            expected.append(
                PackageConflict(root, root, await self._repository.load_baseline(identity))
            )
        assets, sources = await self._dependencies(contents, preview.package.content, accepted)
        try:
            draft = ContentDraft(
                contents=tuple(contents[key] for key in _ordered(contents)),
                assets=assets,
                raw_imports=sources,
            )
        except DomainInvariantError:
            raise PackageError("conflict_decisions_break_content_graph") from None
        incoming_blobs = {blob.binding.asset_id: blob for blob in preview.package.blobs}
        accepted_assets = {
            ref.asset_id
            for identity in accepted
            if isinstance(contents[identity], (CharacterDefinition, WorldContent))
            for ref in contents[identity].assets
        }
        bindings, materialize = [], []
        for asset in assets:
            blob = incoming_blobs.get(asset.asset_id) if asset.asset_id in accepted_assets else None
            if blob is not None:
                bindings.append(blob.binding)
                materialize.append(blob)
            else:
                binding = await self._repository.load_blob_binding(asset.asset_id)
                if binding is not None:
                    # A committed reference must never point at a missing/corrupt blob.
                    PackagedBlob(binding, await self._assets.read(binding))
                    bindings.append(binding)
        baselines = tuple(
            AcceptedImportBaseline(
                identity,
                semantic_hash(contents[identity]),
                accepted_at_utc,
                preview.package.package_id,
                preview.package.semantic_hash,
            )
            for identity in _ordered(accepted)
        )
        for blob in materialize:
            await self._assets.materialize(blob)
        # Orphan immutable blobs may survive a failure here; no DB content becomes visible.
        await self._repository.commit_package(
            draft, expected=tuple(expected), accepted=baselines, bindings=tuple(bindings)
        )
