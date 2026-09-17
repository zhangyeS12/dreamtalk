"""Separate typed content tables; runtime projections contain no authored JSON."""

from uuid import UUID

from sqlalchemy import CheckConstraint, Integer, LargeBinary, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from livingworld.infrastructure.persistence.types import UUIDStorage


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
    # Lore may have no authored title; use distinct checks for its nonempty body in JSON.
    __table_args__ = tuple(
        constraint
        for constraint in root_checks(__tablename__)
        if constraint.name != "ck_content_lore_entries_title"
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
