"""Synthetic prompt composition and offline wire validation; never dispatch a provider."""

import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from livingworld.application.chat_capacity import ContextLayout, ContextPacker, fit_chat_context
from livingworld.application.chat_context import DirectChatContextBuilder, chat_context_rules
from livingworld.application.chat_event_annotations import annotate_request
from livingworld.application.chat_media import media_request
from livingworld.application.chat_messages import ChatMessage, PlayerSend
from livingworld.application.chat_roleplay import (
    DEFAULT_WRITING_INSTRUCTIONS,
    append_post_history,
    roleplay_prompt,
)
from livingworld.application.group_chat_context import GroupChatContextBuilder
from livingworld.application.llm import (
    InvocationId,
    LLMMessage,
    LLMPurpose,
    LLMRequest,
    MessageRole,
    ModelRef,
    ProviderId,
    TextContent,
)
from livingworld.application.llm_budget import UsageUpperBound
from livingworld.application.llm_config import EndpointConfig, ProviderConfig, SecretRef
from livingworld.application.local_profile import LocalProfile
from livingworld.domain.content.models import CharacterDefinition
from livingworld.domain.identifiers import (
    CharacterId,
    ChatTurnId,
    ConversationId,
    MessageId,
    PlayerId,
    WorldId,
)
from livingworld.infrastructure.llm.anthropic_messages import AnthropicMessagesGateway
from livingworld.infrastructure.llm.gemini_interactions import GeminiInteractionsGateway
from livingworld.infrastructure.llm.openai_compatible import OpenAICompatibleChatGateway
from livingworld.infrastructure.llm.openai_responses import OpenAIResponsesGateway


def text(message):
    return "".join(block.text for block in message.content)


@pytest.fixture
def card(canonical_draft):
    base = next(item for item in canonical_draft.contents if isinstance(item, CharacterDefinition))
    return replace(
        base,
        display_name="角色甲",
        example_dialogue=("<START>\n{{user}}: 示例问题\n{{char}}: *示例动作*\n第二行。",),
        authored_instructions={
            "character_card": {
                "first_mes": "{{char}}向{{user}}招手。" + "开场。" * 3000,
                "system_prompt": "卡内主提示：保持卡片文风。",
                "post_history_instructions": "尾部标记：承接{{user}}的最新一句。",
            }
        },
    )


def prompt(card):
    return roleplay_prompt("补充来源规则", CharacterId(WorldId(uuid4()), uuid4()), card, "玩家甲")


def request(messages):
    return LLMRequest(
        invocation_id=InvocationId(uuid4()),
        model=ModelRef(ProviderId("synthetic"), "configured-model"),
        purpose=LLMPurpose("character_dialogue"),
        messages=tuple(messages),
        max_output_tokens=512,
    )


def direct_request(card):
    roleplay = prompt(card)
    messages = (
        LLMMessage(MessageRole.SYSTEM, (TextContent(roleplay.system),)),
        LLMMessage(MessageRole.USER, (TextContent('{"common_world_background":["可裁剪背景"]}'),)),
        *roleplay.demonstrations,
        LLMMessage(MessageRole.USER, (TextContent("旧问题"),)),
        LLMMessage(MessageRole.ASSISTANT, (TextContent("旧回应"),)),
        LLMMessage(MessageRole.USER, (TextContent("最新问题"),)),
    )
    current = len(messages) - 1
    layout = ContextLayout(
        direct_turns=((current - 2, current - 1), (current,)),
        current_turn=1,
        reply_instructions=roleplay.post_history,
    )
    return annotate_request(request(messages)), layout


