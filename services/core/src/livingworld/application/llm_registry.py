"""Immutable operational model configuration, independent of clients and content."""

from dataclasses import dataclass
from enum import StrEnum

from livingworld.application.llm import LLMContractError, ModelCapabilities, ModelRef, ProviderId
from livingworld.application.llm_budget import ModelLimitUsageBounder, ModelUsageLimits
from livingworld.application.llm_preflight import RequestedPricingEnvelope


class AdapterKind(StrEnum):
    OPENAI_COMPATIBLE = "openai-compatible"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"


@dataclass(frozen=True, slots=True)
class RegisteredProvider:
    provider_id: ProviderId
    adapter_kind: AdapterKind

    def __post_init__(self):
        if not isinstance(self.provider_id, ProviderId) or not isinstance(
            self.adapter_kind, AdapterKind
        ):
            raise LLMContractError("invalid_registered_provider")


@dataclass(frozen=True, slots=True, kw_only=True)
class RegisteredModel:
    model: ModelRef
    enabled: bool
    capabilities: ModelCapabilities
    limits: ModelUsageLimits | None = None
    pricing_envelope: RequestedPricingEnvelope | None = None

    def __post_init__(self):
        if (
            not isinstance(self.model, ModelRef)
            or type(self.enabled) is not bool
            or not isinstance(self.capabilities, ModelCapabilities)
        ):
            raise LLMContractError("invalid_registered_model")
        if self.limits is not None and not isinstance(self.limits, ModelUsageLimits):
            raise LLMContractError("invalid_model_limits")
        if self.pricing_envelope is not None and (
            not isinstance(self.pricing_envelope, RequestedPricingEnvelope)
            or self.pricing_envelope.requested != self.model
        ):
            raise LLMContractError("invalid_registry_pricing_reference")


@dataclass(frozen=True, slots=True)
class ModelRegistry:
    """Small immutable snapshot. ProviderId resolves configured instance metadata.

    Limits/envelopes reuse trusted budget types; declaring an adapter kind alone
    proves no billable token bound. No prices or credential/client objects live here.
    """

    providers: tuple[RegisteredProvider, ...]
    models: tuple[RegisteredModel, ...]

    def __post_init__(self):
        for values, kind in ((self.providers, RegisteredProvider), (self.models, RegisteredModel)):
            if type(values) is not tuple or any(not isinstance(v, kind) for v in values):
                raise LLMContractError("invalid_model_registry")
        ids = {p.provider_id for p in self.providers}
        if len(ids) != len(self.providers) or len({m.model for m in self.models}) != len(
            self.models
        ):
            raise LLMContractError("duplicate_registry_identity")
        if any(m.model.provider_id not in ids for m in self.models):
            raise LLMContractError("registry_provider_missing")

    def lookup(self, model: ModelRef) -> RegisteredModel | None:
        if not isinstance(model, ModelRef):
            raise LLMContractError("invalid_model_ref")
        return next((entry for entry in self.models if entry.model == model), None)

    def provider(self, provider_id: ProviderId) -> RegisteredProvider | None:
        if not isinstance(provider_id, ProviderId):
            raise LLMContractError("invalid_provider_id")
        return next((entry for entry in self.providers if entry.provider_id == provider_id), None)

    def capabilities(self, model: ModelRef) -> ModelCapabilities | None:
        entry = self.lookup(model)
        return entry.capabilities if entry else None

    def usage_bounder(self) -> ModelLimitUsageBounder:
        return ModelLimitUsageBounder(
            {entry.model: entry.limits for entry in self.models if entry.limits is not None}
        )

    def pricing_envelopes(self) -> tuple[RequestedPricingEnvelope, ...]:
        return tuple(
            entry.pricing_envelope for entry in self.models if entry.pricing_envelope is not None
        )
