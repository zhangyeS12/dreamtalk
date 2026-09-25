"""One direct reply uses the shared token guard and does not fake world events."""

import asyncio
import io
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from card_fixtures import card_document, json_bytes
from fastapi.testclient import TestClient
from livingworld.adapters.http.app import create_app
from livingworld.application.chat_context import DirectChatContext, DirectChatContextBuilder
from livingworld.application.chat_conversations import ChatConversationService
from livingworld.application.chat_messages import (
    ChatMessage,
    ChatMessageService,
    ClaimedDirectTurn,
    PlayerSend,
)
from livingworld.application.chat_reply import (
    ChatReplyBudgetError,
    ChatReplyUnavailableError,
    ChatReplyValidationError,
    DirectChatReplyService,
)
from livingworld.application.command_handler import CommandHandler
from livingworld.application.commands import CreateWorld
from livingworld.application.errors import ChatTurnUnavailableError
from livingworld.application.llm import (
    AdapterKind,
    FinishReason,
    InvocationId,
    LLMMessage,
    LLMPurpose,
    LLMResponse,
    LLMUsage,
    MessageRole,
    ModelCapabilities,
    ModelRef,
    ProviderId,
    TextContent,
)
from livingworld.application.llm_budget import ModelLimitUsageBounder, ModelUsageLimits
from livingworld.application.llm_chat_turn_budget import (
    TurnTokenBoundViolation,
)
from livingworld.application.llm_registry import ModelRegistry, RegisteredModel, RegisteredProvider
from livingworld.application.llm_routing import (
    ConfiguredGateways,
    FallbackReason,
    ProfileSelection,
    PurposePolicy,
    RoutedModelGateway,
    RoutePolicy,
    RoutePolicyId,
    RoutingConfiguration,
    RoutingProfile,
)
from livingworld.application.player_event_feed import PlayerEventFeedService
from livingworld.application.player_onboarding import LocalPlayerOnboardingService
from livingworld.application.runtime import RuntimeStatus, ShutdownRequests
from livingworld.application.simulation_clock import EffectiveWorldTimeSource, SystemMonotonicClock
from livingworld.domain.contracts import RequestId
from livingworld.domain.identifiers import (
    CharacterId,
    ChatTurnId,
    ConversationId,
    MessageId,
    PlayerId,
    WorldId,
)
from livingworld.infrastructure.clock import SystemWallClock
from livingworld.infrastructure.llm.fake import FakeModelGateway
from livingworld.infrastructure.logging import StructuredLogger
from livingworld.infrastructure.persistence import Database
from livingworld.infrastructure.persistence.models import ObservationRecord, WorldEventRecord
from sqlalchemy import func, select


def _sent():
    world = WorldId(uuid4())
    conversation = ConversationId(world, uuid4())
    turn = ChatTurnId(world, uuid4())
    player = PlayerId(world, uuid4())
    character = CharacterId(world, uuid4())
    player_message = ChatMessage(
        MessageId(world, uuid4()), conversation, turn, 1, player, "玩家私聊", datetime.now(UTC)
    )
    return PlayerSend(turn, player_message, 50000, "pending"), character


class _Messages:
    def __init__(self, sent, character, calls):
        self.claim = ClaimedDirectTurn(
            sent.turn_id,
            sent.message.conversation_id,
            sent.message.sender_id,
            character,
            sent.message,
            sent.token_ceiling,
        )
        self.calls = calls

    async def claim_direct(self, conversation_id, turn_id):
        self.calls.append("claim")
        assert conversation_id == self.claim.conversation_id
        assert turn_id == self.claim.turn_id
        return self.claim

    async def complete_direct(self, claim, text):
        self.calls.append("complete")
        assert claim == self.claim
        return ChatMessage(
            MessageId(claim.turn_id.world_id, uuid4()),
            claim.conversation_id,
            claim.turn_id,
            2,
            claim.character_id,
            text,
            datetime.now(UTC),
        )


