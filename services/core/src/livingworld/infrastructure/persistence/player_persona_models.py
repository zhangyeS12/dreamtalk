"""Authored identity metadata, separate from Kernel/replayed relationships."""

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from livingworld.infrastructure.persistence.models import Base
from livingworld.infrastructure.persistence.types import UUIDStorage


class PlayerPersonaRecord(Base):
    __tablename__ = "world_player_personas"
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    player_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    draft_json: Mapped[str] = mapped_column(Text, nullable=False)
    confirmation_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(["world_id", "player_id"], ["players.world_id", "players.player_id"]),
        CheckConstraint("revision > 0", name="ck_player_persona_revision"),
        CheckConstraint("json_valid(draft_json)", name="ck_player_persona_json"),
    )


class PlayerCardRecord(Base):
    __tablename__ = "world_player_cards"
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    player_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    card_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    content_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    reviewed_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    raw_payload: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(["world_id", "player_id"], ["players.world_id", "players.player_id"]),
        CheckConstraint("json_valid(snapshot_json)", name="ck_player_card_json"),
    )
