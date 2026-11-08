"""Whole-world erasure in one writer transaction, including independent authored copies."""

import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, func, select, text

from livingworld.application.errors import EntityNotFoundError
from livingworld.infrastructure.persistence.content_models import (
    AcceptedImportBaselineRecord,
    AssetBlobBindingRecord,
    CharacterDefinitionRecord,
    ContentAssetRecord,
    LoreCollectionRecord,
    LoreEntryRecord,
    RawImportRecord,
    WorldContentRecord,
)
from livingworld.infrastructure.persistence.deletion_models import WorldDeletionRecord
from livingworld.infrastructure.persistence.models import (
    Base,
    WorldContentImportRecord,
    WorldRecord,
)
from livingworld.infrastructure.persistence.world_cover_models import WorldCoverImageRecord

ROOT_MODELS = (CharacterDefinitionRecord, WorldContentRecord, LoreEntryRecord, LoreCollectionRecord)


def _identities(roots):
    contents, assets, raw = set(), set(), set()
    for encoded in roots:
        data = json.loads(encoded)["data"]
        contents.add(UUID(data["content_id"]))
        assets.update(UUID(item["asset_id"]) for item in data.get("assets", []))
        source = data.get("provenance", {}).get("raw_import_id")
        if source:
            raw.add(UUID(source))
    return contents, assets, raw


class SqlAlchemyWorldDeletionStore:
    def __init__(self, sessions):
        self.sessions = sessions

    async def deleted(self, world_id):
        async with self.sessions() as session:
            return await session.get(WorldDeletionRecord, world_id.value) is not None

    async def purge(self, world_id, expected_name):
        async with self.sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            receipt = await session.get(WorldDeletionRecord, world_id.value)
            if receipt is not None:
                retained = set(await session.scalars(select(WorldCoverImageRecord.digest)))
                retained.update(await session.scalars(select(AssetBlobBindingRecord.digest)))
                pending = tuple(sorted(set(json.loads(receipt.pending_assets_json)) - retained))
                receipt.pending_assets_json = json.dumps(pending)
                return pending
            world = await session.get(WorldRecord, world_id.value)
            if world is None:
                raise EntityNotFoundError("world_not_found")
            if world.name != expected_name:
                raise ValueError("world_delete_confirmation_changed")
            # Keep foreign_keys ON; check the cyclic world graph atomically at commit.
            await session.execute(text("PRAGMA defer_foreign_keys = ON"))
            snapshots = await session.scalars(
                select(WorldContentImportRecord.snapshot_json).where(
                    WorldContentImportRecord.world_id == world_id.value
                )
            )
            roots = [root for snapshot in snapshots for root in json.loads(snapshot)]
            content_ids, asset_ids, raw_ids = _identities(roots)
            # Other worlds may share a library identity. Read only their content IDs.
            keep = set()
            rows = await session.execute(
                text(
                    "SELECT DISTINCT json_extract(j.value, '$.data.content_id') "
                    "FROM world_content_imports i, json_each(i.snapshot_json) j "
                    "WHERE i.world_id != :world"
                ),
                {"world": world_id.value.hex},
            )
            keep.update(UUID(row[0]) for row in rows)
            removable = content_ids - keep
            digests = set(
                await session.scalars(
                    select(WorldCoverImageRecord.digest).where(
                        WorldCoverImageRecord.world_id == world_id.value
                    )
                )
            )
            receipt = WorldDeletionRecord(
                world_id=world_id.value, deleted_at=datetime.now(UTC), pending_assets_json="[]"
            )
            session.add(receipt)
            await session.flush()
            # Base is the reviewed world-owned schema; global profiles and financial
            # accounting have no world_id and must never be erased/reset here.
            for table in Base.metadata.tables.values():
                if "world_id" in table.c and table.name not in {"worlds", "world_deletions"}:
                    await session.execute(delete(table).where(table.c.world_id == world_id.value))
            for model in ROOT_MODELS:
                await session.execute(delete(model).where(model.content_id.in_(removable)))
            await session.execute(
                delete(AcceptedImportBaselineRecord).where(
                    AcceptedImportBaselineRecord.content_id.in_(removable)
                )
            )
            # Dependency references come from metadata, never another world's chat text.
            keep_assets, keep_raw = set(), set()
            for model in ROOT_MODELS:
                references = await session.execute(
                    select(
                        func.json_extract(model.canonical_json, "$.data.assets"),
                        func.json_extract(model.canonical_json, "$.data.provenance.raw_import_id"),
                    )
                )
                for asset_json, raw in references:
                    if asset_json:
                        keep_assets.update(
                            UUID(item["asset_id"]) for item in json.loads(asset_json)
                        )
                    if raw:
                        keep_raw.add(UUID(raw))
            remove_assets = asset_ids - keep_assets
            digests.update(
                await session.scalars(
                    select(AssetBlobBindingRecord.digest).where(
                        AssetBlobBindingRecord.asset_id.in_(remove_assets)
                    )
                )
            )
            # Raw provenance of removed assets is part of the erased import graph.
            for raw in await session.scalars(
                select(
                    func.json_extract(
                        ContentAssetRecord.metadata_json, "$.provenance.raw_import_id"
                    )
                ).where(ContentAssetRecord.asset_id.in_(remove_assets))
            ):
                if raw:
                    raw_ids.add(UUID(raw))
            await session.execute(
                delete(AssetBlobBindingRecord).where(
                    AssetBlobBindingRecord.asset_id.in_(remove_assets)
                )
            )
            await session.execute(
                delete(ContentAssetRecord).where(ContentAssetRecord.asset_id.in_(remove_assets))
            )
            for raw in await session.scalars(
                select(
                    func.json_extract(
                        ContentAssetRecord.metadata_json, "$.provenance.raw_import_id"
                    )
                )
            ):
                if raw:
                    keep_raw.add(UUID(raw))
            await session.execute(
                delete(RawImportRecord).where(RawImportRecord.import_id.in_(raw_ids - keep_raw))
            )
            await session.execute(delete(WorldRecord).where(WorldRecord.world_id == world_id.value))
            retained = set(await session.scalars(select(WorldCoverImageRecord.digest)))
            retained.update(await session.scalars(select(AssetBlobBindingRecord.digest)))
            pending = tuple(sorted(digests - retained))
            receipt.pending_assets_json = json.dumps(pending)
            return pending

    async def assets_removed(self, world_id, digests):
        async with self.sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            receipt = await session.get(WorldDeletionRecord, world_id.value)
            if receipt is not None:
                pending = set(json.loads(receipt.pending_assets_json)) - set(digests)
                receipt.pending_assets_json = json.dumps(sorted(pending))