class _Context:
    async def build(self, sent):
        assert sent.message.text == "玩家私聊"
        return DirectChatContext((LLMMessage(MessageRole.USER, (TextContent("玩家私聊"),)),))


class _Gateway:
    def __init__(
        self,
        calls,
        *,
        finish=FinishReason.STOP,
        text="角色回复",
        fail_plan=False,
        expected_output=2048,
        expected_ceiling=50000,
    ):
        self.calls = calls
        self.finish = finish
        self.text = text
        self.fail_plan = fail_plan
        self.expected_output = expected_output
        self.expected_ceiling = expected_ceiling
        self.bound_violation = False
        self.invocation_mismatch = False

    def plan(self, request, *, selection=None):
        self.calls.append("plan")
        assert request.purpose.value == "character_dialogue"
        if self.fail_plan:
            raise ValueError("route_unavailable")
        return SimpleNamespace(candidates=(request.model,))

    async def generate(self, request, *, selection=None, turn_budget):
        self.calls.append("generate")
        assert request.max_output_tokens == self.expected_output
        assert turn_budget.remaining == self.expected_ceiling
        if self.bound_violation:
            attempt_id = uuid4()
            turn_budget.reserve(attempt_id, input_upper_bound=1, max_output_tokens=1)
            with pytest.raises(TurnTokenBoundViolation):
                turn_budget.settle(
                    attempt_id, LLMUsage(input_tokens=10, output_tokens=10, total_tokens=20)
                )
        return LLMResponse(
            invocation_id=InvocationId(uuid4())
            if self.invocation_mismatch
            else request.invocation_id,
            model_used=request.model,
            content=(TextContent(self.text),),
            finish_reason=self.finish,
            usage=LLMUsage(input_tokens=10, output_tokens=10, total_tokens=20),
        )


def _service(sent, character, gateway, calls):
    model = ModelRef(ProviderId("configured"), "model")
    return DirectChatReplyService(
        _Messages(sent, character, calls),
        _Context(),
        gateway,
        ModelLimitUsageBounder({model: ModelUsageLimits(100, 2048)}),
        model,
        2048,
    )


def test_direct_reply_plans_then_claims_then_generates_then_commits():
    async def run():
        sent, character = _sent()
        calls = []
        gateway = _Gateway(calls)
        reply = await _service(sent, character, gateway, calls).reply(sent)
        assert calls == ["plan", "claim", "generate", "complete"]
        assert reply.text == "角色回复"
        assert reply.sender_id == character

    asyncio.run(run())


@pytest.mark.parametrize(
    ("finish", "text", "violated", "mismatch", "accepted"),
    [
        (FinishReason.REFUSAL, "模型拒绝了请求", False, False, True),
        (FinishReason.OUTPUT_LIMIT, "截断", False, False, False),
        (FinishReason.STOP, "  ", False, False, False),
        (FinishReason.STOP, "角色回复", True, False, False),
        (FinishReason.STOP, "角色回复", False, True, False),
    ],
)
def test_response_validation_never_commits_unusable_or_over_bound_text(
    finish, text, violated, mismatch, accepted
):
    async def run():
        sent, character = _sent()
        calls = []
        gateway = _Gateway(calls, finish=finish, text=text)
        gateway.bound_violation = violated
        gateway.invocation_mismatch = mismatch
        service = _service(sent, character, gateway, calls)
        if accepted:
            assert (await service.reply(sent)).text == text
            assert calls[-1] == "complete"
        else:
            with pytest.raises(ChatReplyValidationError):
                await service.reply(sent)
            assert calls == ["plan", "claim", "generate"]

    asyncio.run(run())


def test_invalid_route_never_claims_or_calls_provider():
    async def run():
        sent, character = _sent()
        calls = []
        gateway = _Gateway(calls, fail_plan=True)
        with pytest.raises(ValueError, match="route_unavailable"):
            await _service(sent, character, gateway, calls).reply(sent)
        assert calls == ["plan"]

    asyncio.run(run())


