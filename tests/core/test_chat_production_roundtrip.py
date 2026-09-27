"""A configured chat provider reaches a durable reply through production composition."""

import asyncio
import io
import json
from uuid import uuid4

import httpx
from card_fixtures import card_document, json_bytes
from livingworld.application.chat_context import DirectChatContextBuilder
from livingworld.application.chat_conversations import ChatConversationService
from livingworld.application.chat_messages import ChatMessageService
from livingworld.application.command_handler import CommandHandler
from livingworld.application.commands import CreateWorld
from livingworld.application.llm_accounting import AttemptOutcome, LedgerQuery
from livingworld.application.player_event_feed import PlayerEventFeedService
from livingworld.application.player_onboarding import LocalPlayerOnboardingService
from livingworld.application.simulation_clock import EffectiveWorldTimeSource, SystemMonotonicClock
from livingworld.bootstrap import llm_runtime as composition
from livingworld.domain.contracts import RequestId
from livingworld.domain.identifiers import WorldId
from livingworld.infrastructure.clock import SystemWallClock
from livingworld.infrastructure.llm.credentials import SessionCredentialProvider
from livingworld.infrastructure.llm.openai_compatible import OpenAICompatibleChatGateway
from livingworld.infrastructure.llm.production_config import load_configuration
from livingworld.infrastructure.logging import StructuredLogger
from livingworld.infrastructure.persistence import Database


def test_configured_compatible_api_creates_one_durable_chat_reply_and_accounted_attempt(
    tmp_path, monkeypatch
):
    secret_ref = str(uuid4())
    config_path = tmp_path / "llm.json"
    config_path.write_text(
        json.dumps(
            {
                "version": 1,
                "providers": [
                    {
                        "provider_id": "configured-chat",
                        "adapter_kind": "openai-compatible",
                        "base_url": "https://controlled.invalid/v1",
                        "secret_ref": secret_ref,
                    }
                ],
                "models": [
                    {
                        "provider_id": "configured-chat",
                        "model_id": "configured-model",
                        "capabilities": {"text_generation": True},
                        "limits": {
                            "max_billable_input_tokens": 1000,
                            "max_output_tokens": 256,
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    calls = []
    persona_canary = "CARD_PERSONA_PRIVATE_CANARY"
    secret_canary = "CONTROLLED_TEST_SECRET"
    reply_text = "我记得你刚才问过的事。"

    async def wire(request):
        assert request.headers["authorization"] == f"Bearer {secret_canary}"
        assert str(request.url) == "https://controlled.invalid/v1/chat/completions"
        payload = json.loads(request.content)
        assert payload["model"] == "configured-model"
        assert persona_canary in json.dumps(payload, ensure_ascii=False)
        assert "你好" in json.dumps(payload, ensure_ascii=False)
        calls.append(payload)
        return httpx.Response(
            200,
            json={
                "object": "chat.completion",
                "model": "configured-model",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": reply_text},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 30, "completion_tokens": 10, "total_tokens": 40},
            },
        )

    def adapter(_model, configured, provider, credentials, logger):
        return OpenAICompatibleChatGateway(
            provider.config,
            credentials,
            profile=configured.profile,
            transport=httpx.MockTransport(wire),
            logger=logger,
        )

    monkeypatch.setattr(composition, "_factory", adapter)

    async def run():
        db = Database(tmp_path / "data")
        await db.initialize()
        log = io.StringIO()
        logger = StructuredLogger(log)
        config = load_configuration(config_path)
        credentials = SessionCredentialProvider(config.secret_refs)
        runtime = await composition.build_production_llm_runtime(
            config, db, logger, credentials=credentials
        )
        credentials.upsert(config.secret_refs[0], secret_canary)
        session = composition.ProductionLLMSession(credentials, runtime)
        try:
            clock = SystemWallClock()
            handler = CommandHandler(
                db.unit_of_work,
                clock,
                world_time_source=EffectiveWorldTimeSource(clock, SystemMonotonicClock()),
            )
            world = WorldId(uuid4())
            await handler.execute(
                CreateWorld(request_id=RequestId(uuid4()), world_id=world, name="测试世界")
            )
            players = PlayerEventFeedService(db.player_event_feed_store())
            await LocalPlayerOnboardingService(handler, players).start_at_home(world)
            imports = db.world_content_service()
            card_data = card_document()
            card_data["data"]["description"] = persona_canary
            staged = await imports.prepare(world, "character", json_bytes(card_data))
            card = await imports.commit(world, staged.item.import_id, staged.item.reviewed_hash)
            conversations = ChatConversationService(
                db.chat_conversation_store(), imports, players, handler
            )
            conversation = await conversations.open_direct(world, card.import_id)
            messages = ChatMessageService(db.chat_message_store(), players)
            sent = await messages.send_player(
                RequestId(uuid4()), conversation.conversation_id, "你好", 5000
            )
            reply_service = composition.configure_direct_chat_reply(
                session,
                messages,
                DirectChatContextBuilder(
                    conversations, messages, db.local_profile_store(), db.character_memory_reader
                ),
            )
            assert reply_service is not None and reply_service.available
            reply = await reply_service.reply(sent)
            assert reply.text == reply_text
            assert reply.sender_id == conversation.character_id
            assert (
                await messages.direct_turn(conversation.conversation_id, sent.turn_id)
            ).reply == reply
            assert len(calls) == 1
            rows = await db.llm_usage_ledger().query(LedgerQuery())
            assert len(rows) == 1
            assert rows[0].outcome is AttemptOutcome.SUCCESS
            assert rows[0].start.requested_model.model_id == "configured-model"
            assert rows[0].facts.usage.input_tokens == 30
            assert rows[0].facts.usage.output_tokens == 10
            assert all(
                canary not in repr(rows) for canary in (secret_canary, persona_canary, reply_text)
            )
            assert all(
                canary not in log.getvalue()
                for canary in (secret_canary, persona_canary, reply_text)
            )
        finally:
            await runtime.aclose()
            await db.close()

    asyncio.run(run())
