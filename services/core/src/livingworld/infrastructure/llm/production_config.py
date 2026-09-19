"""Strict version-1 non-secret production LLM configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import MappingProxyType
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from livingworld.application.llm import (
    AdapterKind,
    LLMContractError,
    LLMPurpose,
    ModelCapabilities,
    ModelRef,
    ProviderId,
    StructuredOutputMode,
)
from livingworld.application.llm_budget import ModelUsageLimits
from livingworld.application.llm_config import EndpointConfig, ProviderConfig, SecretRef
from livingworld.application.llm_execution import JitterStrategy, RetryPolicy
from livingworld.application.llm_preflight import RequestedPricingEnvelope
from livingworld.application.llm_pricing import (
    InMemoryPricingCatalog,
    Meter,
    ModelAlias,
    PricingSchedule,
    PricingVariant,
    RateLine,
    UTCWindow,
)
from livingworld.application.llm_registry import ModelRegistry, RegisteredModel, RegisteredProvider
from livingworld.application.llm_routing import (
    FallbackReason,
    PurposePolicy,
    RoutePolicy,
    RoutePolicyId,
    RoutingConfiguration,
    RoutingProfile,
)
from livingworld.infrastructure.llm.anthropic_messages import (
    AnthropicMessagesProfile,
    AnthropicTemperaturePolicy,
)
from livingworld.infrastructure.llm.gemini_interactions import GeminiInteractionsProfile
from livingworld.infrastructure.llm.openai_compatible import ChatCompletionsProfile
from livingworld.infrastructure.llm.openai_responses import OpenAIResponsesProfile

CONFIG_VERSION = 1
MAX_CONFIG_BYTES = 1_048_576
_SECRET_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "password",
    "secret",
    "token",
}


class LLMProductionConfigurationError(ValueError):
    """A stable safe label with no rejected values or parser detail."""

    def __init__(self, code: str = "llm_configuration_invalid"):
        self.code = code
        super().__init__(code)


class _ConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True, strict=True)


class ProviderSpec(_ConfigModel):
    provider_id: str
    adapter_kind: str
    base_url: str | None = None
    secret_ref: str
    timeout_ms: int = Field(default=30_000, ge=1, le=600_000)


class ModelIdentitySpec(_ConfigModel):
    provider_id: str
    model_id: str


class CapabilitySpec(_ConfigModel):
    text_generation: bool = True
    streaming: bool = False
    structured_output: bool = False
    structured_output_mode: str = StructuredOutputMode.NONE.value
    vision: bool = False
    tool_calling: bool = False
    reasoning_controls: bool = False


class ModelLimitsSpec(_ConfigModel):
    max_billable_input_tokens: int = Field(ge=0, le=2**63 - 1)
    max_output_tokens: int = Field(ge=1, le=2**63 - 1)


class PricingEnvelopeSpec(_ConfigModel):
    targets: tuple[ModelIdentitySpec, ...]
    processing_tier: str | None = None


class ModelSpec(_ConfigModel):
    provider_id: str
    model_id: str
    enabled: bool = True
    capabilities: CapabilitySpec
    limits: ModelLimitsSpec | None = None
    adapter_profile: dict[str, Any] = Field(default_factory=dict)
    pricing_envelope: PricingEnvelopeSpec | None = None


class RouteSpec(_ConfigModel):
    policy_id: str
    profile: str
    purpose: str | None = None
    candidates: tuple[ModelIdentitySpec, ...]
    allowed_fallback: tuple[str, ...] = ()


class ExecutionPolicySpec(_ConfigModel):
    max_attempts: int = 3
    initial_backoff_seconds: float = 0.5
    max_backoff_seconds: float = 8.0
    max_elapsed_seconds: float = 30.0
    jitter: str = JitterStrategy.FULL.value
    retry_rate_limits: bool = True
    retry_transient_http: bool = True
    retry_not_dispatched: bool = True
    retry_http_timeouts: bool = True


class RateSpec(_ConfigModel):
    meter: str
    rate: str
    unit_tokens: int = Field(default=1_000_000, ge=1, le=2**63 - 1)


class UTCWindowSpec(_ConfigModel):
    weekdays: tuple[int, ...]
    start_minute: int
    end_minute: int


class PricingVariantSpec(_ConfigModel):
    variant_id: str
    rates: tuple[RateSpec, ...]
    input_min: int | None = None
    input_max_exclusive: int | None = None
    processing_tier: str | None = None
    utc_windows: tuple[UTCWindowSpec, ...] = ()


class PricingScheduleSpec(_ConfigModel):
    schedule_id: str
    model: ModelIdentitySpec
    currency: str
    effective_from: str
    effective_until: str | None = None
    source_label: str
    variants: tuple[PricingVariantSpec, ...]


class PricingAliasSpec(_ConfigModel):
    alias: ModelIdentitySpec
    target: ModelIdentitySpec
    allow_requested_fallback: bool = False


class PricingCatalogSpec(_ConfigModel):
    catalog_id: str
    source_label: str
    schedules: tuple[PricingScheduleSpec, ...] = ()
    aliases: tuple[PricingAliasSpec, ...] = ()


class LLMConfigDocument(_ConfigModel):
    version: int
    providers: tuple[ProviderSpec, ...] = ()
    models: tuple[ModelSpec, ...] = ()
    routes: tuple[RouteSpec, ...] = ()
    execution_policy: ExecutionPolicySpec = ExecutionPolicySpec()
    pricing_catalog: PricingCatalogSpec = PricingCatalogSpec(
        catalog_id="empty", source_label="configured-empty"
    )


@dataclass(frozen=True, slots=True)
class ConfiguredProvider:
    adapter_kind: AdapterKind
    config: ProviderConfig


@dataclass(frozen=True, slots=True)
class ConfiguredModel:
    model: ModelRef
    adapter_kind: AdapterKind
    profile: object


@dataclass(frozen=True, slots=True)
class ProductionLLMConfiguration:
    version: int
    providers: MappingProxyType
    models: MappingProxyType
    registry: ModelRegistry
    routing: RoutingConfiguration
    retry_policy: RetryPolicy
    pricing_catalog: InMemoryPricingCatalog
    pricing_catalog_id: str
    pricing_source_label: str

    @property
    def secret_refs(self) -> tuple[SecretRef, ...]:
        return tuple(
            dict.fromkeys(provider.config.secret_ref for provider in self.providers.values())
        )


def empty_configuration() -> ProductionLLMConfiguration:
    return _convert(LLMConfigDocument(version=CONFIG_VERSION))


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise LLMProductionConfigurationError()
        result[key] = value
    return result


def _reject_secret_keys(value) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = key.lower().replace("-", "_") if type(key) is str else ""
            if normalized in _SECRET_KEYS:
                raise LLMProductionConfigurationError("llm_config_contains_secret_field")
            _reject_secret_keys(item)
    elif isinstance(value, list):
        for item in value:
            _reject_secret_keys(item)


def load_configuration(path: Path | None) -> ProductionLLMConfiguration:
    if path is None or not path.exists():
        return empty_configuration()
    try:
        if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_CONFIG_BYTES:
            raise LLMProductionConfigurationError()
        raw = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
        _reject_secret_keys(raw)
        document = LLMConfigDocument.model_validate_json(
            json.dumps(raw, ensure_ascii=False, separators=(",", ":")), strict=True
        )
        return _convert(document)
    except LLMProductionConfigurationError:
        raise
    except (OSError, UnicodeError, ValueError, TypeError, ValidationError, LLMContractError):
        raise LLMProductionConfigurationError() from None


def _model(identity: ModelIdentitySpec) -> ModelRef:
    return ModelRef(ProviderId(identity.provider_id), identity.model_id)


def _decimal(value: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError):
        raise LLMProductionConfigurationError() from None
    if not parsed.is_finite() or parsed < 0:
        raise LLMProductionConfigurationError()
    return parsed


def _datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise LLMProductionConfigurationError() from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LLMProductionConfigurationError()
    return parsed


def _profile(kind: AdapterKind, values: dict[str, Any]):
    values = dict(values)
    try:
        if kind is AdapterKind.OPENAI_COMPATIBLE:
            allowed = {
                "supports_n",
                "supports_streaming",
                "supports_stream_usage",
                "structured_output_mode",
            }
            if set(values) - allowed:
                raise LLMProductionConfigurationError()
            if "structured_output_mode" in values:
                values["structured_output_mode"] = StructuredOutputMode(
                    values["structured_output_mode"]
                )
            return ChatCompletionsProfile(**values)
        if kind is AdapterKind.ANTHROPIC:
            allowed = {
                "supports_streaming",
                "supports_native_structured_output",
                "supports_assistant_prefill",
                "default_max_output_tokens",
                "max_output_tokens",
                "temperature_minimum",
                "temperature_maximum",
            }
            if set(values) - allowed:
                raise LLMProductionConfigurationError()
            minimum = values.pop("temperature_minimum", None)
            maximum = values.pop("temperature_maximum", None)
            if (minimum is None) != (maximum is None):
                raise LLMProductionConfigurationError()
            if minimum is not None:
                values["temperature_policy"] = AnthropicTemperaturePolicy(minimum, maximum)
            return AnthropicMessagesProfile(**values)
        common = {
            "supports_streaming",
            "supports_native_structured_output",
            "default_max_output_tokens",
            "max_output_tokens",
        }
        if kind is AdapterKind.GEMINI:
            allowed = common | {"supports_assistant_prefill"}
            if set(values) - allowed:
                raise LLMProductionConfigurationError()
            return GeminiInteractionsProfile(**values)
        if kind is AdapterKind.OPENAI_RESPONSES:
            allowed = common | {"supports_temperature", "supports_reasoning_continuation"}
            if set(values) - allowed:
                raise LLMProductionConfigurationError()
            return OpenAIResponsesProfile(**values)
    except (TypeError, ValueError, LLMContractError):
        raise LLMProductionConfigurationError() from None
    raise LLMProductionConfigurationError()


def _profile_capabilities(profile) -> ModelCapabilities:
    if isinstance(profile, ChatCompletionsProfile):
        mode = profile.structured_output_mode
        return ModelCapabilities(
            True,
            profile.supports_streaming,
            mode is not StructuredOutputMode.NONE,
            structured_output_mode=mode,
        )
    structured = profile.supports_native_structured_output
    return ModelCapabilities(
        text_generation=True,
        streaming=profile.supports_streaming,
        structured_output=structured,
        structured_output_mode=StructuredOutputMode.NATIVE_JSON_SCHEMA
        if structured
        else StructuredOutputMode.NONE,
    )


def _capabilities(spec: CapabilitySpec) -> ModelCapabilities:
    try:
        return ModelCapabilities(
            text_generation=spec.text_generation,
            streaming=spec.streaming,
            structured_output=spec.structured_output,
            vision=spec.vision,
            tool_calling=spec.tool_calling,
            reasoning_controls=spec.reasoning_controls,
            structured_output_mode=StructuredOutputMode(spec.structured_output_mode),
        )
    except (ValueError, LLMContractError):
        raise LLMProductionConfigurationError() from None


def _pricing(document: LLMConfigDocument, valid_pricing_models: set[ModelRef]):
    schedules = []
    for source in document.pricing_catalog.schedules:
        model = _model(source.model)
        if (
            model not in valid_pricing_models
            or source.source_label != document.pricing_catalog.source_label
        ):
            raise LLMProductionConfigurationError("invalid_pricing_reference")
        schedules.append(
            PricingSchedule(
                schedule_id=source.schedule_id,
                model=model,
                currency=source.currency,
                effective_from=_datetime(source.effective_from),
                effective_until=_datetime(source.effective_until)
                if source.effective_until is not None
                else None,
                source_label=source.source_label,
                variants=tuple(
                    PricingVariant(
                        variant_id=variant.variant_id,
                        rates=tuple(
                            RateLine(Meter(rate.meter), _decimal(rate.rate), rate.unit_tokens)
                            for rate in variant.rates
                        ),
                        input_min=variant.input_min,
                        input_max_exclusive=variant.input_max_exclusive,
                        processing_tier=variant.processing_tier,
                        utc_windows=tuple(
                            UTCWindow(window.weekdays, window.start_minute, window.end_minute)
                            for window in variant.utc_windows
                        ),
                    )
                    for variant in source.variants
                ),
            )
        )
    aliases = tuple(
        ModelAlias(_model(alias.alias), _model(alias.target), alias.allow_requested_fallback)
        for alias in document.pricing_catalog.aliases
    )
    if any(
        alias.alias not in valid_pricing_models or alias.target not in valid_pricing_models
        for alias in aliases
    ):
        raise LLMProductionConfigurationError("invalid_pricing_reference")
    return InMemoryPricingCatalog(tuple(schedules), aliases)


def _convert(document: LLMConfigDocument) -> ProductionLLMConfiguration:
    if document.version != CONFIG_VERSION:
        raise LLMProductionConfigurationError("llm_config_version_unsupported")
    providers = {}
    try:
        for source in document.providers:
            provider_id = ProviderId(source.provider_id)
            if provider_id in providers:
                raise LLMProductionConfigurationError("duplicate_provider_id")
            kind = AdapterKind(source.adapter_kind)
            provider = ProviderConfig(
                provider_id=provider_id,
                endpoint=EndpointConfig(source.base_url) if source.base_url is not None else None,
                secret_ref=SecretRef(UUID(source.secret_ref)),
                timeout_ms=source.timeout_ms,
            )
            providers[provider_id] = ConfiguredProvider(kind, provider)
    except LLMProductionConfigurationError:
        raise
    except (ValueError, TypeError, LLMContractError):
        raise LLMProductionConfigurationError() from None

    configured_models, registered_models, envelope_targets = {}, [], set()
    for source in document.models:
        model = ModelRef(ProviderId(source.provider_id), source.model_id)
        if model in configured_models:
            raise LLMProductionConfigurationError("duplicate_model_ref")
        provider = providers.get(model.provider_id)
        if provider is None:
            raise LLMProductionConfigurationError("model_provider_missing")
        profile = _profile(provider.adapter_kind, source.adapter_profile)
        declared = _capabilities(source.capabilities)
        if declared != _profile_capabilities(profile):
            raise LLMProductionConfigurationError("model_capability_mismatch")
        limits = (
            ModelUsageLimits(
                source.limits.max_billable_input_tokens, source.limits.max_output_tokens
            )
            if source.limits is not None
            else None
        )
        envelope = None
        if source.pricing_envelope is not None:
            targets = tuple(_model(target) for target in source.pricing_envelope.targets)
            envelope = RequestedPricingEnvelope(
                model, targets, source.pricing_envelope.processing_tier
            )
            envelope_targets.update(targets)
        configured_models[model] = ConfiguredModel(model, provider.adapter_kind, profile)
        registered_models.append(
            RegisteredModel(
                model=model,
                enabled=source.enabled,
                capabilities=declared,
                limits=limits,
                pricing_envelope=envelope,
            )
        )
    registry = ModelRegistry(
        tuple(RegisteredProvider(key, value.adapter_kind) for key, value in providers.items()),
        tuple(registered_models),
    )

    policies = []
    for source in document.routes:
        candidates = tuple(_model(candidate) for candidate in source.candidates)
        if any(
            registry.lookup(candidate) is None or not registry.lookup(candidate).enabled
            for candidate in candidates
        ):
            raise LLMProductionConfigurationError("route_model_unavailable")
        try:
            policies.append(
                PurposePolicy(
                    RoutingProfile(source.profile),
                    RoutePolicy(
                        RoutePolicyId(source.policy_id),
                        candidates,
                        frozenset(FallbackReason(reason) for reason in source.allowed_fallback),
                    ),
                    LLMPurpose(source.purpose) if source.purpose is not None else None,
                )
            )
        except (ValueError, LLMContractError):
            raise LLMProductionConfigurationError() from None
    routing = RoutingConfiguration(tuple(policies))
    execution = document.execution_policy
    try:
        retry = RetryPolicy(
            max_attempts=execution.max_attempts,
            initial_backoff_seconds=execution.initial_backoff_seconds,
            max_backoff_seconds=execution.max_backoff_seconds,
            max_elapsed_seconds=execution.max_elapsed_seconds,
            jitter=JitterStrategy(execution.jitter),
            retry_rate_limits=execution.retry_rate_limits,
            retry_transient_http=execution.retry_transient_http,
            retry_not_dispatched=execution.retry_not_dispatched,
            retry_http_timeouts=execution.retry_http_timeouts,
        )
    except (ValueError, LLMContractError):
        raise LLMProductionConfigurationError() from None
    valid_pricing_models = set(configured_models) | envelope_targets
    pricing = _pricing(document, valid_pricing_models)
    return ProductionLLMConfiguration(
        CONFIG_VERSION,
        MappingProxyType(providers),
        MappingProxyType(configured_models),
        registry,
        routing,
        retry,
        pricing,
        document.pricing_catalog.catalog_id,
        document.pricing_catalog.source_label,
    )
