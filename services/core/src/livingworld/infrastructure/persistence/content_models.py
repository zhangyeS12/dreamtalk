"""Separate typed content tables; runtime projections contain no authored JSON."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from livingworld.infrastructure.persistence.types import UTCTimestampStorage, UUIDStorage


class ContentBase(DeclarativeBase):
    pass


class _RootColumns:
    content_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content_version: Mapped[int] = mapped_column(Integer, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    semantic_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_json: Mapped[str] = mapped_column(Text, nullable=False)


def root_checks(table: str) -> tuple:
    return (
        CheckConstraint("length(trim(title)) > 0", name=f"ck_{table}_title"),
        CheckConstraint(
            "typeof(content_version) = 'integer' AND content_version = 1",
            name=f"ck_{table}_version",
        ),
        CheckConstraint(
            "typeof(revision) = 'integer' AND revision >= 0", name=f"ck_{table}_revision"
        ),
        CheckConstraint("length(semantic_hash) = 64", name=f"ck_{table}_hash"),
        CheckConstraint("json_valid(canonical_json)", name=f"ck_{table}_json"),
    )


class CharacterDefinitionRecord(_RootColumns, ContentBase):
    __tablename__ = "content_character_definitions"
    __table_args__ = root_checks(__tablename__)


class WorldContentRecord(_RootColumns, ContentBase):
    __tablename__ = "content_worlds"
    __table_args__ = root_checks(__tablename__)


class LoreEntryRecord(_RootColumns, ContentBase):
    __tablename__ = "content_lore_entries"
    collection_id: Mapped[UUID | None] = mapped_column(
        UUIDStorage(),
        ForeignKey("content_lore_collections.content_id"),
        nullable=True,
        sort_order=100,
    )
    # Lore may have no authored title; use distinct checks for its nonempty body in JSON.
    __table_args__ = tuple(
        constraint
        for constraint in root_checks(__tablename__)
        if constraint.name != "ck_content_lore_entries_title"
    )


class LoreCollectionRecord(_RootColumns, ContentBase):
    __tablename__ = "content_lore_collections"
    # An external book may be unnamed, including a valid empty collection.
    __table_args__ = tuple(
        constraint
        for constraint in root_checks(__tablename__)
        if constraint.name != "ck_content_lore_collections_title"
    )


class ContentAssetRecord(ContentBase):
    __tablename__ = "content_assets"
    asset_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    media_type: Mapped[str] = mapped_column(Text, nullable=False)
    resource_reference: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False)
    __table_args__ = (
        CheckConstraint("length(trim(media_type)) > 0", name="ck_content_assets_media_type"),
        CheckConstraint("length(trim(resource_reference)) > 0", name="ck_content_assets_reference"),
        CheckConstraint("json_valid(metadata_json)", name="ck_content_assets_json"),
    )


class RawImportRecord(ContentBase):
    __tablename__ = "content_raw_imports"
    import_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    provenance_json: Mapped[str] = mapped_column(Text, nullable=False)
    extensions_json: Mapped[str] = mapped_column(Text, nullable=False)
    original_payload: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    __table_args__ = (
        CheckConstraint("length(content_hash) = 64", name="ck_content_raw_imports_hash"),
        CheckConstraint("json_valid(provenance_json)", name="ck_content_raw_imports_provenance"),
        CheckConstraint("json_valid(extensions_json)", name="ck_content_raw_imports_extensions"),
    )


class AcceptedImportBaselineRecord(ContentBase):
    __tablename__ = "content_import_baselines"
    content_kind: Mapped[str] = mapped_column(String(32), primary_key=True)
    content_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    accepted_semantic_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    accepted_at_utc: Mapped[datetime] = mapped_column(UTCTimestampStorage(), nullable=False)
    source_package_id: Mapped[UUID | None] = mapped_column(UUIDStorage(), nullable=True)
    source_package_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    __table_args__ = (
        CheckConstraint(
            "content_kind IN ('character_definition','world_content',"
            "'lore_entry','lore_collection')",
            name="ck_import_baseline_kind",
        ),
        CheckConstraint(
            "length(accepted_semantic_hash) = 64 AND accepted_semantic_hash NOT GLOB '*[^0-9a-f]*'",
            name="ck_import_baseline_hash",
        ),
        CheckConstraint(
            "source_package_hash IS NULL OR (length(source_package_hash) = 64 "
            "AND source_package_hash NOT GLOB '*[^0-9a-f]*')",
            name="ck_import_baseline_source_hash",
        ),
    )


class AssetBlobBindingRecord(ContentBase):
    __tablename__ = "content_asset_blob_bindings"
    asset_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), ForeignKey("content_assets.asset_id"), primary_key=True
    )
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (
        CheckConstraint(
            "length(digest) = 64 AND digest NOT GLOB '*[^0-9a-f]*'", name="ck_asset_blob_digest"
        ),
        CheckConstraint("typeof(size) = 'integer' AND size >= 0", name="ck_asset_blob_size"),
    )