def test_unaffordable_turn_rejects_before_claim_or_provider():
    async def run():
        sent, character = _sent()
        sent = replace(sent, token_ceiling=100)
        calls = []
        with pytest.raises(ChatReplyBudgetError, match="turn_token_limit_exceeded"):
            await _service(sent, character, _Gateway(calls), calls).reply(sent)
        assert calls == ["plan"]

    asyncio.run(run())


def test_missing_trusted_input_bound_rejects_before_claim_or_provider():
    async def run():
        sent, character = _sent()
        calls = []
        model = ModelRef(ProviderId("configured"), "model")
        service = DirectChatReplyService(
            _Messages(sent, character, calls),
            _Context(),
            _Gateway(calls),
            ModelLimitUsageBounder({}),
            model,
            2048,
        )
        with pytest.raises(ChatReplyBudgetError, match="turn_input_bound_unavailable"):
            await service.reply(sent)
        assert calls == ["plan"]

    asyncio.run(run())


def test_missing_session_credential_rejects_before_claim_or_provider():
    async def run():
        sent, character = _sent()
        calls = []
        model = ModelRef(ProviderId("configured"), "model")
        service = DirectChatReplyService(
            _Messages(sent, character, calls),
            _Context(),
            _Gateway(calls),
            ModelLimitUsageBounder({model: ModelUsageLimits(100, 2048)}),
            model,
            2048,
            available=lambda: False,
        )
        with pytest.raises(ChatReplyUnavailableError, match="chat_model_unavailable"):
            await service.reply(sent)
        assert calls == []

    asyncio.run(run())


def test_turn_output_cap_is_reduced_to_fit_trusted_input_bound():
    async def run():
        sent, character = _sent()
        sent = replace(sent, token_ceiling=1000)
        calls = []
        gateway = _Gateway(calls, expected_output=900, expected_ceiling=1000)
        assert (await _service(sent, character, gateway, calls).reply(sent)).text == "角色回复"
        assert calls == ["plan", "claim", "generate", "complete"]

    asyncio.run(run())


def test_direct_reply_runs_through_real_routing_and_physical_token_guard():
    async def run():
        sent, character = _sent()
        calls = []
        model = ModelRef(ProviderId("configured"), "model")

        class CountingFake(FakeModelGateway):
            async def generate(self, request):
                calls.append("provider")
                return await super().generate(request)

        provider = CountingFake(
            chunks=("经模型网关的角色回复",),
            usage=LLMUsage(input_tokens=10, output_tokens=10, total_tokens=20),
        )
        registry = ModelRegistry(
            (RegisteredProvider(model.provider_id, AdapterKind.OPENAI_COMPATIBLE),),
            (
                RegisteredModel(
                    model=model,
                    enabled=True,
                    capabilities=ModelCapabilities(text_generation=True),
                    limits=ModelUsageLimits(100, 2048),
                ),
            ),
        )
        gateway = RoutedModelGateway(
            registry, RoutingConfiguration(), ConfiguredGateways({model: provider})
        )
        reply = await _service(sent, character, gateway, calls).reply(sent)
        assert reply.text == "经模型网关的角色回复"
        assert calls == ["claim", "provider", "complete"]

    asyncio.run(run())


