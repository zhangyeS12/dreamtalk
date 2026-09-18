"""Explicit effective-dated reference data and deterministic estimated money."""

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from enum import StrEnum
from typing import Protocol

from livingworld.application.llm import LLMContractError, ModelRef
from livingworld.domain.values import utc_timestamp

QUANTUM = Decimal("0.000000001")


class PricingConfigurationError(ValueError):
    """Safe configuration labels only; never include reference data or DB errors."""


class CostStatus(StrEnum):
    PRICED = "priced"
    PRICE_UNKNOWN = "price_unknown"
    USAGE_UNKNOWN = "usage_unknown"
    USAGE_PARTIAL = "usage_partial"
    PRICING_CONTEXT_INCOMPLETE = "pricing_context_incomplete"
    POSSIBLY_BILLED_UNKNOWN = "possibly_billed_unknown"
    NOT_DISPATCHED = "not_dispatched"


class Meter(StrEnum):
    INPUT = "input_tokens"
    UNCACHED_INPUT = "uncached_input_tokens"
    CACHED_INPUT = "cached_input_tokens"
    CACHE_WRITE_INPUT = "cache_write_input_tokens"
    OUTPUT = "output_tokens"
    NON_REASONING_OUTPUT = "non_reasoning_output_tokens"
    REASONING_OUTPUT = "reasoning_output_tokens"


def _label(value):
    if (
        type(value) is not str
        or not 1 <= len(value) <= 128
        or any(not (c.isascii() and (c.isalnum() or c in "_.:-")) for c in value)
    ):
        raise LLMContractError("invalid_accounting_label")


def _amount(value):
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise PricingConfigurationError("invalid_money")
    if value.as_tuple().exponent < -9 or len(value.as_tuple().digits) > 40:
        raise PricingConfigurationError("money_precision_exceeded")


@dataclass(frozen=True, slots=True)
class Money:
    currency: str
    amount: Decimal

    def __post_init__(self):
        if (
            type(self.currency) is not str
            or len(self.currency) != 3
            or not (self.currency.isascii() and self.currency.isalpha() and self.currency.isupper())
        ):
            raise PricingConfigurationError("invalid_currency")
        _amount(self.amount)


@dataclass(frozen=True, slots=True)
class RateLine:
    meter: Meter
    rate: Decimal
    unit_tokens: int = 1_000_000

    def __post_init__(self):
        if not isinstance(self.meter, Meter):
            raise PricingConfigurationError("invalid_meter")
        _amount(self.rate)
        if type(self.unit_tokens) is not int or not 1 <= self.unit_tokens <= 2**63 - 1:
            raise PricingConfigurationError("invalid_rate_unit")


