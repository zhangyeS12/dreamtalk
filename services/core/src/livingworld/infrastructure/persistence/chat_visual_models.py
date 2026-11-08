"""World-scoped chat backgrounds and character expression bindings."""

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from livingworld.infrastructure.persistence.models import Base
from livingworld.infrastructure.persistence.types import UUIDStorage


class ChatVisualBackgroundRecord(Base):
    __tablename__ = "chat_visual_backgrounds"
    world_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), ForeignKey("worlds.world_id"), primary_key=True
    )
    common_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    __table_args__ = (
        ForeignKeyConstraint(
            ["world_id", "common_digest"],
            ["world_cover_images.world_id", "world_cover_images.digest"],
        ),
        CheckConstraint(
            "common_digest IS NULL OR length(common_digest) = 64",
            name="ck_chat_visual_common_digest",
        ),
    )


class ChatCharacterBackgroundRecord(Base):
    __tablename__ = "chat_character_backgrounds"
    world_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), ForeignKey("worlds.world_id"), primary_key=True
    )
    root_import_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(["root_import_id"], ["world_content_imports.import_id"]),
        ForeignKeyConstraint(
            ["world_id", "digest"],
            ["world_cover_images.world_id", "world_cover_images.digest"],
        ),
        CheckConstraint("length(digest) = 64", name="ck_chat_visual_character_digest"),
    )


class ChatCharacterExpressionRecord(Base):
    __tablename__ = "chat_character_expressions"
    world_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), ForeignKey("worlds.world_id"), primary_key=True
    )
    root_import_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    expression: Mapped[str] = mapped_column(String(16), primary_key=True)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(["root_import_id"], ["world_content_imports.import_id"]),
        ForeignKeyConstraint(
            ["world_id", "digest"],
            ["world_cover_images.world_id", "world_cover_images.digest"],
        ),
        CheckConstraint(
            "expression IN ("
            "'neutral','joy','content','sad','angry','surprised','scared',"
            "'disgusted','confused','love','embarrassed','thinking')",
            name="ck_chat_visual_expression",
        ),
        CheckConstraint("length(digest) = 64", name="ck_chat_visual_expression_digest"),
        Index("ix_chat_character_expressions_world_root", "world_id", "root_import_id"),
    )