def test_configured_chat_route_falls_back_with_one_shared_turn_budget():
    async def run():
        sent, character = _sent()
        calls = []
        primary = ModelRef(ProviderId("primary"), "model-a")
        backup = ModelRef(ProviderId("backup"), "model-b")

        class CountingFake(FakeModelGateway):
            async def generate(self, request):
                calls.append("provider")
                return await super().generate(request)

        registry = ModelRegistry(
            (
                RegisteredProvider(primary.provider_id, AdapterKind.OPENAI_COMPATIBLE),
                RegisteredProvider(backup.provider_id, AdapterKind.OPENAI_COMPATIBLE),
            ),
            tuple(
                RegisteredModel(
                    model=model,
                    enabled=True,
                    capabilities=ModelCapabilities(text_generation=True),
                    limits=ModelUsageLimits(input_bound, 1024),
                )
                for model, input_bound in ((primary, 100), (backup, 200))
            ),
        )
        policy = RoutePolicy(
            RoutePolicyId("chat-balanced"),
            (primary, backup),
            frozenset({FallbackReason.CANDIDATE_UNAVAILABLE}),
        )
        gateway = RoutedModelGateway(
            registry,
            RoutingConfiguration(
                (PurposePolicy(RoutingProfile.BALANCED, policy, LLMPurpose("character_dialogue")),)
            ),
            ConfiguredGateways(
                {backup: CountingFake(chunks=("备用角色回复",), usage=LLMUsage(10, 10, 20))},
                credential_available=lambda model: model == backup,
            ),
        )
        service = DirectChatReplyService(
            _Messages(sent, character, calls),
            _Context(),
            gateway,
            registry.usage_bounder(),
            primary,
            1024,
            selection=ProfileSelection(RoutingProfile.BALANCED),
        )
        assert (await service.reply(sent)).text == "备用角色回复"
        assert calls == ["claim", "provider", "complete"]

    asyncio.run(run())


def test_route_with_unbounded_fallback_cannot_claim_a_chat_turn():
    async def run():
        sent, character = _sent()
        calls = []
        primary = ModelRef(ProviderId("primary"), "bounded")
        backup = ModelRef(ProviderId("backup"), "unbounded")
        registry = ModelRegistry(
            (
                RegisteredProvider(primary.provider_id, AdapterKind.OPENAI_COMPATIBLE),
                RegisteredProvider(backup.provider_id, AdapterKind.OPENAI_COMPATIBLE),
            ),
            tuple(
                RegisteredModel(
                    model=model,
                    enabled=True,
                    capabilities=ModelCapabilities(text_generation=True),
                    limits=limits,
                )
                for model, limits in (
                    (primary, ModelUsageLimits(100, 1024)),
                    (backup, None),
                )
            ),
        )
        policy = RoutePolicy(RoutePolicyId("chat"), (primary, backup))
        gateway = RoutedModelGateway(
            registry,
            RoutingConfiguration(
                (PurposePolicy(RoutingProfile.BALANCED, policy, LLMPurpose("character_dialogue")),)
            ),
            ConfiguredGateways(
                {
                    primary: FakeModelGateway(chunks=("a",)),
                    backup: FakeModelGateway(chunks=("b",)),
                }
            ),
        )
        service = DirectChatReplyService(
            _Messages(sent, character, calls),
            _Context(),
            gateway,
            registry.usage_bounder(),
            primary,
            1024,
            selection=ProfileSelection(RoutingProfile.BALANCED),
        )
        with pytest.raises(ChatReplyBudgetError, match="turn_input_bound_unavailable"):
            await service.reply(sent)
        assert calls == []

    asyncio.run(run())


