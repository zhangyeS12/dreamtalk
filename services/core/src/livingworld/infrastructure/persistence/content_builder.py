"""Durable single-dispatch builder receipts, independently scoped to a World."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column

from livingworld.application.content_builder import BuilderError
from livingworld.domain.content.serialization import parse_json, stable_json
from livingworld.infrastructure.persistence.models import Base
from livingworld.infrastructure.persistence.types import UTCTimestampStorage, UUIDStorage


class ContentBuilderJobRecord(Base):
    __tablename__ = "content_builder_jobs"
    __table_args__ = (
        CheckConstraint(
            "state IN ('searching','generating','ready','failed','interrupted')",
            name="ck_builder_job_state",
        ),
        CheckConstraint("length(fingerprint) = 64", name="ck_builder_job_fingerprint"),
        CheckConstraint(
            "result_json IS NULL OR json_valid(result_json)", name="ck_builder_job_result"
        ),
    )
    request_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    world_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), ForeignKey("worlds.world_id"), nullable=False
    )
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    result_json: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(UTCTimestampStorage(), nullable=False)


class SqlAlchemyBuilderStore:
    def __init__(self, sessions):
        self._sessions = sessions

    async def claim(self, world_id, request_id, fingerprint):
        async with self._sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            existing = await session.get(ContentBuilderJobRecord, request_id)
            if existing is not None:
                if existing.world_id != world_id.value or existing.fingerprint != fingerprint:
                    raise BuilderError("builder_request_conflict")
                return False
            session.add(
                ContentBuilderJobRecord(
                    request_id=request_id,
                    world_id=world_id.value,
                    fingerprint=fingerprint,
                    state="searching",
                    created_at=datetime.now(UTC),
                )
            )
            return True

    async def read(self, world_id, request_id):
        async with self._sessions() as session:
            row = await session.scalar(
                select(ContentBuilderJobRecord).where(
                    ContentBuilderJobRecord.request_id == request_id,
                    ContentBuilderJobRecord.world_id == world_id.value,
                )
            )
            if row is None:
                return None
            return {
                "request_id": str(row.request_id),
                "state": row.state,
                "error": row.error,
                "result": parse_json(row.result_json) if row.result_json else None,
            }

    async def update(self, world_id, request_id, state, *, result=None, error=None):
        async with self._sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            row = await session.get(ContentBuilderJobRecord, request_id)
            if row is None or row.world_id != world_id.value:
                raise BuilderError("builder_job_not_found")
            row.state, row.error = state, error
            if result is not None:
                row.result_json = stable_json(result)
