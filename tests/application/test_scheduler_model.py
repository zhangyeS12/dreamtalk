"""Independent scheduler routing, inheritance and shared budgets; synthetic inputs only."""

import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from livingworld.application.group_chat_reply import GroupChatReplyService
from livingworld.application.llm import AdapterKind, ModelCapabilities, ModelRef, ProviderId
from livingworld.application.llm_budget import ModelUsageLimits
from livingworld.application.llm_registry import ModelRegistry, RegisteredModel, RegisteredProvider
from livingworld.application.llm_routing import (
    ConfiguredGateways,
    RoutedModelGateway,
    RoutingConfiguration,
)
from livingworld.bootstrap.llm_runtime import ProductionLLMSession, configure_group_chat_reply
from livingworld.domain.contracts import RequestId
from livingworld.domain.identifiers import WorldId
from livingworld.infrastructure.llm.production_config import (
    load_configuration,
    load_scheduler_configurations,
    load_world_configurations,
)
from test_group_chat_reply import ScriptedProvider, _environment


def single(name, reference):
    return {
        "version": 1,
        "providers": [
            {
                "provider_id": "fixture",
                "adapter_kind": "openai-compatible",
                "base_url": "https://synthetic.invalid/v1",
                "secret_ref": str(reference),
            }
        ],
        "models": [
            {
                "provider_id": "fixture",
                "model_id": name,
                "enabled": True,
                "capabilities": {"text_generation": True},
                "limits": {"max_billable_input_tokens": 2048, "max_output_tokens": 128},
                "adapter_profile": {"supports_streaming": False},
            }
        ],
    }


def session_for(tmp_path, name):
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps(single(name, uuid4())), encoding="utf-8")
    config = load_configuration(path)
    runtime = SimpleNamespace(
        registry=config.registry, token_bounder=None, gateway=object(), configuration=config
    )
    return ProductionLLMSession(SimpleNamespace(contains=lambda _: True), runtime)


@pytest.mark.parametrize("bad", [None, "global", "world"])
def test_scheduler_configuration_is_independent_and_invalid_overrides_do_not_inherit(tmp_path, bad):
    world = WorldId(uuid4())
    base, body, fast, world_fast = [
        single(name, uuid4()) for name in ("base-pro", "world-pro", "global-flash", "world-flash")
    ]
    payload = {
        "version": 2,
        "default": base,
        "worlds": {str(world.value): body},
        "scheduler": {
            "default": {"invalid": True} if bad == "global" else fast,
            "worlds": {str(world.value): {"invalid": True} if bad == "world" else world_fast},
        },
    }
    path = tmp_path / "models.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    default, worlds = load_world_configurations(path, isolate_invalid=True)
    assert default.registry.models[0].model.model_id == "base-pro"
    assert worlds[world].registry.models[0].model.model_id == "world-pro"
    scheduler, explicit, schedulers = load_scheduler_configurations(path, isolate_invalid=True)
    assert explicit
    assert (scheduler is None) == (bad == "global")
    assert (schedulers[world] is None) == (bad == "world")
    if scheduler is not None:
        assert scheduler.registry.models[0].model.model_id == "global-flash"
    if schedulers[world] is not None:
        assert schedulers[world].registry.models[0].model.model_id == "world-flash"


def test_legacy_config_has_no_scheduler_override(tmp_path):
    path = tmp_path / "models.json"
    path.write_text(json.dumps(single("legacy", uuid4())), encoding="utf-8")
    assert load_scheduler_configurations(path) == (None, False, {})


