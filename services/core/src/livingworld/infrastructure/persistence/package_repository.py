"""Explicit native snapshot acceptance with transactional local baseline evidence."""

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from livingworld.application.content import ContentConflictError, ContentDraft
from livingworld.application.content_packages import (
    AcceptedImportBaseline,
    AssetBlobBinding,
    PackageError,
    PackageId,
)
from livingworld.domain.content.identifiers import (
    CharacterDefinitionId,
    LoreCollectionId,
    LoreEntryId,
    WorldContentId,
)
from livingworld.domain.content.models import LoreCollection, LoreEntry
from livingworld.domain.content.serialization import semantic_hash, serialize_content
from livingworld.infrastructure.persistence.content_models import (
    AcceptedImportBaselineRecord,
    AssetBlobBindingRecord,
    LoreEntryRecord,
)
from livingworld.infrastructure.persistence.content_repository import (
    SqlAlchemyContentRepository,
    _loaded,
    _record_type,
    _save_dependencies,
    _title,
)

_ID_KINDS = {
    CharacterDefinitionId: "character_definition",
    WorldContentId: "world_content",
    LoreEntryId: "lore_entry",
    LoreCollectionId: "lore_collection",
}


def _baseline(record, content_id):
    if record is None:
        return None
    return AcceptedImportBaseline(
        content_id,
        record.accepted_semantic_hash,
        record.accepted_at_utc,
        PackageId(record.source_package_id) if record.source_package_id is not None else None,
        record.source_package_hash,
    )


class SqlAlchemyPackageRepository(SqlAlchemyContentRepository):
    async def load_baseline(self, content_id):
        _record_type(content_id)
        async with self._sessions() as session:
            return _baseline(
                await session.get(
                    AcceptedImportBaselineRecord, (_ID_KINDS[type(content_id)], content_id.value)
                ),
                content_id,
            )

    async def load_blob_binding(self, asset_id):
        async with self._sessions() as session:
            record = await session.get(AssetBlobBindingRecord, asset_id.value)
            return (
                AssetBlobBinding(asset_id, record.digest, record.size)
                if record is not None
                else None
            )

    async def commit_package(self, draft: ContentDraft, *, expected, accepted, bindings):
        if not isinstance(draft, ContentDraft):
            raise PackageError("invalid_package_commit")
        roots = {root.content_id: root for root in draft.contents}
        preconditions = {item.incoming.content_id: item for item in expected}
        if len(preconditions) != len(expected) or set(preconditions) != set(roots):
            raise PackageError("incomplete_package_preconditions")
        if len({item.content_id for item in accepted}) != len(accepted) or any(
            item.content_id not in roots
            or item.accepted_semantic_hash != semantic_hash(roots[item.content_id])
            for item in accepted
        ):
            raise PackageError("invalid_accepted_baselines")
        if len({item.asset_id for item in bindings}) != len(bindings) or not {
            item.asset_id for item in bindings
        } <= {asset.asset_id for asset in draft.assets}:
            raise PackageError("invalid_package_asset_bindings")
        try:
            async with self._sessions() as session, session.begin():
                await session.connection(execution_options={"livingworld_write_intent": True})
                records = {}
                for identity, item in preconditions.items():
                    record = await session.get(_record_type(identity), identity.value)
                    local = _loaded(record, identity) if record is not None else None
                    baseline = _baseline(
                        await session.get(
                            AcceptedImportBaselineRecord,
                            (_ID_KINDS[type(identity)], identity.value),
                        ),
                        identity,
                    )
                    if local != item.local or baseline != item.baseline:
                        raise ContentConflictError("Native import preview is stale")
                    records[identity] = record
                await _save_dependencies(session, draft)
                for root in sorted(
                    draft.contents, key=lambda root: not isinstance(root, LoreCollection)
                ):
                    identity = root.content_id
                    model, record = _record_type(identity), records[identity]
                    values = {
                        "title": _title(root),
                        "content_version": root.content_version,
                        "revision": root.revision.value,
                        "semantic_hash": semantic_hash(root),
                        "canonical_json": serialize_content(root),
                    }
                    if isinstance(root, LoreEntry):
                        if root.collection_id is None:
                            raise PackageError("legacy_unbound_lore_not_portable")
                        values["collection_id"] = root.collection_id.value
                        if record is not None and record.collection_id != root.collection_id.value:
                            raise ContentConflictError("LoreEntry ownership cannot be reassigned")
                    if record is None:
                        # Imported snapshot history is preserved, not disguised as a new local edit.
                        session.add(model(content_id=identity.value, **values))
                    elif record.canonical_json != values["canonical_json"]:
                        result = await session.execute(
                            update(model)
                            .where(
                                model.content_id == identity.value,
                                model.semantic_hash == record.semantic_hash,
                                model.revision == record.revision,
                            )
                            .values(**values)
                        )
                        if result.rowcount != 1:
                            raise ContentConflictError("Native snapshot compare-and-swap failed")
                await session.flush()
                for root in draft.contents:
                    if isinstance(root, LoreCollection):
                        members = set(
                            (
                                await session.scalars(
                                    select(LoreEntryRecord.content_id).where(
                                        LoreEntryRecord.collection_id == root.content_id.value
                                    )
                                )
                            ).all()
                        )
                        if members != {identity.value for identity in root.lore_entry_ids}:
                            raise ContentConflictError(
                                "Native replacement cannot discard owned entries"
                            )
                for binding in bindings:
                    record = await session.get(AssetBlobBindingRecord, binding.asset_id.value)
                    if record is None:
                        session.add(
                            AssetBlobBindingRecord(
                                asset_id=binding.asset_id.value,
                                digest=binding.digest,
                                size=binding.size,
                            )
                        )
                    elif (record.digest, record.size) != (binding.digest, binding.size):
                        raise ContentConflictError("Asset blob binding identity is immutable")
                for baseline in accepted:
                    key = (_ID_KINDS[type(baseline.content_id)], baseline.content_id.value)
                    values = {
                        "accepted_semantic_hash": baseline.accepted_semantic_hash,
                        "accepted_at_utc": baseline.accepted_at_utc,
                        "source_package_id": baseline.source_package_id.value
                        if baseline.source_package_id
                        else None,
                        "source_package_hash": baseline.source_package_hash,
                    }
                    record = await session.get(AcceptedImportBaselineRecord, key)
                    if record is None:
                        session.add(
                            AcceptedImportBaselineRecord(
                                content_kind=key[0], content_id=key[1], **values
                            )
                        )
                    else:
                        for name, value in values.items():
                            setattr(record, name, value)
                await session.flush()
        except IntegrityError:
            raise ContentConflictError("Native content transaction constraint conflict") from None