@dataclass(frozen=True, slots=True)
class UTCWindow:
    """Half-open minutes in a UTC day; weekdays use Monday=0. No local timezone."""

    weekdays: tuple[int, ...]
    start_minute: int
    end_minute: int

    def __post_init__(self):
        if (
            type(self.weekdays) is not tuple
            or not self.weekdays
            or any(type(day) is not int or not 0 <= day <= 6 for day in self.weekdays)
            or len(set(self.weekdays)) != len(self.weekdays)
        ):
            raise PricingConfigurationError("invalid_utc_weekdays")
        if (
            type(self.start_minute) is not int
            or type(self.end_minute) is not int
            or not (0 <= self.start_minute < self.end_minute <= 1440)
        ):
            raise PricingConfigurationError("invalid_utc_window")

    def matches(self, timestamp):
        return timestamp.weekday() in self.weekdays and (
            self.start_minute <= timestamp.hour * 60 + timestamp.minute < self.end_minute
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class PricingVariant:
    variant_id: str
    rates: tuple[RateLine, ...]
    input_min: int | None = None
    input_max_exclusive: int | None = None
    processing_tier: str | None = None
    utc_windows: tuple[UTCWindow, ...] = ()

    def __post_init__(self):
        _label(self.variant_id)
        if (
            type(self.rates) is not tuple
            or not self.rates
            or any(not isinstance(rate, RateLine) for rate in self.rates)
            or len({rate.meter for rate in self.rates}) != len(self.rates)
        ):
            raise PricingConfigurationError("invalid_rate_lines")
        meters = {rate.meter for rate in self.rates}
        if (
            Meter.INPUT in meters
            and meters & {Meter.UNCACHED_INPUT, Meter.CACHED_INPUT, Meter.CACHE_WRITE_INPUT}
            or Meter.OUTPUT in meters
            and meters & {Meter.REASONING_OUTPUT, Meter.NON_REASONING_OUTPUT}
        ):
            raise PricingConfigurationError("overlapping_billing_meters")
        for value in (self.input_min, self.input_max_exclusive):
            if value is not None and (type(value) is not int or not 0 <= value <= 2**63 - 1):
                raise PricingConfigurationError("invalid_input_threshold")
        if (
            self.input_min is not None
            and self.input_max_exclusive is not None
            and self.input_min >= self.input_max_exclusive
        ):
            raise PricingConfigurationError("invalid_input_threshold")
        if self.processing_tier is not None:
            _label(self.processing_tier)
        if type(self.utc_windows) is not tuple or any(
            not isinstance(w, UTCWindow) for w in self.utc_windows
        ):
            raise PricingConfigurationError("invalid_utc_windows")

    def match(self, timestamp, usage, tier):
        """False=no match; None=required factual context missing; True=compatible."""
        if self.utc_windows and not any(w.matches(timestamp) for w in self.utc_windows):
            return False
        missing = False
        if self.processing_tier is not None:
            if tier is None:
                missing = True
            elif tier != self.processing_tier:
                return False
        if self.input_min is not None or self.input_max_exclusive is not None:
            if usage.input_tokens is None:
                missing = True
            elif (
                self.input_min is not None
                and usage.input_tokens < self.input_min
                or self.input_max_exclusive is not None
                and usage.input_tokens >= self.input_max_exclusive
            ):
                return False
        return None if missing else True


@dataclass(frozen=True, slots=True, kw_only=True)
class PricingSchedule:
    schedule_id: str
    model: ModelRef
    currency: str
    effective_from: datetime
    variants: tuple[PricingVariant, ...]
    source_label: str
    effective_until: datetime | None = None

    def __post_init__(self):
        _label(self.schedule_id)
        _label(self.source_label)
        if not isinstance(self.model, ModelRef):
            raise PricingConfigurationError("invalid_schedule_model")
        Money(self.currency, Decimal("0"))
        object.__setattr__(
            self, "effective_from", utc_timestamp(self.effective_from, "pricing_from")
        )
        if self.effective_until is not None:
            object.__setattr__(
                self, "effective_until", utc_timestamp(self.effective_until, "pricing_until")
            )
            if self.effective_until <= self.effective_from:
                raise PricingConfigurationError("invalid_pricing_interval")
        if (
            type(self.variants) is not tuple
            or not self.variants
            or any(not isinstance(v, PricingVariant) for v in self.variants)
            or len({v.variant_id for v in self.variants}) != len(self.variants)
        ):
            raise PricingConfigurationError("invalid_pricing_variants")


@dataclass(frozen=True, slots=True)
class ModelAlias:
    alias: ModelRef
    target: ModelRef
    allow_requested_fallback: bool = False

    def __post_init__(self):
        if (
            not isinstance(self.alias, ModelRef)
            or not isinstance(self.target, ModelRef)
            or self.alias.provider_id != self.target.provider_id
            or type(self.allow_requested_fallback) is not bool
        ):
            raise PricingConfigurationError("invalid_pricing_alias")


class PricingCatalog(Protocol):
    def schedules(
        self, requested: ModelRef, reported: ModelRef | None, at: datetime
    ) -> tuple[PricingSchedule, ...]: ...


class InMemoryPricingCatalog:
    """Trusted explicitly supplied data; no default catalog, network or model heuristics."""

    def __init__(self, schedules=(), aliases=()):
        self._schedules, self._aliases = tuple(schedules), tuple(aliases)
        if (
            any(not isinstance(s, PricingSchedule) for s in self._schedules)
            or any(not isinstance(a, ModelAlias) for a in self._aliases)
            or len({a.alias for a in self._aliases}) != len(self._aliases)
        ):
            raise PricingConfigurationError("invalid_pricing_catalog")

    def schedules(self, requested, reported, at):
        at = utc_timestamp(at, "pricing_at")

        def matching(model):
            target = next((a.target for a in self._aliases if a.alias == model), model)
            return tuple(
                s
                for s in self._schedules
                if s.model == target
                and s.effective_from <= at
                and (s.effective_until is None or at < s.effective_until)
            )

        if reported is not None:
            found = matching(reported)
            if found:
                return found
            if not any(a.alias == requested and a.allow_requested_fallback for a in self._aliases):
                return ()
        return matching(requested)


@dataclass(frozen=True, slots=True)
class PriceLineItem:
    rate_line: RateLine
    quantity: int
    subtotal: Money

    def __post_init__(self):
        if (
            not isinstance(self.rate_line, RateLine)
            or not isinstance(self.subtotal, Money)
            or type(self.quantity) is not int
            or not 0 <= self.quantity <= 2**63 - 1
        ):
            raise PricingConfigurationError("invalid_price_line_item")


@dataclass(frozen=True, slots=True)
class PriceSnapshot:
    schedule: PricingSchedule
    selected_variant_id: str
    priced_at_utc: datetime
    input_tokens: int | None
    processing_tier: str | None
    line_items: tuple[PriceLineItem, ...]
    estimated_total: Money

    def __post_init__(self):
        if not isinstance(self.schedule, PricingSchedule) or not isinstance(
            self.estimated_total, Money
        ):
            raise PricingConfigurationError("invalid_price_snapshot")
        object.__setattr__(self, "priced_at_utc", utc_timestamp(self.priced_at_utc, "priced_at"))
        variant = next(
            (v for v in self.schedule.variants if v.variant_id == self.selected_variant_id), None
        )
        if (
            variant is None
            or type(self.line_items) is not tuple
            or any(not isinstance(i, PriceLineItem) for i in self.line_items)
        ):
            raise PricingConfigurationError("invalid_snapshot_variant")
        if (
            tuple(item.rate_line for item in self.line_items) != variant.rates
            or any(item.subtotal.currency != self.schedule.currency for item in self.line_items)
            or self.estimated_total.currency != self.schedule.currency
        ):
            raise PricingConfigurationError("invalid_snapshot_rates")
        with localcontext() as context:
            context.prec = 100
            if (
                sum((i.subtotal.amount for i in self.line_items), Decimal("0"))
                != self.estimated_total.amount
            ):
                raise PricingConfigurationError("invalid_snapshot_total")


@dataclass(frozen=True, slots=True)
class PriceQuote:
    status: CostStatus
    snapshot: PriceSnapshot | None = None

    def __post_init__(self):
        if not isinstance(self.status, CostStatus) or (
            self.status is CostStatus.PRICED
        ) != isinstance(self.snapshot, PriceSnapshot):
            raise PricingConfigurationError("invalid_price_quote")

    @property
    def estimated_cost(self):
        return self.snapshot.estimated_total if self.snapshot else None


class PricingEngine:
    def __init__(self, catalog: PricingCatalog):
        self.catalog = catalog

    def estimate(self, *, requested, reported, at, usage, processing_tier=None):
        at = utc_timestamp(at, "pricing_at")
        if usage is None:
            return PriceQuote(CostStatus.USAGE_UNKNOWN)
        candidates, missing = [], False
        for schedule in self.catalog.schedules(requested, reported, at):
            for variant in schedule.variants:
                match = variant.match(at, usage, processing_tier)
                missing |= match is None
                if match is True:
                    candidates.append((schedule, variant))
        if len(candidates) > 1:
            raise PricingConfigurationError("ambiguous_pricing_variants")
        # Even one match cannot be chosen if another could match unknown context.
        if missing:
            return PriceQuote(CostStatus.PRICING_CONTEXT_INCOMPLETE)
        if not candidates:
            return PriceQuote(CostStatus.PRICE_UNKNOWN)
        schedule, variant = candidates[0]
        items = []
        with localcontext() as context:
            context.prec = 100
            for rate in variant.rates:
                quantity = getattr(usage, rate.meter.value, None)
                if (
                    rate.meter is Meter.NON_REASONING_OUTPUT
                    and usage.output_tokens is not None
                    and usage.reasoning_output_tokens is not None
                ):
                    quantity = usage.output_tokens - usage.reasoning_output_tokens
                if quantity is None:
                    return PriceQuote(CostStatus.PRICING_CONTEXT_INCOMPLETE)
                if not 0 <= quantity <= 2**63 - 1:
                    raise PricingConfigurationError("pricing_quantity_out_of_range")
                subtotal = (Decimal(quantity) * rate.rate / Decimal(rate.unit_tokens)).quantize(
                    QUANTUM, rounding=ROUND_HALF_EVEN
                )
                items.append(PriceLineItem(rate, quantity, Money(schedule.currency, subtotal)))
            total = Money(
                schedule.currency, sum((item.subtotal.amount for item in items), Decimal("0"))
            )
        return PriceQuote(
            CostStatus.PRICED,
            PriceSnapshot(
                schedule,
                variant.variant_id,
                at,
                usage.input_tokens,
                processing_tier,
                tuple(items),
                total,
            ),
        )
