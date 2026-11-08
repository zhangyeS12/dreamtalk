"""Explicit deletion receipts; group history remains owned by its original participants."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKeyConstraint, Text
from sqlalchemy.orm import Mapped, mapped_column

from livingworld.infrastructure.persistence.models import Base
from livingworld.infrastructure.persistence.types import UTCTimestampStorage, UUIDStorage


class GroupDissolutionRecord(Base):
    __tablename__ = "group_dissolutions"

    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    conversation_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    dissolved_at: Mapped[datetime] = mapped_column(UTCTimestampStorage(), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["world_id", "conversation_id"],
            ["chat_conversations.world_id", "chat_conversations.conversation_id"],
        ),
    )


class WorldDeletionRecord(Base):
    __tablename__ = "world_deletions"

    # No foreign key: this minimal receipt survives removal of the world itself.
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    deleted_at: Mapped[datetime] = mapped_column(UTCTimestampStorage(), nullable=False)
    pending_assets_json: Mapped[str] = mapped_column(Text, nullable=False)


WORLD_DELETE_TRIGGER = (
    "CREATE TRIGGER world_events_no_delete BEFORE DELETE ON world_events "
    "WHEN NOT EXISTS (SELECT 1 FROM world_deletions WHERE world_id = OLD.world_id) "
    "BEGIN SELECT RAISE(ABORT, 'world_event_immutable'); END"
)
WORLD_RECREATE_TRIGGER = (
    "CREATE TRIGGER worlds_no_recreate BEFORE INSERT ON worlds "
    "WHEN EXISTS (SELECT 1 FROM world_deletions WHERE world_id = NEW.world_id) "
    "BEGIN SELECT RAISE(ABORT, 'world_deleted'); END"
)