@pytest.mark.parametrize(
    "override", ["inherit", "global", "world", "invalid-world", "world-only-role"]
)
def test_group_composition_preserves_global_and_world_scheduler_inheritance(tmp_path, override):
    session = session_for(tmp_path, "global-pro")
    body = session_for(tmp_path, "world-pro")
    fast = session_for(tmp_path, "global-flash")
    local_fast = session_for(tmp_path, "world-flash")
    world = WorldId(uuid4())
    if override != "world-only-role":
        session.world_runtimes[world] = body.runtime
    expected = session.runtime
    if override != "inherit":
        session.scheduler_resolved = True
        session.scheduler_runtime = fast.runtime
        expected = fast.runtime
    if override in {"world", "invalid-world", "world-only-role"}:
        session.world_scheduler_runtimes[world] = (
            local_fast.runtime if override != "invalid-world" else None
        )
        expected = local_fast.runtime
    configured = configure_group_chat_reply(session, None, None)
    service = configured.for_world(world)
    if override == "invalid-world":
        assert service is None
        assert configured.default is not None
    else:
        assert (
            service._gateway
            is (session.runtime if override == "world-only-role" else body.runtime).gateway
        )
        assert service._scheduler._gateway is expected.gateway


class RecordingProvider(ScriptedProvider):
    def __init__(self, outputs):
        super().__init__(outputs)
        self.requests = []

    async def generate(self, request):
        self.requests.append(request)
        return await super().generate(request)


class RecordingRouter(RoutedModelGateway):
    async def generate(self, request, **options):
        self.budgets.append(options["turn_budget"])
        return await super().generate(request, **options)


def route(provider, name):
    model = ModelRef(ProviderId("fixture"), name)
    registry = ModelRegistry(
        (RegisteredProvider(model.provider_id, AdapterKind.OPENAI_COMPATIBLE),),
        (
            RegisteredModel(
                model=model,
                enabled=True,
                capabilities=ModelCapabilities(text_generation=True),
                limits=ModelUsageLimits(100, 80),
            ),
        ),
    )
    gateway = RecordingRouter(
        registry, RoutingConfiguration(), ConfiguredGateways({model: provider})
    )
    gateway.budgets = []
    return gateway, registry.usage_bounder(), model, 80


@pytest.mark.parametrize("failure", ["unavailable", "invalid-output"])
def test_scheduler_failure_does_not_fall_back_to_the_dialogue_model(tmp_path, failure):
    async def run():
        db, group, messages, context = await _environment(tmp_path)
        try:
            selection = RecordingProvider(("not-a-member",))
            dialogue = RecordingProvider(("must-not-be-generated",))
            fast = route(selection, "synthetic-flash")
            if failure == "unavailable":
                fast = (*fast, lambda: False)
            service = GroupChatReplyService(
                messages, context, *route(dialogue, "synthetic-pro"), scheduler_configuration=fast
            )
            sent = await messages.send_group_player(
                RequestId(uuid4()), group.conversation_id, "大家好", 1000
            )
            from livingworld.application.chat_reply import (
                ChatReplyUnavailableError,
                ChatReplyValidationError,
            )

            with pytest.raises(
                ChatReplyUnavailableError if failure == "unavailable" else ChatReplyValidationError
            ):
                await service.reply(sent)
            assert dialogue.calls == 0
        finally:
            await db.close()

    asyncio.run(run())


@pytest.mark.parametrize("mention", [False, True])
def test_selection_and_stop_use_flash_while_reply_uses_pro_with_one_shared_budget(
    tmp_path, mention
):
    async def run():
        db, group, messages, context = await _environment(tmp_path)
        try:
            target = group.participants[0]
            selection = RecordingProvider(
                ("STOP",) if mention else (str(target.character_id.value), "STOP")
            )
            dialogue = RecordingProvider(("这是一条角色正文。",))
            fast = route(selection, "synthetic-flash")
            pro = route(dialogue, "synthetic-pro")
            service = GroupChatReplyService(messages, context, *pro, scheduler_configuration=fast)
            text = f"@{target.character_name} 你好" if mention else "大家好"
            sent = await messages.send_group_player(
                RequestId(uuid4()), group.conversation_id, text, 1000
            )
            completed = await service.reply(sent)
            assert len(completed.replies) == 1
            assert selection.calls == (1 if mention else 2) and dialogue.calls == 1
            assert all(r.model.model_id == "synthetic-flash" for r in selection.requests)
            assert dialogue.requests[0].model.model_id == "synthetic-pro"
            budgets = fast[0].budgets + pro[0].budgets
            assert len({id(value) for value in budgets}) == 1
        finally:
            await db.close()

    asyncio.run(run())
