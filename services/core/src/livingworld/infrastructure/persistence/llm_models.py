"""Independent operational accounting metadata; no world/content foreign keys."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
)
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


class LLMBudgetRow(AccountingBase):
    __tablename__ = "llm_budgets"
    __table_args__ = (
        CheckConstraint("revision >= 0", name="ck_llm_budget_revision"),
        CheckConstraint("enabled IN (0,1)", name="ck_llm_budget_enabled"),
        CheckConstraint("mode IN ('off','soft','hard')", name="ck_llm_budget_mode"),
        CheckConstraint("start_utc < end_utc", name="ck_llm_budget_window"),
        CheckConstraint("updated_at_utc >= created_at_utc", name="ck_llm_budget_audit_time"),
        CheckConstraint(
            "model_id IS NULL OR provider_id IS NOT NULL", name="ck_llm_budget_model_scope"
        ),
        Index("ix_llm_budget_enabled", "enabled", "mode", "start_utc", "end_utc"),
    )
    budget_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean)
    mode: Mapped[str] = mapped_column(String(8))
    currency: Mapped[str] = mapped_column(String(3))
    limit_amount: Mapped[Decimal] = mapped_column(DecimalTextStorage())
    start_utc: Mapped[datetime] = mapped_column(UTCTimestampStorage())
    end_utc: Mapped[datetime] = mapped_column(UTCTimestampStorage())
    purpose: Mapped[str | None] = mapped_column(Text)
    provider_id: Mapped[str | None] = mapped_column(Text)
    model_id: Mapped[str | None] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer)
    created_at_utc: Mapped[datetime] = mapped_column(UTCTimestampStorage())
    updated_at_utc: Mapped[datetime] = mapped_column(UTCTimestampStorage())


class LLMBudgetReservationRow(AccountingBase):
    __tablename__ = "llm_budget_reservations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["invocation_id", "attempt_ordinal"],
            ["llm_attempts.invocation_id", "llm_attempts.attempt_ordinal"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("attempt_ordinal >= 1", name="ck_llm_reservation_ordinal"),
        CheckConstraint(
            "status IN ('held','held_uncertain','settled','released',"
            "'bound_violation','integrity_degraded')",
            name="ck_llm_reservation_status",
        ),
        CheckConstraint(
            "(status = 'settled' AND settled_amount IS NOT NULL) OR "
            "(status != 'settled' AND settled_amount IS NULL)",
            name="ck_llm_reservation_settlement",
        ),
        CheckConstraint("updated_at_utc >= created_at_utc", name="ck_llm_reservation_audit_time"),
        Index("ix_llm_reservation_attempt", "invocation_id", "attempt_ordinal"),
    )
    budget_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), ForeignKey("llm_budgets.budget_id", ondelete="RESTRICT"), primary_key=True
    )
    invocation_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    attempt_ordinal: Mapped[int] = mapped_column(Integer, primary_key=True)
    currency: Mapped[str] = mapped_column(String(3))
    reserved_amount: Mapped[Decimal] = mapped_column(DecimalTextStorage())
    status: Mapped[str] = mapped_column(String(24))
    settled_amount: Mapped[Decimal | None] = mapped_column(DecimalTextStorage())
    created_at_utc: Mapped[datetime] = mapped_column(UTCTimestampStorage())
    updated_at_utc: Mapped[datetime] = mapped_column(UTCTimestampStorage())
    policy_snapshot: Mapped[dict] = mapped_column(NullableAccountingJSON())
    bound_evidence: Mapped[dict] = mapped_column(NullableAccountingJSON())
