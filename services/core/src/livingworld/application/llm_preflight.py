"""Conservative token-rate cost bounds, separate from historical exact pricing."""

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_CEILING, Decimal, localcontext

from livingworld.application.llm import ModelRef
from livingworld.application.llm_budget import UsageUpperBound
from livingworld.application.llm_pricing import (
    QUANTUM,
    Meter,
    Money,
    PricingConfigurationError,
    PricingSchedule,
    _label,
)
from livingworld.domain.values import utc_timestamp


@dataclass(frozen=True, slots=True)
class RequestedPricingEnvelope:
    """Trusted exhaustive reachable targets, not a dynamic Model Registry."""

    requested: ModelRef
    targets: tuple[ModelRef, ...]
    processing_tier: str | None = None

    def __post_init__(self):
        if (
            not isinstance(self.requested, ModelRef)
            or type(self.targets) is not tuple
            or not self.targets
            or len(set(self.targets)) != len(self.targets)
            or any(
                not isinstance(t, ModelRef) or t.provider_id != self.requested.provider_id
                for t in self.targets
            )
        ):
            raise PricingConfigurationError("invalid_pricing_envelope")
        if self.processing_tier is not None:
            _label(self.processing_tier)


@dataclass(frozen=True, slots=True)
class MoneyUpperBound:
    requested: ModelRef
    usage: UsageUpperBound
    money: Money
    at_utc: datetime
    schedules: tuple[PricingSchedule, ...]
    processing_tier: str | None

    def __post_init__(self):
        if (
            not isinstance(self.requested, ModelRef)
            or not isinstance(self.usage, UsageUpperBound)
            or not isinstance(self.money, Money)
            or type(self.schedules) is not tuple
            or not self.schedules
            or any(
                not isinstance(s, PricingSchedule)
                or s.currency != self.money.currency
                or s.model.provider_id != self.requested.provider_id
                for s in self.schedules
            )
        ):
            raise PricingConfigurationError("invalid_money_upper_bound")
        object.__setattr__(self, "at_utc", utc_timestamp(self.at_utc, "bound_at"))
        if self.processing_tier is not None:
            _label(self.processing_tier)


class PreflightPricingEngine:
    def __init__(self, catalog, *, envelopes=()):
        self.catalog = catalog
        envelopes = tuple(envelopes)
        if any(not isinstance(e, RequestedPricingEnvelope) for e in envelopes):
            raise PricingConfigurationError("invalid_pricing_envelope")
        self._envelopes = {e.requested: e for e in envelopes}
        if len(self._envelopes) != len(envelopes):
            raise PricingConfigurationError("duplicate_pricing_envelope")

    def bound(self, *, requested, usage, at):
        """None means unverifiable. Never select a cheap ambiguous alias schedule."""
        at = utc_timestamp(at, "bound_at")
        if not isinstance(usage, UsageUpperBound):
            return None
        envelope = self._envelopes.get(requested)
        targets = envelope.targets if envelope else (requested,)
        tier = envelope.processing_tier if envelope else None
        totals, schedules = [], []
        for target in targets:
            found = self.catalog.schedules(target, None, at)
            if len(found) != 1:
                return None
            schedule = found[0]
            # A catalog alias is not proof that this is its only reachable outcome.
            if schedule.model != target:
                return None
            maximum = self._schedule_bound(schedule, usage, at, tier)
            if maximum is None:
                return None
            schedules.append(schedule)
            totals.append(Money(schedule.currency, maximum))
        if len({m.currency for m in totals}) != 1:
            return None
        return MoneyUpperBound(
            requested, usage, max(totals, key=lambda m: m.amount), at, tuple(schedules), tier
        )

    @staticmethod
    def _schedule_bound(schedule, usage, at, tier):
        variants = []
        for v in schedule.variants:
            if v.utc_windows and not any(w.matches(at) for w in v.utc_windows):
                continue
            if v.processing_tier is not None:
                if tier is None:
                    return None
                if v.processing_tier != tier:
                    continue
            lo, hi = (
                v.input_min or 0,
                min(
                    usage.input_tokens,
                    (v.input_max_exclusive - 1)
                    if v.input_max_exclusive is not None
                    else usage.input_tokens,
                ),
            )
            if lo <= hi:
                variants.append((lo, hi, v))
        # All possible integral input counts must have exactly one applicable rule.
        cursor = 0
        for lo, hi, _v in sorted(variants, key=lambda item: item[0]):
            if lo != cursor:
                return None
            cursor = hi + 1
        if cursor != usage.input_tokens + 1:
            return None
        amounts = []
        with localcontext() as context:
            context.prec = 100
            for _lo, hi, variant in variants:
                groups = [[], []]
                for rate in variant.rates:
                    group = (
                        0
                        if rate.meter
                        in {
                            Meter.INPUT,
                            Meter.UNCACHED_INPUT,
                            Meter.CACHED_INPUT,
                            Meter.CACHE_WRITE_INPUT,
                        }
                        else 1
                    )
                    groups[group].append(rate)
                total = Decimal("0")
                for rates, cap in zip(groups, (hi, usage.output_tokens), strict=True):
                    if rates:
                        largest = max(r.rate / Decimal(r.unit_tokens) for r in rates)
                        value = (Decimal(cap) * largest).quantize(QUANTUM, rounding=ROUND_CEILING)
                        # Partition rounding may exceed the rounded aggregate linear maximum.
                        total += value + (len(rates) * QUANTUM if len(rates) > 1 else Decimal("0"))
                amounts.append(total)
        return max(amounts) if amounts else None
