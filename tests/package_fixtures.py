"""A small authored ecosystem; binary blobs are generated in memory, never downloaded."""

import zipfile
from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from io import BytesIO
from uuid import uuid4

from livingworld.application.content import ContentDraft
from livingworld.application.content_packages import (
    AssetBlobBinding,
    PackagedBlob,
    PackageDraft,
    PackageId,
)
from livingworld.application.package_service import PackageService
from livingworld.domain.content.identifiers import (
    CharacterDefinitionId,
    ContentAssetId,
    WorldContentId,
)
from livingworld.domain.content.models import (
    AssetReference,
    CharacterDefinition,
    ContentAsset,
    ContentProvenance,
    ContentRevision,
    ContentSourceKind,
    WorldContent,
)
from livingworld.infrastructure.imports.lorebooks import LorebookImporter
from livingworld.infrastructure.packages.lwcontent import LwContentAdapter
from lorebook_fixtures import preserved_card, roots, standalone

NOW = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)
LOCAL_ASSET = b"LivingWorld controlled local asset\x00\x01\x02"


def native_package():
    card = LorebookImporter().normalize_embedded(preserved_card(3))
    native_lore = standalone()
    collections = (roots(card)[0].content_id, roots(native_lore)[0].content_id)
    provenance = ContentProvenance(
        source_kind=ContentSourceKind.NATIVE, source_format="livingworld-native"
    )
    digest = sha256(LOCAL_ASSET).hexdigest()
    assets = tuple(
        ContentAsset(
            asset_id=ContentAssetId(uuid4()),
            media_type="application/octet-stream",
            resource_reference="sha256:" + digest,
            content_hash=digest,
        )
        for _ in range(2)
    )
    references = tuple(
        AssetReference(asset_id=asset.asset_id, role="test-asset") for asset in assets
    )
    first = replace(roots(card)[2][0], lore_collection_ids=collections, revision=ContentRevision(4))
    second = CharacterDefinition(
        content_id=CharacterDefinitionId(uuid4()),
        display_name="Second Character",
        lore_collection_ids=(collections[1],),
        assets=references,
        provenance=provenance,
        revision=ContentRevision(2),
    )
    world = WorldContent(
        content_id=WorldContentId(uuid4()),
        title="Authored Ecosystem",
        setting="Test setting",
        lore_collection_ids=collections,
        assets=references,
        provenance=provenance,
        revision=ContentRevision(7),
    )
    contents = (
        world,
        first,
        second,
        *(root for root in card.draft.contents if root.content_id != first.content_id),
        *native_lore.draft.contents,
    )
    return PackageDraft(
        package_id=PackageId(uuid4()),
        created_at_utc=NOW,
        root_ids=(world.content_id, first.content_id, second.content_id),
        content=ContentDraft(
            contents=contents,
            assets=(*card.draft.assets, *assets),
            raw_imports=(*card.draft.raw_imports, *native_lore.draft.raw_imports),
        ),
        blobs=tuple(
            PackagedBlob(AssetBlobBinding(asset.asset_id, digest, len(LOCAL_ASSET)), LOCAL_ASSET)
            for asset in assets
        ),
    )


def simple_package(character=None):
    character = character or CharacterDefinition(
        content_id=CharacterDefinitionId(uuid4()),
        display_name="Character",
        provenance=ContentProvenance(source_kind=ContentSourceKind.NATIVE, source_format="native"),
    )
    return PackageDraft(
        package_id=PackageId(uuid4()),
        created_at_utc=NOW,
        root_ids=(character.content_id,),
        content=ContentDraft(contents=(character,)),
    )


def service(database, adapter=None):
    return PackageService(
        database.package_repository(), database.content_asset_store(), adapter or LwContentAdapter()
    )


async def accept(database, package, decisions=None):
    app = service(database)
    draft = app.parse(LwContentAdapter().write(package))
    preview = await app.preview(draft)
    await app.commit(
        preview, reviewed_hash=preview.reviewed_hash, decisions=decisions or {}, accepted_at_utc=NOW
    )
    return preview


def zip_members(payload):
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        return {info.filename: archive.read(info) for info in archive.infolist()}


def zip_bytes(members, *, extras=(), compression=zipfile.ZIP_STORED):
    target = BytesIO()
    with zipfile.ZipFile(target, "w", compression=compression) as archive:
        for path, data in members.items():
            archive.writestr(path, data)
        for info, data in extras:
            archive.writestr(info, data)
    return target.getvalue()
