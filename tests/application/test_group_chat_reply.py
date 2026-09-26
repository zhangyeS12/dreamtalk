"""Group turns share one governed token ceiling across selection and replies."""

import asyncio
import io
from uuid import uuid4

import pytest
from card_fixtures import card_document, json_bytes
from fastapi.testclient import TestClient
from livingworld.adapters.http.app import create_app
from livingworld.application.chat_conversations import ChatConversationService
from livingworld.application.chat_messages import ChatMessageService
from livingworld.application.chat_reply import ChatReplyBudgetError, ChatReplyValidationError
from livingworld.application.command_handler import CommandHandler
from livingworld.application.commands import CreateWorld
from livingworld.application.group_chat_context import GroupChatContextBuilder
from livingworld.application.group_chat_reply import GroupChatReplyService
from livingworld.application.llm import (
    AdapterKind,
    FinishReason,
    LLMResponse,
    LLMUsage,
    ModelCapabilities,
    ModelRef,
    ProviderId,
    TextContent,
)
from livingworld.application.llm_budget import ModelUsageLimits
from livingworld.application.llm_registry import ModelRegistry, RegisteredModel, RegisteredProvider
from livingworld.application.llm_routing import (
    ConfiguredGateways,
    RoutedModelGateway,
    RoutingConfiguration,
)
from livingworld.application.player_event_feed import PlayerEventFeedService
from livingworld.application.player_onboarding import LocalPlayerOnboardingService
from livingworld.application.runtime import RuntimeStatus, ShutdownRequests
from livingworld.application.simulation_clock import EffectiveWorldTimeSource, SystemMonotonicClock
from livingworld.domain.contracts import RequestId
from livingworld.domain.identifiers import WorldId
from livingworld.infrastructure.clock import SystemWallClock
from livingworld.infrastructure.llm.fake import FakeModelGateway
from livingworld.infrastructure.logging import StructuredLogger
from livingworld.infrastructure.persistence import Database


class ScriptedProvider(FakeModelGateway):
    def __init__(self, outputs: tuple[str, ...], usage: LLMUsage | None = None):
        super().__init__()
        self.outputs = iter(outputs)
        self.calls = 0
        self.usage = usage if usage is not None else LLMUsage(10, 10, 20)

    async def generate(self, request):
        self.calls += 1
        return LLMResponse(
            invocation_id=request.invocation_id,
            model_used=request.model,
            content=(TextContent(next(self.outputs)),),
            finish_reason=FinishReason.STOP,
            usage=self.usage,
        )


async def _environment(tmp_path):
    db = Database(tmp_path)
    await db.initialize()
    clock = SystemWallClock()
    handler = CommandHandler(
        db.unit_of_work,
        clock,
        world_time_source=EffectiveWorldTimeSource(clock, SystemMonotonicClock()),
    )
    players = PlayerEventFeedService(db.player_event_feed_store())
    imports = db.world_content_service()
    chats = ChatConversationService(db.chat_conversation_store(), imports, players, handler)
    messages = ChatMessageService(db.chat_message_store(), players)
    world = WorldId(uuid4())
    await handler.execute(CreateWorld(request_id=RequestId(uuid4()), world_id=world, name="世界"))
    await LocalPlayerOnboardingService(handler, players).start_at_home(world)
    cards = []
    for name in ("角色甲", "角色乙"):
        document = card_document()
        document["data"]["name"] = name
        staged = await imports.prepare(world, "character", json_bytes(document))
        cards.append(await imports.commit(world, staged.item.import_id, staged.item.reviewed_hash))
    group = await chats.create_group(world, RequestId(uuid4()), tuple(c.import_id for c in cards))
    context = GroupChatContextBuilder(
        chats, messages, db.local_profile_store(), db.character_memory_reader
    )
    return db, group, messages, context


def _service(messages, context, provider):
    model = ModelRef(ProviderId("configured"), "model")
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
    gateway = RoutedModelGateway(
        registry, RoutingConfiguration(), ConfiguredGateways({model: provider})
    )
    return GroupChatReplyService(messages, context, gateway, registry.usage_bounder(), model, 80)


def test_at_mention_skips_selector_and_finishes_after_one_reply(tmp_path):
    async def run():
        db, group, messages, context = await _environment(tmp_path)
        try:
            target = next(p for p in group.participants if p.character_name == "角色乙")
            provider = ScriptedProvider(("乙的回复", "STOP"))
            sent = await messages.send_group_player(
                RequestId(uuid4()), group.conversation_id, "@角色乙 你好", 500
            )
            finished = await _service(messages, context, provider).reply(sent)
            assert finished.state == "completed"
            assert [(reply.sender_id, reply.text) for reply in finished.replies] == [
                (target.character_id, "乙的回复")
            ]
            assert provider.calls == 2
            assert await messages.group_turn(group.conversation_id, sent.turn_id) == finished
        finally:
            await db.close()

    asyncio.run(run())


