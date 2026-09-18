"""Local estimated-spend policy; contains no provider or world capabilities."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from livingworld.application.llm import (
    InvocationId,
    LLMContractError,
    LLMPurpose,
    LLMRequest,
    ModelRef,
    ProviderId,
)
from livingworld.application.llm_accounting import AttemptAccountingSink, AttemptStart
from livingworld.application.llm_pricing import Money
from livingworld.domain.values import Revision, utc_timestamp


@dataclass(frozen=True, slots=True)
class BudgetId:
    value: UUID

    def __post_init__(self):
        if not isinstance(self.value, UUID):
            raise LLMContractError("invalid_budget_id")


class BudgetMode(StrEnum):
    OFF = "off"
    SOFT = "soft"
    HARD = "hard"


class BudgetReason(StrEnum):
    EXCEEDED = "budget_exceeded"
    UNVERIFIABLE = "budget_unverifiable"
    STATE_UNCERTAIN = "budget_state_uncertain"
    CURRENCY_UNSUPPORTED = "budget_currency_unsupported"
    INTEGRITY_DEGRADED = "budget_integrity_degraded"


class BudgetAdmissionError(RuntimeError):
    """Local denial, never a provider error and never eligible for provider retry."""

    def __init__(self, reason: BudgetReason, budget_id: BudgetId):
        self.reason, self.budget_id = reason, budget_id
        super().__init__(reason.value)


class BudgetIntegrityError(RuntimeError):
    """Safe operational condition after dispatch; original outcome must survive."""

    def __init__(self, event="budget_finalization_incomplete"):
        if event not in {"budget_finalization_incomplete", "budget_bound_violation"}:
            raise LLMContractError("invalid_budget_integrity_event")
        self.event = event
        super().__init__(event)


@dataclass(frozen=True, slots=True, kw_only=True)
class BudgetPolicy:
    budget_id: BudgetId
    enabled: bool
    mode: BudgetMode
    limit: Money
    start_utc: datetime
    end_utc: datetime
    created_at_utc: datetime
    updated_at_utc: datetime
    purpose: LLMPurpose | None = None
    provider: ProviderId | None = None
    model: ModelRef | None = None
    revision: Revision = Revision()

    def __post_init__(self):
        for value, type_ in (
            (self.budget_id, BudgetId),
            (self.mode, BudgetMode),
            (self.limit, Money),
            (self.revision, Revision),
        ):
            if not isinstance(value, type_):
                raise LLMContractError("invalid_budget_policy")
        if type(self.enabled) is not bool:
            raise LLMContractError("invalid_budget_enabled")
        for name in ("start_utc", "end_utc", "created_at_utc", "updated_at_utc"):
            object.__setattr__(self, name, utc_timestamp(getattr(self, name), name))
        if self.start_utc >= self.end_utc or self.updated_at_utc < self.created_at_utc:
            raise LLMContractError("invalid_budget_interval")
        for value, type_ in (
            (self.purpose, LLMPurpose),
            (self.provider, ProviderId),
            (self.model, ModelRef),
        ):
            if value is not None and not isinstance(value, type_):
                raise LLMContractError("invalid_budget_scope")
        if (
            self.provider is not None
            and self.model is not None
            and self.provider != self.model.provider_id
        ):
            raise LLMContractError("conflicting_budget_provider")
        if self.model is not None and self.provider is None:
            object.__setattr__(self, "provider", self.model.provider_id)

    def matches(self, start: AttemptStart):
        return (
            self.start_utc <= start.started_at_utc < self.end_utc
            and (self.purpose is None or self.purpose == start.purpose)
            and (self.provider is None or self.provider == start.requested_model.provider_id)
            and (self.model is None or self.model == start.requested_model)
        )


class BoundGuarantee(StrEnum):
    HARD_UPPER_BOUND = "hard_upper_bound"
    ESTIMATE_ONLY = "estimate_only"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class UsageUpperBound:
    input_tokens: int
    output_tokens: int
    guarantee: BoundGuarantee = BoundGuarantee.HARD_UPPER_BOUND

    def __post_init__(self):
        if any(
            type(v) is not int or not 0 <= v <= 2**63 - 1
            for v in (self.input_tokens, self.output_tokens)
        ):
            raise LLMContractError("invalid_usage_bound")
        if not isinstance(self.guarantee, BoundGuarantee):
            raise LLMContractError("invalid_bound_guarantee")


class PreflightUsageBounder(Protocol):
    def bound(self, request: LLMRequest) -> UsageUpperBound | None: ...


@dataclass(frozen=True, slots=True)
class ModelUsageLimits:
    max_billable_input_tokens: int
    max_output_tokens: int

    def __post_init__(self):
        UsageUpperBound(self.max_billable_input_tokens, self.max_output_tokens)
        if self.max_output_tokens < 1:
            raise LLMContractError("invalid_model_output_limit")


class ModelLimitUsageBounder:
    """Explicit trusted configuration, including the adapter's billable cap semantics."""

    def __init__(self, limits):
        self._limits = dict(limits)
        if any(
            not isinstance(k, ModelRef) or not isinstance(v, ModelUsageLimits)
            for k, v in self._limits.items()
        ):
            raise LLMContractError("invalid_model_limits")

    def bound(self, request):
        limits = self._limits.get(request.model)
        if limits is None:
            return None
        cap = request.max_output_tokens
        return UsageUpperBound(
            limits.max_billable_input_tokens,
            cap
            if cap is not None and cap <= limits.max_output_tokens
            else limits.max_output_tokens,
        )


class ReservationStatus(StrEnum):
    HELD = "held"
    HELD_UNCERTAIN = "held_uncertain"
    SETTLED = "settled"
    RELEASED = "released"
    BOUND_VIOLATION = "bound_violation"
    INTEGRITY_DEGRADED = "integrity_degraded"


@dataclass(frozen=True, slots=True)
class BudgetReservation:
    policy: BudgetPolicy
    invocation_id: InvocationId
    attempt_ordinal: int
    reserved: Money
    status: ReservationStatus
    created_at_utc: datetime
    updated_at_utc: datetime
    settled: Money | None = None


@dataclass(frozen=True, slots=True)
class BudgetView:
    policy: BudgetPolicy
    known_estimated_spend: Money
    held: Money
    remaining: Money | None
    has_unbounded_exposure: bool
    currency_unsupported: bool
    integrity_degraded: bool


@dataclass(frozen=True, slots=True)
class BudgetDiagnostic:
    invocation_id: InvocationId
    attempt_ordinal: int
    event: str
    budget_id: BudgetId | None = None

    def __post_init__(self):
        if (
            not isinstance(self.invocation_id, InvocationId)
            or type(self.attempt_ordinal) is not int
            or self.attempt_ordinal < 1
        ):
            raise LLMContractError("invalid_budget_diagnostic_identity")
        if self.event not in {
            *(r.value for r in BudgetReason),
            "budget_bound_violation",
            "budget_finalization_incomplete",
        }:
            raise LLMContractError("invalid_budget_diagnostic")


class BudgetedAttemptAccountingSink(AttemptAccountingSink, Protocol):
    async def admit(self, start: AttemptStart, request: LLMRequest) -> None: ...


class BudgetRepository(Protocol):
    async def put_policy(
        self, policy: BudgetPolicy, expected_revision: Revision | None
    ) -> None: ...
    async def view(self, budget_id: BudgetId) -> BudgetView: ...
    async def reservations(self, budget_id: BudgetId) -> tuple[BudgetReservation, ...]: ...