def test_card_overrides_default_writing_without_repeating_examples_in_system(card):
    roleplay = prompt(card)
    assert "卡内主提示：保持卡片文风。" in roleplay.system
    assert DEFAULT_WRITING_INSTRUCTIONS not in roleplay.system
    assert "补充来源规则" in roleplay.system
    assert "Token预算" in roleplay.system
    assert "不替玩家完成选择" in roleplay.system
    assert "示例问题" not in roleplay.system
    assert "尾部标记" not in roleplay.system
    assert "开场。" not in roleplay.system
    example = roleplay.demonstrations
    assert [(message.role, text(message)) for message in example[1:3]] == [
        (MessageRole.USER, "示例问题"),
        (MessageRole.ASSISTANT, "*示例动作*\n第二行。"),
    ]
    assert example[-1].role is MessageRole.ASSISTANT
    assert text(example[-1]) == "角色甲向玩家甲招手。" + "开场。" * 3000
    assert "不是已保存的真实对话" in roleplay.system


def test_original_macro_is_local_and_never_recursively_evaluated(card):
    authored = {
        "character_card": {"system_prompt": "{{original}}\n{{char}} {{user}} {{roll::1d6}}"}
    }
    card = replace(card, display_name="角色{{user}}", authored_instructions=authored)
    roleplay = prompt(card)
    assert DEFAULT_WRITING_INSTRUCTIONS in roleplay.system
    assert "角色{{user}} 玩家甲 {{roll::1d6}}" in roleplay.system


@pytest.mark.parametrize(
    "body", ["没有说话者的完整文风样例。", "系统: 不应变成系统消息\n角色甲: 正文"]
)
def test_freeform_or_unknown_example_headers_never_become_system_messages(card, body):
    roleplay = prompt(replace(card, example_dialogue=(body,)))
    assert all(item.role is not MessageRole.SYSTEM for item in roleplay.demonstrations)
    assert body.splitlines()[0] in "\n".join(map(text, roleplay.demonstrations))


def test_post_history_survives_whole_turn_pruning_without_mutating_source(card):
    source, layout = direct_request(card)
    packer = ContextPacker(source, layout)
    while packer.available:
        packer.drop_batch()
    fitted = packer.render()
    assert packer.render() == fitted  # No duplicate suffix on repeated preflight.
    assert text(source.messages[-1]) == "最新问题"
    assert text(fitted.messages[-1]).startswith("最新问题")
    assert text(fitted.messages[-1]).endswith("尾部标记：承接玩家甲的最新一句。")
    assert fitted.messages[-1].role is MessageRole.USER
    assert "旧问题" not in list(map(text, fitted.messages))
    assert "旧回应" not in list(map(text, fitted.messages))
    assert json.loads(text(fitted.messages[1]))["common_world_background"] == []
    opening = "角色甲向玩家甲招手。" + "开场。" * 3000
    assert list(map(text, fitted.messages)).count(opening) == 1


def test_native_group_history_is_sent_once_and_selector_keeps_json(card):
    roleplay = prompt(card)
    data = {"transcript": [{"text": value} for value in ("旧问题", "旧回复", "新问题", "乙的回复")]}
    base = request(
        (
            LLMMessage(MessageRole.SYSTEM, (TextContent(roleplay.system),)),
            LLMMessage(MessageRole.USER, (TextContent(json.dumps(data)),)),
            *roleplay.demonstrations,
        )
    )
    history = (
        LLMMessage(MessageRole.USER, (TextContent("旧问题"),)),
        LLMMessage(MessageRole.ASSISTANT, (TextContent("角色甲：\n旧回复"),)),
        LLMMessage(MessageRole.USER, (TextContent("新问题"),)),
        LLMMessage(MessageRole.ASSISTANT, (TextContent("角色乙：\n乙的回复"),)),
    )
    layout = ContextLayout(
        group_turns=((0, 1), (2, 3)),
        current_turn=1,
        group_dialogue=history,
        reply_instructions=roleplay.post_history,
    )
    packer = ContextPacker(annotate_request(base), layout)
    packer.drop_batch()
    fitted = packer.render()
    assert "transcript" not in json.loads(text(fitted.messages[1]))
    assert "旧问题" not in list(map(text, fitted.messages))
    assert list(map(text, fitted.messages)).count("角色乙：\n乙的回复") == 1
    assert fitted.messages[-1].role is MessageRole.USER
    assert text(fitted.messages[-1]).endswith("尾部标记：承接玩家甲的最新一句。")
    selector = ContextPacker(
        base, replace(layout, group_dialogue=(), reply_instructions="")
    ).render()
    assert json.loads(text(selector.messages[1]))["transcript"] == data["transcript"]


