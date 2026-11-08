"""Stable authored identities independent of opening a conversation."""

from uuid import UUID

from sqlalchemy import ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from livingworld.infrastructure.persistence.models import Base, UUIDStorage


class CharacterCardBindingRecord(Base):
    __tablename__ = "character_card_bindings"
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    character_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    root_import_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["world_id", "character_id"], ["characters.world_id", "characters.character_id"]
        ),
        ForeignKeyConstraint(["root_import_id"], ["world_content_imports.import_id"]),
        UniqueConstraint("world_id", "root_import_id", name="uq_character_card_binding_root"),
    )
