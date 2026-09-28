"""Single production composition root for the complete Stage-4 LLM graph."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from livingworld.application.chat_context import DirectChatContextBuilder
from livingworld.application.chat_messages import ChatMessageService
from livingworld.application.chat_reply import DirectChatReplyService
from livingworld.application.group_chat_context import GroupChatContextBuilder
from livingworld.application.group_chat_reply import GroupChatReplyService
from livingworld.application.llm import InvocationId, LLMPurpose
from livingworld.application.llm_config import LLMRuntimeHealth, SecretRef
from livingworld.application.llm_registry import ModelRegistry
from livingworld.application.llm_routing import (
    ConfiguredGateways,
    FallbackReason,
    ProfileSelection,
    RoutedModelGateway,
    RoutingProfile,
)
from livingworld.infrastructure.llm.anthropic_messages import AnthropicMessagesGateway
from livingworld.infrastructure.llm.credentials import SessionCredentialProvider
from livingworld.infrastructure.llm.gemini_interactions import GeminiInteractionsGateway
from livingworld.infrastructure.llm.openai_compatible import OpenAICompatibleChatGateway
from livingworld.infrastructure.llm.openai_responses import OpenAIResponsesGateway
from livingworld.infrastructure.llm.production_config import (
    LLMProductionConfigurationError,
    ProductionLLMConfiguration,
    load_configuration,
)
from livingworld.infrastructure.logging import StructuredLogger
from livingworld.infrastructure.persistence.engine import Database
from livingworld.infrastructure.persistence.llm_budget_repository import BudgetDiagnostics
from livingworld.infrastructure.persistence.llm_repository import AccountingDiagnostics


@dataclass(frozen=True, slots=True)
class InvocationFactory:
    def create(self) -> InvocationId:
        return InvocationId(uuid4())


@dataclass(slots=True)
class ProductionLLMRuntime:
    """Owns adapter clients; callers receive only the governed routed gateway."""

    configuration: ProductionLLMConfiguration
    credentials: SessionCredentialProvider
    gateway: RoutedModelGateway
    registry: ModelRegistry
    invocation_factory: InvocationFactory = field(default_factory=InvocationFactory)
    _owned_gateways: tuple[object, ...] = field(default=(), repr=False)

    @property
    def health(self) -> LLMRuntimeHealth:
        if not self.configuration.registry.models:
            return LLMRuntimeHealth.UNCONFIGURED
        return self.credentials.health

    async def aclose(self) -> None:
        for gateway in reversed(self._owned_gateways):
            await gateway.aclose()


@dataclass(slots=True)
class ProductionLLMSession:
    """Optional LLM subsystem lifecycle kept outside the generic Core bootstrap."""

    credentials: SessionCredentialProvider
    runtime: ProductionLLMRuntime | None = None

    def health(self) -> str:
        return (
            self.runtime.health.value
            if self.runtime is not None
            else LLMRuntimeHealth.DEGRADED.value
        )

    async def aclose(self) -> None:
        if self.runtime is not None:
            await self.runtime.aclose()


def configure_direct_chat_reply(
    session: ProductionLLMSession,
    messages: ChatMessageService,
    context: DirectChatContextBuilder,
) -> DirectChatReplyService | None:
    """Use the explicit BALANCED route, or the sole eligible configured model."""
    configured = _chat_reply_configuration(session)
    if configured is None:
        return None
    return DirectChatReplyService(messages, context, *configured)


def configure_group_chat_reply(
    session: ProductionLLMSession,
    messages: ChatMessageService,
    context: GroupChatContextBuilder,
) -> GroupChatReplyService | None:
    configured = _chat_reply_configuration(session)
    if configured is None:
        return None
    return GroupChatReplyService(messages, context, *configured)


def configure_content_builder(session: ProductionLLMSession):
    return _chat_reply_configuration(session, "content_builder")


def _chat_reply_configuration(session: ProductionLLMSession, purpose="character_dialogue"):
    runtime = session.runtime
    if runtime is None:
        return None
    policy = runtime.configuration.routing.policy(LLMPurpose(purpose), RoutingProfile.BALANCED)
    selection = ProfileSelection(RoutingProfile.BALANCED) if policy else None
    # Multiple enabled models need an explicit route; config order is not policy.
    candidates = (
        policy.candidates
        if policy is not None
        else tuple(
            entry.model
            for entry in runtime.registry.models
            if entry.enabled and entry.capabilities.text_generation
        )
    )
    entries = tuple(runtime.registry.lookup(model) for model in candidates)
    if (
        not entries
        or policy is None
        and len(entries) != 1
        or any(
            entry is None
            or not entry.enabled
            or not entry.capabilities.text_generation
            or entry.limits is None
            for entry in entries
        )
    ):
        return None
    primary = entries[0]

    def available() -> bool:
        # The route may explicitly permit skipping candidates without a key.
        # Match the router's candidate-unavailable policy when reporting chat
        # availability, including after in-memory credential rotation.
        reachable = (
            entries
            if policy is not None
            and FallbackReason.CANDIDATE_UNAVAILABLE in policy.allowed_fallback
            else (primary,)
        )
        return any(
            session.credentials.contains(
                runtime.configuration.providers[entry.model.provider_id].config.secret_ref
            )
            for entry in reachable
        )

    return (
        runtime.gateway,
        runtime.registry.usage_bounder(),
        primary.model,
        min(entry.limits.max_output_tokens for entry in entries),
        available,
        selection,
    )


def _factory(model, configured, provider, credentials, logger):
    kwargs = {
        "config": provider.config,
        "credentials": credentials,
        "profile": configured.profile,
        "logger": logger,
    }
    kind = configured.adapter_kind
    from livingworld.application.llm import AdapterKind

    if kind is AdapterKind.OPENAI_COMPATIBLE:
        return OpenAICompatibleChatGateway(**kwargs)
    if kind is AdapterKind.ANTHROPIC:
        return AnthropicMessagesGateway(**kwargs)
    if kind is AdapterKind.GEMINI:
        return GeminiInteractionsGateway(**kwargs)
    if kind is AdapterKind.OPENAI_RESPONSES:
        return OpenAIResponsesGateway(**kwargs)
    raise ValueError("adapter_kind_unsupported")


async def build_production_llm_runtime(
    configuration: ProductionLLMConfiguration,
    database: Database,
    logger: StructuredLogger,
    *,
    credentials: SessionCredentialProvider | None = None,
) -> ProductionLLMRuntime:
    enabled = tuple(entry for entry in configuration.registry.models if entry.enabled)
    expected: tuple[SecretRef, ...] = tuple(
        dict.fromkeys(
            configuration.providers[entry.model.provider_id].config.secret_ref for entry in enabled
        )
    )
    credentials = credentials or SessionCredentialProvider(expected)
    gateways = {}
    owned = []
    try:
        for entry in enabled:
            configured = configuration.models[entry.model]
            provider = configuration.providers[entry.model.provider_id]
            gateway = _factory(entry.model, configured, provider, credentials, logger)
            gateways[entry.model] = gateway
            owned.append(gateway)
    except BaseException:
        # Construction is synchronous and no request can be in flight here.
        for gateway in reversed(owned):
            await gateway.aclose()
        raise

    provider_refs = {
        model: configuration.providers[model.provider_id].config.secret_ref for model in gateways
    }
    resolver = ConfiguredGateways(
        gateways,
        credential_available=lambda model: credentials.contains(provider_refs[model]),
    )
    budget = database.llm_budget_guard(
        bounder=configuration.registry.usage_bounder(),
        diagnostics=BudgetDiagnostics(logger),
        catalog=configuration.pricing_catalog,
        envelopes=configuration.registry.pricing_envelopes(),
    )
    routed = RoutedModelGateway(
        configuration.registry,
        configuration.routing,
        resolver,
        policy=configuration.retry_policy,
        budget_guard=budget,
        wall_clock=lambda: datetime.now(UTC),
        accounting_diagnostics=AccountingDiagnostics(logger),
    )
    return ProductionLLMRuntime(
        configuration,
        credentials,
        routed,
        configuration.registry,
        _owned_gateways=tuple(owned),
    )


async def start_production_llm_session(
    config_path: Path | None,
    database: Database,
    logger: StructuredLogger,
) -> ProductionLLMSession:
    """Load the immutable snapshot while allowing optional LLM failure isolation."""
    try:
        configuration = load_configuration(config_path)
        enabled = tuple(entry for entry in configuration.registry.models if entry.enabled)
        expected = tuple(
            dict.fromkeys(
                configuration.providers[entry.model.provider_id].config.secret_ref
                for entry in enabled
            )
        )
        credentials = SessionCredentialProvider(expected)
        runtime = await build_production_llm_runtime(
            configuration, database, logger, credentials=credentials
        )
        return ProductionLLMSession(credentials, runtime)
    except LLMProductionConfigurationError:
        credentials = SessionCredentialProvider()
        credentials.mark_degraded()
        logger.emit("llm", "llm_configuration_invalid", level="ERROR")
        return ProductionLLMSession(credentials)
