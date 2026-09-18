"""Independent operational accounting metadata; no world/content foreign keys."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from livingworld.infrastructure.persistence.types import (
    DecimalTextStorage,
    JSONTextStorage,
    UTCTimestampStorage,
    UUIDStorage,
)


class AccountingBase(DeclarativeBase):
    pass


class NullableAccountingJSON(JSONTextStorage):
    """SQL NULL means lifecycle facts do not yet exist, distinct from JSON null."""

    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else super().process_bind_param(value, dialect)

    def process_result_value(self, value, dialect):
        return None if value is None else super().process_result_value(value, dialect)


class LLMAttemptRow(AccountingBase):
    __tablename__ = "llm_attempts"
    __table_args__ = (
        CheckConstraint("attempt_ordinal >= 1", name="ck_llm_attempt_ordinal"),
        CheckConstraint(
            "invocation_outcome IS NULL OR (facts IS NOT NULL AND "
            "invocation_outcome IN ('success','failed','cancelled','local_error'))",
            name="ck_llm_invocation_terminal",
        ),
        CheckConstraint(
            "outcome IN ('incomplete','success','failed','cancelled','local_error')",
            name="ck_llm_attempt_outcome",
        ),
        CheckConstraint(
            "cost_status IN "
            "('priced','price_unknown','usage_unknown','usage_partial','pricing_context_incomplete"
            "','possibly_billed_unknown','not_dispatched')",
            name="ck_llm_attempt_cost_status",
        ),
        CheckConstraint(
            "(outcome = 'incomplete' AND finished_at_utc IS NULL AND facts IS NULL AND "
            "cost_status = 'possibly_billed_unknown') OR (outcome != 'incomplete' AND "
            "finished_at_utc IS NOT NULL AND facts IS NOT NULL)",
            name="ck_llm_attempt_lifecycle",
        ),
        CheckConstraint(
            "(cost_status = 'priced' AND currency IS NOT NULL AND estimated_cost IS NOT NULL AND "
            "price_snapshot IS NOT NULL) OR (cost_status != 'priced' AND currency IS NULL AND "
            "estimated_cost IS NULL AND price_snapshot IS NULL)",
            name="ck_llm_attempt_estimate",
        ),
        Index("ix_llm_attempt_time", "started_at_utc"),
        Index("ix_llm_attempt_purpose", "purpose", "started_at_utc"),
        Index("ix_llm_attempt_model", "provider_id", "requested_model", "started_at_utc"),
    )
    invocation_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    attempt_ordinal: Mapped[int] = mapped_column(Integer, primary_key=True)
    purpose: Mapped[str] = mapped_column(Text)
    provider_id: Mapped[str] = mapped_column(Text)
    requested_model: Mapped[str] = mapped_column(Text)
    reported_model: Mapped[str | None] = mapped_column(Text)
    started_at_utc: Mapped[datetime] = mapped_column(UTCTimestampStorage())
    finished_at_utc: Mapped[datetime | None] = mapped_column(UTCTimestampStorage())
    outcome: Mapped[str] = mapped_column(String(16))
    invocation_outcome: Mapped[str | None] = mapped_column(String(16))
    facts: Mapped[dict | None] = mapped_column(NullableAccountingJSON())
    cost_status: Mapped[str] = mapped_column(String(32))
    currency: Mapped[str | None] = mapped_column(String(3))
    estimated_cost: Mapped[Decimal | None] = mapped_column(DecimalTextStorage())
    price_snapshot: Mapped[dict | None] = mapped_column(NullableAccountingJSON())
