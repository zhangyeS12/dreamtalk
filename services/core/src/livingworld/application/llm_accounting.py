"""Content-free physical attempt lifecycle and accounting query contracts."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext
from enum import StrEnum
from typing import Protocol

from livingworld.application.llm import (
    DispatchState,
    FinishReason,
    InvocationId,
    LLMContractError,
    LLMErrorCode,
    LLMPurpose,
    LLMUsage,
    ModelRef,
    StreamOutcome,
    _accounting_usage,
)
from livingworld.application.llm_pricing import CostStatus, Money, PriceQuote, _label
from livingworld.domain.values import utc_timestamp


class AccountingInfrastructureError(RuntimeError):
    """Local infrastructure failure, deliberately outside normalized provider errors."""

    def __init__(self):
        super().__init__("accounting_start_persistence_failed")


class AttemptOutcome(StrEnum):
    INCOMPLETE = "incomplete"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    LOCAL_ERROR = "local_error"


class UsageCompleteness(StrEnum):
    FINAL = "final"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


def factual_usage(usage):
    if usage is None:
        return None
    if not isinstance(usage, LLMUsage):
        raise LLMContractError("invalid_accounting_usage")
    safe = _accounting_usage(usage)
    # Arbitrary metadata is not evidence. Empty usage objects remain unknown.
    if (
        not any(
            getattr(safe, field) is not None
            for field in (
                "input_tokens",
                "output_tokens",
                "total_tokens",
                "cached_input_tokens",
                "cache_write_input_tokens",
                "uncached_input_tokens",
                "reasoning_output_tokens",
                "cache_write_5m_input_tokens",
                "cache_write_1h_input_tokens",
            )
        )
        and not safe.details
    ):
        return None
    return safe


@dataclass(frozen=True, slots=True)
class AttemptStart:
    invocation_id: InvocationId
    attempt_ordinal: int
    purpose: LLMPurpose
    requested_model: ModelRef
    started_at_utc: datetime

    def __post_init__(self):
        if (
            not isinstance(self.invocation_id, InvocationId)
            or not isinstance(self.purpose, LLMPurpose)
            or not isinstance(self.requested_model, ModelRef)
        ):
            raise LLMContractError("invalid_attempt_start")
        if type(self.attempt_ordinal) is not int or not 1 <= self.attempt_ordinal <= 2**63 - 1:
            raise LLMContractError("invalid_attempt_ordinal")
        object.__setattr__(
            self, "started_at_utc", utc_timestamp(self.started_at_utc, "attempt_started")
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class AttemptFacts:
    start: AttemptStart
    finished_at_utc: datetime
    latency_ms: int
    outcome: AttemptOutcome
    dispatch_state: DispatchState
    reported_model: ModelRef | None = None
    failure_code: LLMErrorCode | None = None
    finish_reason: FinishReason | None = None
    stream_outcome: StreamOutcome | None = None
    usage: LLMUsage | None = None
    completeness: UsageCompleteness = UsageCompleteness.UNKNOWN
    processing_tier: str | None = None
    provider_request_id: str | None = None

    def __post_init__(self):
        if (
            not isinstance(self.start, AttemptStart)
            or not isinstance(self.outcome, AttemptOutcome)
            or self.outcome is AttemptOutcome.INCOMPLETE
            or not isinstance(self.dispatch_state, DispatchState)
            or not isinstance(self.completeness, UsageCompleteness)
        ):
            raise LLMContractError("invalid_attempt_facts")
        object.__setattr__(
            self, "finished_at_utc", utc_timestamp(self.finished_at_utc, "attempt_finished")
        )
        if type(self.latency_ms) is not int or self.latency_ms < 0:
            raise LLMContractError("invalid_accounting_latency")
        if self.reported_model is not None and (
            not isinstance(self.reported_model, ModelRef)
            or self.reported_model.provider_id != self.start.requested_model.provider_id
        ):
            raise LLMContractError("invalid_reported_model")
        for value, type_ in (
            (self.failure_code, LLMErrorCode),
            (self.finish_reason, FinishReason),
            (self.stream_outcome, StreamOutcome),
        ):
            if value is not None and not isinstance(value, type_):
                raise LLMContractError("invalid_attempt_terminal_semantics")
        object.__setattr__(self, "usage", factual_usage(self.usage))
        if (self.usage is None) != (self.completeness is UsageCompleteness.UNKNOWN):
            raise LLMContractError("invalid_usage_completeness")
        for value in (self.processing_tier, self.provider_request_id):
            if value is not None:
                _label(value)


@dataclass(frozen=True, slots=True)
class AccountingDiagnostic:
    invocation_id: InvocationId
    attempt_ordinal: int
    event: str = "accounting_persistence_incomplete"

    def __post_init__(self):
        if self.event not in {
            "accounting_persistence_incomplete",
            "accounting_start_persistence_failed",
        }:
            raise LLMContractError("invalid_accounting_diagnostic")


class AttemptAccountingSink(Protocol):
    async def start(self, record: AttemptStart) -> None: ...
    async def finalize(self, facts: AttemptFacts) -> None: ...
    async def complete_invocation(
        self, invocation_id: InvocationId, outcome: AttemptOutcome
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class AttemptRecord:
    start: AttemptStart
    facts: AttemptFacts | None
    quote: PriceQuote
    invocation_outcome: AttemptOutcome | None = None

    @property
    def outcome(self):
        return self.facts.outcome if self.facts else AttemptOutcome.INCOMPLETE


@dataclass(frozen=True, slots=True, kw_only=True)
class LedgerQuery:
    invocation_id: InvocationId | None = None
    since_utc: datetime | None = None
    until_utc: datetime | None = None
    provider_id: str | None = None
    model_id: str | None = None
    purpose: LLMPurpose | None = None

    def __post_init__(self):
        for name in ("since_utc", "until_utc"):
            if getattr(self, name) is not None:
                object.__setattr__(self, name, utc_timestamp(getattr(self, name), name))
        if (
            self.since_utc is not None
            and self.until_utc is not None
            and self.since_utc >= self.until_utc
        ):
            raise LLMContractError("invalid_ledger_interval")


class UsageLedger(AttemptAccountingSink, Protocol):
    async def query(self, query: LedgerQuery) -> tuple[AttemptRecord, ...]: ...


@dataclass(frozen=True, slots=True)
class AccountingSummary:
    attempt_count: int
    known_input_tokens: int | None
    known_output_tokens: int | None
    known_estimated_cost: tuple[Money, ...]
    has_partial_usage: bool
    has_unknown_usage: bool
    has_unknown_cost: bool
    has_possible_billing_exposure: bool
    has_incomplete_attempts: bool
    final_outcome: AttemptOutcome | None


def summarize(records: tuple[AttemptRecord, ...]) -> AccountingSummary:
    """Known totals are lower-bound observations, never a confident settled total."""
    inputs, outputs, currencies = [], [], {}
    partial = unknown = cost_unknown = exposure = incomplete = False
    for record in records:
        facts, quote = record.facts, record.quote
        incomplete |= facts is None
        unknown |= (
            facts is None
            or facts.completeness is UsageCompleteness.UNKNOWN
            or facts.usage is not None
            and (facts.usage.input_tokens is None or facts.usage.output_tokens is None)
        )
        partial |= facts is not None and facts.completeness is UsageCompleteness.PARTIAL
        cost_unknown |= (
            quote.estimated_cost is None and quote.status is not CostStatus.NOT_DISPATCHED
        )
        exposure |= (
            facts is None
            or quote.status is CostStatus.POSSIBLY_BILLED_UNKNOWN
            or facts.dispatch_state is not DispatchState.NOT_DISPATCHED
            and quote.estimated_cost is None
        )
        if facts and facts.usage:
            if facts.usage.input_tokens is not None:
                inputs.append(facts.usage.input_tokens)
            if facts.usage.output_tokens is not None:
                outputs.append(facts.usage.output_tokens)
        money = quote.estimated_cost
        if money:
            with localcontext() as context:
                context.prec = 100
                currencies[money.currency] = (
                    currencies.get(money.currency, Decimal("0")) + money.amount
                )
    # Invocation outcome only makes sense when all rows belong to one invocation.
    same_invocation = len({r.start.invocation_id for r in records}) == 1
    last = (
        max(records, key=lambda r: r.start.attempt_ordinal) if records and same_invocation else None
    )
    return AccountingSummary(
        len(records),
        sum(inputs) if inputs else None,
        sum(outputs) if outputs else None,
        tuple(Money(currency, amount) for currency, amount in sorted(currencies.items())),
        partial,
        unknown,
        cost_unknown,
        exposure,
        incomplete,
        (last.invocation_outcome or AttemptOutcome.INCOMPLETE) if last else None,
    )
