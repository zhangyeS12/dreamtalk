"""Chat model selection is an explicit operational policy, never config order."""

from types import SimpleNamespace
from uuid import uuid4

from livingworld.application.llm import (
    AdapterKind,
    LLMPurpose,
    ModelCapabilities,
    ModelRef,
    ProviderId,
)
from livingworld.application.llm_budget import ModelUsageLimits
from livingworld.application.llm_config import SecretRef
from livingworld.application.llm_registry import ModelRegistry, RegisteredModel, RegisteredProvider
from livingworld.application.llm_routing import (
    FallbackReason,
    PurposePolicy,
    RoutePolicy,
    RoutePolicyId,
    RoutingConfiguration,
    RoutingProfile,
)
from livingworld.bootstrap.llm_runtime import (
    ProductionLLMSession,
    configure_direct_chat_reply,
    configure_group_chat_reply,
)


def _session(*, model_count: int, routed: bool, fallback: bool = False, key_index: int = 0):
    models = tuple(
        ModelRef(ProviderId(f"provider-{index}"), f"model-{index}") for index in range(model_count)
    )
    registry = ModelRegistry(
        tuple(
            RegisteredProvider(model.provider_id, AdapterKind.OPENAI_COMPATIBLE) for model in models
        ),
        tuple(
            RegisteredModel(
                model=model,
                enabled=True,
                capabilities=ModelCapabilities(text_generation=True),
                limits=ModelUsageLimits(100 + index * 100, 2048 - index * 1024),
            )
            for index, model in enumerate(models)
        ),
    )
    policies = (
        (
            PurposePolicy(
                RoutingProfile.BALANCED,
                RoutePolicy(
                    RoutePolicyId("chat"),
                    models,
                    frozenset({FallbackReason.CANDIDATE_UNAVAILABLE}) if fallback else frozenset(),
                ),
                LLMPurpose("character_dialogue"),
            ),
        )
        if routed
        else ()
    )
    refs = {model.provider_id: SecretRef(uuid4()) for model in models}
    runtime = SimpleNamespace(
        registry=registry,
        gateway=object(),
        configuration=SimpleNamespace(
            routing=RoutingConfiguration(policies),
            providers={
                provider: SimpleNamespace(config=SimpleNamespace(secret_ref=reference))
                for provider, reference in refs.items()
            },
        ),
    )
    credentials = SimpleNamespace(
        contains=lambda reference: reference == refs[models[key_index].provider_id]
    )
    return ProductionLLMSession(credentials, runtime), models


def test_one_enabled_model_is_an_unambiguous_direct_chat_choice():
    session, _ = _session(model_count=1, routed=False)
    service = configure_direct_chat_reply(session, object(), object())
    assert service is not None
    assert service.available
    group = configure_group_chat_reply(session, object(), object())
    assert group is not None
    assert group.available


def test_multiple_models_without_explicit_chat_route_do_not_pick_one():
    session, _ = _session(model_count=2, routed=False)
    assert configure_direct_chat_reply(session, object(), object()) is None
    assert configure_group_chat_reply(session, object(), object()) is None


def test_explicit_balanced_route_permits_composition():
    session, _ = _session(model_count=2, routed=True)
    service = configure_direct_chat_reply(session, object(), object())
    assert service is not None
    assert service.available


def test_chat_availability_follows_explicit_credential_fallback_policy():
    session, _ = _session(model_count=2, routed=True, fallback=True, key_index=1)
    direct = configure_direct_chat_reply(session, object(), object())
    group = configure_group_chat_reply(session, object(), object())
    assert direct is not None and direct.available
    assert group is not None and group.available

    # Without explicit fallback, a missing primary key makes the route unusable.
    strict, _ = _session(model_count=2, routed=True, key_index=1)
    assert not configure_direct_chat_reply(strict, object(), object()).available
    assert not configure_group_chat_reply(strict, object(), object()).available


def test_missing_runtime_keeps_chat_generation_unavailable():
    assert configure_direct_chat_reply(ProductionLLMSession(object()), object(), object()) is None