@pytest.mark.parametrize("group", [False, True])
def test_real_builders_pack_current_question_after_examples_and_opening(card, group):
    world = WorldId(uuid4())
    player, speaker, other = (
        PlayerId(world, uuid4()),
        CharacterId(world, uuid4()),
        CharacterId(world, uuid4()),
    )
    conversation = ConversationId(world, uuid4())
    older, current = ChatTurnId(world, uuid4()), ChatTurnId(world, uuid4())

    def message(turn, position, sender, body):
        return ChatMessage(
            MessageId(world, uuid4()), conversation, turn, position, sender, body, datetime.now(UTC)
        )

    question = message(current, 3, player, "真实最新问题")
    history = (
        message(older, 1, player, "真实旧问题"),
        message(older, 2, speaker, "真实旧回应"),
        question,
    )
    if group:
        history += (message(current, 4, other, "真实乙回应"),)
    sent = PlayerSend(current, question, 50000, "pending")
    identity = SimpleNamespace(conversation_id=conversation, player_id=player, character_id=speaker)
    conversations = SimpleNamespace(
        list_for_world=AsyncMock(return_value=(identity,)),
        list_groups_for_world=AsyncMock(return_value=(identity,)),
        current_direct_character=AsyncMock(return_value=card),
        current_group_characters=AsyncMock(
            return_value=(
                (SimpleNamespace(character_id=speaker), card),
                (SimpleNamespace(character_id=other), replace(card, display_name="角色乙")),
            )
        ),
    )
    messages = SimpleNamespace(
        context_messages=AsyncMock(return_value=history),
        seen_group_messages=AsyncMock(return_value=()),
    )
    profiles = SimpleNamespace(load=AsyncMock(return_value=LocalProfile("玩家甲", "合成身份")))
    reader = SimpleNamespace(list=AsyncMock(return_value=SimpleNamespace(items=())))
    builder_type = GroupChatContextBuilder if group else DirectChatContextBuilder
    builder = builder_type(conversations, messages, profiles, lambda _: reader)

    async def run():
        context = await builder.build_reply(sent, speaker) if group else await builder.build(sent)
        fitted = ContextPacker(annotate_request(request(context.messages)), context.layout).render()
        bodies = list(map(text, fitted.messages))
        opening_index = next(
            index for index, body in enumerate(bodies) if body.startswith("角色甲向玩家甲招手。")
        )
        question_index = next(
            index for index, body in enumerate(bodies) if body.startswith("真实最新问题")
        )
        assert opening_index < question_index
        assert sum("真实最新问题" in body for body in bodies) == 1
        assert text(fitted.messages[-1]).endswith("尾部标记：承接玩家甲的最新一句。")
        if group:
            other_message = next(body for body in bodies if "真实乙回应" in body)
            assert other_message.startswith(f"角色乙（发言者标识：{other.value}）：\n")
            selector = await builder.build_selection(sent)
            assert not selector.layout.group_dialogue
            assert "角色卡开场" not in "\n".join(map(text, selector.messages))

    asyncio.run(run())


