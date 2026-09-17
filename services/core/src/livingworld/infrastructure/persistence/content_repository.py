"""Atomic content-library writes with no runtime UoW, ledger or knowledge capability."""

from collections.abc import Mapping

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from livingworld.application.content import ContentConflictError, ContentDraft, RawImportEnvelope
from livingworld.domain.content.identifiers import (
    CharacterDefinitionId,
    ContentAssetId,
    ContentId,
    LoreEntryId,
    RawImportId,
    WorldContentId,
)
from livingworld.domain.content.models import (
    CanonicalContent,
    CharacterDefinition,
    ContentAsset,
    ContentRevision,
    WorldContent,
)
from livingworld.domain.content.serialization import (
    decode_asset,
    decode_provenance,
    deserialize_content,
    json_value,
    parse_json,
    semantic_hash,
    serialize_content,
    stable_json,
)
from livingworld.domain.errors import DomainInvariantError
from livingworld.domain.values import require_type
from livingworld.infrastructure.persistence.content_models import (
    CharacterDefinitionRecord,
    ContentAssetRecord,
    LoreEntryRecord,
    RawImportRecord,
    WorldContentRecord,
)
from livingworld.infrastructure.persistence.errors import PersistenceDataError

_RECORDS = {
    CharacterDefinitionId: CharacterDefinitionRecord,
    WorldContentId: WorldContentRecord,
    LoreEntryId: LoreEntryRecord,
}


def _record_type(content_id: ContentId) -> type:
    model = _RECORDS.get(type(content_id))
    if model is None:
        raise DomainInvariantError("Content repository requires a typed content identity")
    return model


def _title(content: CanonicalContent) -> str:
    if isinstance(content, CharacterDefinition):
        return content.display_name
    if isinstance(content, WorldContent):
        return content.title
    return content.title


def _loaded(record: object, content_id: ContentId) -> CanonicalContent:
    content = deserialize_content(record.canonical_json)
    if (
        content.content_id != content_id
        or content.revision.value != record.revision
        or content.content_version != record.content_version
        or _title(content) != record.title
        or semantic_hash(content) != record.semantic_hash
    ):
        raise PersistenceDataError("stored_content_metadata_mismatch")
    return content


class SqlAlchemyContentRepository:
    def __init__(self, sessions: async_sessionmaker) -> None:
        self._sessions = sessions

    async def load(self, content_id: ContentId) -> CanonicalContent | None:
        model = _record_type(content_id)
        async with self._sessions() as session:
            record = await session.get(model, content_id.value)
            if record is None:
                return None
            return _loaded(record, content_id)

    async def load_asset(self, asset_id: ContentAssetId) -> ContentAsset | None:
        require_type(asset_id, ContentAssetId, "asset_id")
        async with self._sessions() as session:
            record = await session.get(ContentAssetRecord, asset_id.value)
            if record is None:
                return None
            asset = decode_asset(parse_json(record.metadata_json))
            if (
                asset.asset_id != asset_id
                or asset.media_type != record.media_type
                or asset.resource_reference != record.resource_reference
            ):
                raise PersistenceDataError("stored_asset_metadata_mismatch")
            return asset

    async def load_raw_import(self, import_id: RawImportId) -> RawImportEnvelope | None:
        require_type(import_id, RawImportId, "import_id")
        async with self._sessions() as session:
            record = await session.get(RawImportRecord, import_id.value)
            if record is None:
                return None
            envelope = RawImportEnvelope(
                import_id=import_id,
                provenance=decode_provenance(parse_json(record.provenance_json)),
                original_payload=record.original_payload,
                unknown_extensions=parse_json(record.extensions_json),
            )
            if envelope.provenance.content_hash != record.content_hash:
                raise PersistenceDataError("stored_raw_hash_mismatch")
            return envelope

    async def save(
        self,
        draft: ContentDraft,
        expected_revisions: Mapping[ContentId, ContentRevision | None],
    ) -> None:
        require_type(draft, ContentDraft, "draft")
        if not isinstance(expected_revisions, Mapping) or set(expected_revisions) != {
            content.content_id for content in draft.contents
        }:
            raise DomainInvariantError(
                "Expected content revisions must cover exactly the draft IDs"
            )
        expected = dict(expected_revisions)
        for revision in expected.values():
            if revision is not None:
                require_type(revision, ContentRevision, "expected content revision")
        try:
            async with self._sessions() as session, session.begin():
                await session.connection(execution_options={"livingworld_write_intent": True})
                for envelope in draft.raw_imports:
                    values = {
                        "import_id": envelope.import_id.value,
                        "content_hash": envelope.provenance.content_hash,
                        "provenance_json": stable_json(json_value(envelope.provenance)),
                        "extensions_json": stable_json(envelope.unknown_extensions),
                        "original_payload": envelope.original_payload,
                    }
                    record = await session.get(RawImportRecord, envelope.import_id.value)
                    if record is None:
                        session.add(RawImportRecord(**values))
                    elif any(getattr(record, key) != value for key, value in values.items()):
                        raise ContentConflictError("Raw import identity is immutable")
                for asset in draft.assets:
                    values = {
                        "asset_id": asset.asset_id.value,
                        "media_type": asset.media_type,
                        "resource_reference": asset.resource_reference,
                        "metadata_json": stable_json(json_value(asset)),
                    }
                    record = await session.get(ContentAssetRecord, asset.asset_id.value)
                    if record is None:
                        session.add(ContentAssetRecord(**values))
                    elif any(getattr(record, key) != value for key, value in values.items()):
                        raise ContentConflictError("Asset reference identity is immutable")
                for content in draft.contents:
                    model = _record_type(content.content_id)
                    precondition = expected[content.content_id]
                    record = await session.get(model, content.content_id.value)
                    values = {
                        "title": _title(content),
                        "content_version": content.content_version,
                        "revision": content.revision.value,
                        "semantic_hash": semantic_hash(content),
                        "canonical_json": serialize_content(content),
                    }
                    if precondition is None:
                        if record is not None or content.revision != ContentRevision():
                            raise ContentConflictError(
                                "New content requires absent identity/revision zero"
                            )
                        session.add(model(content_id=content.content_id.value, **values))
                    else:
                        if record is None or record.revision != precondition.value:
                            raise ContentConflictError("Stale content revision")
                        _loaded(record, content.content_id)
                        if record.semantic_hash == values["semantic_hash"]:
                            # An unchanged dependency is retained, never silently overwritten.
                            if record.canonical_json != values["canonical_json"]:
                                raise PersistenceDataError("stored_content_hash_collision")
                            continue
                        if content.revision.value != precondition.value + 1:
                            raise ContentConflictError(
                                "Content edit must advance exactly one revision"
                            )
                        result = await session.execute(
                            update(model)
                            .where(
                                model.content_id == content.content_id.value,
                                model.revision == precondition.value,
                            )
                            .values(**values)
                        )
                        if result.rowcount != 1:
                            raise ContentConflictError("Content revision compare-and-swap failed")
                await session.flush()
        except IntegrityError:
            raise ContentConflictError("Content persistence constraint conflict") from None