def test_group_http_send_reply_and_retry_keep_one_durable_turn(tmp_path):
    db, group, messages, context = asyncio.run(_environment(tmp_path))
    provider = ScriptedProvider(("乙的回复", "STOP"))
    app = create_app(
        RuntimeStatus("test", "generation"),
        ShutdownRequests(),
        "secret",
        lambda: None,
        StructuredLogger(io.StringIO()),
        chat_messages=messages,
        group_chat_reply=_service(messages, context, provider),
    )
    base = f"/api/v1/worlds/{group.conversation_id.world_id.value}/conversations"
    path = f"{base}/{group.conversation_id.value}"
    headers = {"Authorization": "Bearer secret", "X-Request-Id": str(uuid4())}
    try:
        with TestClient(app, base_url="http://127.0.0.1") as client:
            assert client.get(path + "/messages").status_code == 401
            assert client.get(
                base + "/group-reply-availability",
                headers=headers,
            ).json() == {"available": True}
            sent = client.post(
                path + "/group-messages",
                headers=headers,
                json={"text": "@角色乙 你好", "token_ceiling": 500},
            )
            assert sent.status_code == 202
            assert (
                client.post(
                    path + "/group-messages",
                    headers=headers,
                    json={"text": "@角色乙 你好", "token_ceiling": 500},
                ).json()
                == sent.json()
            )
            turn = path + f"/group-turns/{sent.json()['turn_id']}"
            assert client.get(turn, headers=headers).json()["state"] == "pending"
            finished = client.post(turn + "/reply", headers=headers)
            assert finished.status_code == 200
            assert finished.json()["state"] == "completed"
            assert [reply["text"] for reply in finished.json()["replies"]] == ["乙的回复"]
            assert client.post(turn + "/reply", headers=headers).json() == finished.json()
            assert provider.calls == 2
            assert len(client.get(path + "/messages", headers=headers).json()) == 2
    finally:
        asyncio.run(db.close())


def test_selector_can_choose_multiple_speakers_under_one_turn_budget(tmp_path):
    async def run():
        db, group, messages, context = await _environment(tmp_path)
        try:
            first, second = group.participants
            provider = ScriptedProvider(
                (
                    str(first.character_id.value),
                    "甲的回复",
                    str(second.character_id.value),
                    "乙的回复",
                    "STOP",
                )
            )
            sent = await messages.send_group_player(
                RequestId(uuid4()), group.conversation_id, "大家怎么看？", 500
            )
            finished = await _service(messages, context, provider).reply(sent)
            assert finished.state == "completed"
            assert [(reply.sender_id, reply.text) for reply in finished.replies] == [
                (first.character_id, "甲的回复"),
                (second.character_id, "乙的回复"),
            ]
            assert provider.calls == 5
        finally:
            await db.close()

    asyncio.run(run())


def test_unaffordable_selection_rejects_before_claim_or_provider(tmp_path):
    async def run():
        db, group, messages, context = await _environment(tmp_path)
        try:
            provider = ScriptedProvider(())
            sent = await messages.send_group_player(
                RequestId(uuid4()), group.conversation_id, "大家好", 100
            )
            with pytest.raises(ChatReplyBudgetError, match="turn_token_limit_exceeded"):
                await _service(messages, context, provider).reply(sent)
            assert provider.calls == 0
            assert (
                await messages.group_turn(group.conversation_id, sent.turn_id)
            ).state == "pending"
        finally:
            await db.close()

    asyncio.run(run())


def test_remaining_budget_stops_new_selector_after_first_reply(tmp_path):
    async def run():
        db, group, messages, context = await _environment(tmp_path)
        try:
            first = group.participants[0]
            provider = ScriptedProvider((str(first.character_id.value), "第一条回复"))
            sent = await messages.send_group_player(
                RequestId(uuid4()), group.conversation_id, "大家好", 130
            )
            finished = await _service(messages, context, provider).reply(sent)
            assert finished.state == "completed"
            assert len(finished.replies) == 1
            assert provider.calls == 2
        finally:
            await db.close()

    asyncio.run(run())


def test_unknown_selector_usage_closes_budget_without_starting_a_reply(tmp_path):
    async def run():
        db, group, messages, context = await _environment(tmp_path)
        try:
            provider = ScriptedProvider((str(group.participants[0].character_id.value),))
            provider.usage = None
            sent = await messages.send_group_player(
                RequestId(uuid4()), group.conversation_id, "大家好", 500
            )
            with pytest.raises(ChatReplyBudgetError, match="turn_token_limit_exceeded"):
                await _service(messages, context, provider).reply(sent)
            assert provider.calls == 1
            turn = await messages.group_turn(group.conversation_id, sent.turn_id)
            assert turn.state == "claimed" and turn.replies == ()
        finally:
            await db.close()

    asyncio.run(run())


def test_selector_cannot_send_as_nonparticipant(tmp_path):
    async def run():
        db, group, messages, context = await _environment(tmp_path)
        try:
            provider = ScriptedProvider((str(uuid4()),))
            sent = await messages.send_group_player(
                RequestId(uuid4()), group.conversation_id, "大家好", 500
            )
            with pytest.raises(ChatReplyValidationError, match="group_selection_invalid"):
                await _service(messages, context, provider).reply(sent)
            assert provider.calls == 1
            turn = await messages.group_turn(group.conversation_id, sent.turn_id)
            assert turn.state == "claimed" and turn.replies == ()
        finally:
            await db.close()

    asyncio.run(run())