def test_direct_reply_persists_once_without_creating_world_facts(tmp_path):
    async def run():
        db = Database(tmp_path)
        try:
            await db.initialize()
            clock = SystemWallClock()
            handler = CommandHandler(
                db.unit_of_work,
                clock,
                world_time_source=EffectiveWorldTimeSource(clock, SystemMonotonicClock()),
            )
            world = WorldId(uuid4())
            await handler.execute(
                CreateWorld(request_id=RequestId(uuid4()), world_id=world, name="私聊世界")
            )
            players = PlayerEventFeedService(db.player_event_feed_store())
            await LocalPlayerOnboardingService(handler, players).start_at_home(world)
            imports = db.world_content_service()
            staged = await imports.prepare(world, "character", json_bytes(card_document()))
            card = await imports.commit(world, staged.item.import_id, staged.item.reviewed_hash)
            conversations = ChatConversationService(
                db.chat_conversation_store(), imports, players, handler
            )
            conversation = await conversations.open_direct(world, card.import_id)
            messages = ChatMessageService(db.chat_message_store(), players)
            sent = await messages.send_player(
                RequestId(uuid4()), conversation.conversation_id, "你好", 50000
            )
            async with db._sessions() as session:
                events_before = await session.scalar(
                    select(func.count()).select_from(WorldEventRecord)
                )
            model = ModelRef(ProviderId("configured"), "model")
            calls = []

            class CountingFake(FakeModelGateway):
                async def generate(self, request):
                    calls.append("provider")
                    return await super().generate(request)

            provider = CountingFake(
                chunks=("欢迎来到图书馆。",),
                usage=LLMUsage(input_tokens=10, output_tokens=10, total_tokens=20),
            )
            registry = ModelRegistry(
                (RegisteredProvider(model.provider_id, AdapterKind.OPENAI_COMPATIBLE),),
                (
                    RegisteredModel(
                        model=model,
                        enabled=True,
                        capabilities=ModelCapabilities(text_generation=True),
                        limits=ModelUsageLimits(100, 2048),
                    ),
                ),
            )
            gateway = RoutedModelGateway(
                registry, RoutingConfiguration(), ConfiguredGateways({model: provider})
            )
            service = DirectChatReplyService(
                messages,
                DirectChatContextBuilder(
                    conversations,
                    messages,
                    db.local_profile_store(),
                    db.character_memory_reader,
                ),
                gateway,
                registry.usage_bounder(),
                model,
                2048,
            )
            reply = await service.reply(sent)
            assert reply.sender_id == conversation.character_id
            assert reply.text == "欢迎来到图书馆。"
            completed = await messages.direct_turn(conversation.conversation_id, sent.turn_id)
            assert completed.state == "completed"
            assert completed.reply == reply
            http_sent = await messages.send_player(
                RequestId(uuid4()), conversation.conversation_id, "从页面发起", 50000
            )
            app = create_app(
                RuntimeStatus("test", "generation"),
                ShutdownRequests(),
                "secret",
                lambda: None,
                StructuredLogger(io.StringIO()),
                chat_messages=messages,
                chat_reply=service,
            )
            path = (
                f"/api/v1/worlds/{world.value}/conversations/"
                f"{conversation.conversation_id.value}/turns/{http_sent.turn_id.value}/reply"
            )
            with TestClient(app, base_url="http://127.0.0.1") as client:
                assert client.post(path).status_code == 401
                headers = {"Authorization": "Bearer secret"}
                first_http = client.post(path, headers=headers)
                assert first_http.status_code == 200
                assert first_http.json()["state"] == "completed"
                assert first_http.json()["reply"]["text"] == "欢迎来到图书馆。"
                assert client.post(path, headers=headers).json() == first_http.json()
            assert calls == ["provider", "provider"]
            interrupted = await messages.send_player(
                RequestId(uuid4()), conversation.conversation_id, "下一条", 50000
            )
            await messages.claim_direct(conversation.conversation_id, interrupted.turn_id)
            claimed = await messages.direct_turn(conversation.conversation_id, interrupted.turn_id)
            assert claimed.state == "claimed"
            assert claimed.reply is None
            with pytest.raises(ChatTurnUnavailableError, match="chat_turn_already_claimed"):
                await service.reply(sent)
            assert calls == ["provider", "provider"]
            assert await messages.list_messages(conversation.conversation_id) == (
                sent.message,
                reply,
                http_sent.message,
                (await messages.direct_turn(conversation.conversation_id, http_sent.turn_id)).reply,
                interrupted.message,
            )
            async with db._sessions() as session:
                assert (
                    await session.scalar(select(func.count()).select_from(WorldEventRecord))
                    == events_before
                )
                assert (
                    await session.scalar(select(func.count()).select_from(ObservationRecord)) == 0
                )
        finally:
            await db.close()

    asyncio.run(run())