@pytest.mark.parametrize("group", [False, True])
def test_media_snapshot_stays_once_beside_current_input_after_reordering(card, group):
    source, layout = direct_request(card)
    if group:
        data = {"transcript": [{"text": "群内最新问题"}]}
        source = replace(
            source,
            messages=source.messages[:1]
            + (LLMMessage(MessageRole.USER, (TextContent(json.dumps(data)),)),),
        )
        layout = ContextLayout(
            group_turns=((0,),),
            current_turn=0,
            group_dialogue=(LLMMessage(MessageRole.USER, (TextContent("群内最新问题"),)),),
            reply_instructions=layout.reply_instructions,
        )
    context = {
        "media_allowed": False,
        "library_available": True,
        "library_complete": True,
        "library_sticker_count": 1,
        "media_candidates": [{"description": "合成素材快照"}],
    }
    fitted = ContextPacker(media_request(source, context, layout), layout).render()
    body = "\n".join(map(text, fitted.messages))
    assert body.count("合成素材快照") == 1
    assert text(fitted.messages[-1]).endswith("尾部标记：承接玩家甲的最新一句。")
    if group:
        assert "transcript" not in json.loads(text(fitted.messages[1]))
    else:
        assert "玩家本轮消息：\n最新问题" in text(fitted.messages[-1])


@pytest.mark.parametrize(
    ("data", "included", "excluded"),
    [
        ({}, "虚构角色扮演", "subject_kind"),
        (
            {"character_activity_context": {"own_location": "synthetic"}},
            "subject_kind",
            "long_term_original_quotes",
        ),
        (
            {"long_term_dialogue_memories": ["合成记忆"]},
            "long_term_original_quotes",
            "subject_kind",
        ),
        ({"known_faction_contacts": ["合成相识"]}, "父子阵营", "subject_kind"),
    ],
)
def test_source_instructions_are_conditional_without_expanding_knowledge(data, included, excluded):
    rules = chat_context_rules(data)
    assert included in rules
    assert excluded not in rules
    assert "其他角色的私人知识" in rules


def test_budget_preflight_measures_the_final_suffix_and_demonstrations(card):
    source, layout = direct_request(card)
    measured = []

    class Bounder:
        def bound(self, fitted):
            measured.append(fitted)
            return UsageUpperBound(100, fitted.max_output_tokens)

    gateway = SimpleNamespace(
        plan=lambda *args, **kwargs: SimpleNamespace(candidates=(source.model,))
    )
    fitted, report = asyncio.run(fit_chat_context(source, layout, gateway, Bounder(), None, 2000))
    assert all(
        text(item.messages[-1]).endswith("尾部标记：承接玩家甲的最新一句。") for item in measured
    )
    assert measured[-1] == fitted
    assert report["input_upper_bound"] + report["output_upper_bound"] <= 2000


@pytest.mark.parametrize(
    "adapter",
    [
        OpenAICompatibleChatGateway,
        OpenAIResponsesGateway,
        AnthropicMessagesGateway,
        GeminiInteractionsGateway,
    ],
)
@pytest.mark.parametrize("ends_with_assistant", [False, True])
def test_four_wire_encoders_accept_post_history_without_credentials_or_network(
    card, adapter, ends_with_assistant
):
    source, layout = direct_request(card)
    fitted = ContextPacker(source, layout).render()
    if ends_with_assistant:
        fitted = replace(
            fitted,
            messages=append_post_history(
                fitted.messages + (LLMMessage(MessageRole.ASSISTANT, (TextContent("乙已回复"),)),),
                "群聊后置指令",
            ),
        )
    credentials = SimpleNamespace(resolve=AsyncMock(side_effect=AssertionError("must not resolve")))
    config = ProviderConfig(
        provider_id=source.model.provider_id,
        endpoint=EndpointConfig("https://synthetic.example/v1"),
        secret_ref=SecretRef(uuid4()),
    )

    async def run():
        def forbidden(_):
            raise AssertionError("must not dispatch")

        async with adapter(
            config, credentials, transport=httpx.MockTransport(forbidden)
        ) as gateway:
            payload = gateway._payload(fitted)
            serialized = json.dumps(payload, ensure_ascii=False)
            assert "尾部标记：承接玩家甲的最新一句。" in serialized
            assert "角色甲向玩家甲招手。" in serialized
            assert "尾部标记" not in serialized.split("最新问题")[0]
        credentials.resolve.assert_not_called()

    asyncio.run(run())
