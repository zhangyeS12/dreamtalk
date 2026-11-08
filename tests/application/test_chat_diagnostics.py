"""Synthetic failures, correlated stages and content-free diagnostics only."""

import asyncio
import io
import json
import sqlite3
from uuid import uuid4

import pytest
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.testclient import TestClient
from livingworld.adapters.http.chat_diagnostics import diagnostic_route
from livingworld.application.chat_diagnostics import chat_diagnostic_scope, chat_phase
from livingworld.application.chat_reply import (
    ChatReplyGenerationError,
    ChatReplyValidationError,
    _generation_error,
)
from livingworld.application.llm import (
    DispatchState,
    LLMError,
    LLMErrorCode,
    LLMFailure,
)
from livingworld.infrastructure.logging import StructuredLogger
from test_chat_reply import _Gateway, _sent, _service

CANARY = "PRIVATE-CONTENT-KEY-AND-EXCEPTION-CANARY"


def records(stream):
    value = stream.getvalue()
    assert CANARY not in value
    return [json.loads(line) for line in value.splitlines()]


@pytest.mark.parametrize("phase", ["context", "preflight", "persist_reply"])
def test_direct_unexpected_failures_record_stage_and_turn_without_exception_payload(phase):
    async def run():
        sent, character = _sent()
        stream, calls = io.StringIO(), []
        service = _service(sent, character, _Gateway(calls), calls)
        service._logger = StructuredLogger(stream)

        async def fail(*args, **kwargs):
            raise RuntimeError(CANARY)

        if phase == "context":
            service._context.build = fail
        elif phase == "preflight":

            def fail_plan(*args, **kwargs):
                raise RuntimeError(CANARY)

            service._gateway.plan = fail_plan
        else:
            service._messages.complete_direct = fail
        with pytest.raises(RuntimeError, match=CANARY):
            await service.reply(sent)
        (row,) = records(stream)
        assert row["stage"] == phase and row["kind"] == "direct"
        assert row["turn_id"] == str(sent.turn_id.value)
        assert row["code"] == "unexpected_error" and row["error_type"] == "RuntimeError"
        assert row["frames"] and all(f["module"].startswith("livingworld.") for f in row["frames"])
        assert calls.count("generate") == (1 if phase == "persist_reply" else 0)

    asyncio.run(run())


def test_decode_failure_has_exact_safe_reason_and_one_event_across_http_and_service():
    async def run():
        sent, character = _sent()
        stream, calls = io.StringIO(), []
        logger = StructuredLogger(stream)
        service = _service(sent, character, _Gateway(calls, text='{"memories":[]}'), calls)
        service._event_capture, service._logger = True, logger
        with pytest.raises(ChatReplyValidationError):
            with chat_diagnostic_scope(None, endpoint="reply_direct"):
                await service.reply(sent)
        (row,) = records(stream)
        assert row["stage"] == "reply_decode" and row["reason"] == "missing_reply"
        assert row["code"] == "chat_reply_format_invalid" and row["finish_reason"] == "stop"
        assert row["invocation_id"] and row["endpoint"] == "reply_direct"
        assert row["private_context"] is False and row["reply_shape"] == "missing_body"
        assert calls.count("generate") == 1 and "complete" not in calls

    asyncio.run(run())


@pytest.mark.parametrize("private", [False, True])
def test_missing_body_diagnostics_distinguish_private_contract_without_logging_values(private):
    from dataclasses import replace

    from livingworld.application.chat_event_annotations import annotate_request
    from livingworld.application.chat_reply import dialogue_text
    from livingworld.application.llm import FinishReason
    from livingworld.application.llm_chat_turn_budget import ChatTurnTokenBudget
    from test_chat_reply_formats import _Gateway as BodyGateway
    from test_chat_reply_formats import _request

    async def run():
        stream = io.StringIO()
        request = annotate_request(_request(False), private=private)
        request = replace(request, metadata={**request.metadata, "chat_kind": "group"})
        with pytest.raises(ChatReplyValidationError):
            with chat_diagnostic_scope(StructuredLogger(stream), kind="group", operation="reply"):
                await dialogue_text(
                    BodyGateway(json.dumps({"memories": [], "unknown": CANARY}), FinishReason.STOP),
                    request,
                    ChatTurnTokenBudget(50000),
                    None,
                    None,
                    _sent()[1],
                )
        (row,) = records(stream)
        assert row["reason"] == "missing_reply" and row["reply_shape"] == "missing_body"
        assert row["private_context"] is private

    asyncio.run(run())


@pytest.mark.parametrize(
    ("key", "shape"), [("message_parts", "history_parts"), ("content", "text_body")]
)
def test_diagnostics_recognize_unsupported_shapes_without_treating_them_as_dialogue(key, shape):
    from livingworld.application.chat_event_annotations import decode_optional_dialogue

    stream = io.StringIO()
    with pytest.raises(ValueError):
        with chat_diagnostic_scope(StructuredLogger(stream)):
            decode_optional_dialogue(json.dumps({key: CANARY}), private=True)
    (row,) = records(stream)
    assert row["reason"] == "missing_reply" and row["reply_shape"] == shape


def test_provider_category_and_http_status_survive_mapping_without_diagnostics_payload():
    async def run():
        sent, character = _sent()
        stream, calls = io.StringIO(), []
        gateway = _Gateway(calls)

        async def fail(request, **kwargs):
            raise LLMError(
                LLMFailure(
                    LLMErrorCode.PROVIDER_UNAVAILABLE,
                    request.invocation_id,
                    dispatch_state=DispatchState.HTTP_RESPONSE_RECEIVED,
                    http_status=503,
                )
            )

        gateway.generate = fail
        service = _service(sent, character, gateway, calls)
        service._logger = StructuredLogger(stream)
        with pytest.raises(ChatReplyGenerationError):
            await service.reply(sent)
        (row,) = records(stream)
        assert row["stage"] == "reply_generate"
        assert row["provider_code"] == "provider_unavailable" and row["http_status"] == 503

    asyncio.run(run())


def test_database_failure_records_sqlite_code_without_sql_or_parameters():
    stream = io.StringIO()
    with pytest.raises(sqlite3.IntegrityError):
        with chat_diagnostic_scope(StructuredLogger(stream), kind="direct", operation="reply"):
            chat_phase("persist_memories")
            with sqlite3.connect(":memory:") as connection:
                connection.execute("create table sample(value text unique)")
                connection.execute("insert into sample values (?)", (CANARY,))
                connection.execute("insert into sample values (?)", (CANARY,))
    (row,) = records(stream)
    assert (
        row["stage"] == "persist_memories"
        and row["database_code"] == sqlite3.SQLITE_CONSTRAINT_UNIQUE
    )
    assert "insert into" not in stream.getvalue()


def test_builtin_validation_error_keeps_a_known_code_without_allowing_arbitrary_messages():
    stream = io.StringIO()
    with pytest.raises(ValueError, match="chat_privacy_invalid"):
        with chat_diagnostic_scope(StructuredLogger(stream)):
            raise ValueError("chat_privacy_invalid")
    (row,) = records(stream)
    assert row["code"] == "chat_privacy_invalid" and row["error_type"] == "ValueError"


def test_stream_failure_preserves_provider_facts_without_a_raised_llm_exception():
    from livingworld.application.llm import InvocationId

    stream = io.StringIO()
    failure = LLMFailure(
        LLMErrorCode.RATE_LIMITED,
        InvocationId(uuid4()),
        dispatch_state=DispatchState.HTTP_RESPONSE_RECEIVED,
        http_status=429,
    )
    with pytest.raises(ChatReplyGenerationError):
        with chat_diagnostic_scope(StructuredLogger(stream), kind="group", operation="reply"):
            chat_phase("reply_generate")
            raise _generation_error(failure)
    (row,) = records(stream)
    assert row["provider_code"] == "rate_limited" and row["http_status"] == 429
    assert row["dispatch_state"] == "http_response_received"


def test_http_validation_and_save_rejections_are_logged_without_request_contents():
    stream = io.StringIO()
    app, router = FastAPI(), APIRouter(route_class=diagnostic_route(StructuredLogger(stream)))

    @router.get("/sample/{number}")
    async def sample(number: int):
        raise HTTPException(400, "chat_privacy_target_required")

    app.include_router(router)
    with TestClient(app) as client:
        assert client.get("/sample/1").status_code == 400
        assert client.get("/sample/" + CANARY).status_code == 422
    first, second = records(stream)
    assert first["code"] == "chat_privacy_target_required" and first["http_status"] == 400
    assert second["error_type"] == "RequestValidationError" and second["http_status"] == 422
    assert first["endpoint"] == second["endpoint"] == "sample"
    assert first["trace_id"] != second["trace_id"]


def test_diagnostic_write_failure_cannot_change_reply_or_original_error():
    class BrokenLogger:
        def emit_chat_diagnostic(self, **kwargs):
            raise OSError(CANARY)

    async def run():
        sent, character = _sent()
        calls = []
        service = _service(sent, character, _Gateway(calls, text=""), calls)
        service._logger = BrokenLogger()
        with pytest.raises(ChatReplyValidationError, match="chat_reply_empty"):
            await service.reply(sent)
        assert calls.count("generate") == 1

    asyncio.run(run())


@pytest.mark.parametrize("stage", ["media_context", "media"])
def test_optional_media_failure_records_its_cause_and_keeps_text_path_available(stage):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from livingworld.application.chat_media import ChatMediaService

    stream = io.StringIO()
    store = SimpleNamespace(
        prompt_context=AsyncMock(side_effect=RuntimeError(CANARY)),
        select_for_reply=AsyncMock(side_effect=RuntimeError(CANARY)),
    )
    service = ChatMediaService(store, SimpleNamespace(), StructuredLogger(stream))
    with chat_diagnostic_scope(service.logger, kind="direct", operation="reply"):
        if stage == "media_context":
            assert asyncio.run(service.context(None, None))["media_allowed"] is False
        else:
            assert asyncio.run(service.resolve(None, None, object())) is None
    (row,) = [r for r in records(stream) if r["component"] == "chat"]
    assert row["stage"] == stage and row["error_type"] == "RuntimeError"


def test_summary_failure_has_diagnostics_without_requiring_a_model_call():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from livingworld.application.conversation_memory import ConversationMemoryService

    async def run():
        sent, _ = _sent()
        request = uuid4()
        draft = {"state": "failed", "draft_id": str(request)}
        store = SimpleNamespace(
            claim=AsyncMock(return_value=(True, draft)),
            finish=AsyncMock(),
            draft=AsyncMock(return_value=draft),
        )
        players = SimpleNamespace(selected_player=AsyncMock(return_value=sent.message.sender_id))
        service = ConversationMemoryService(store, players)
        stream = io.StringIO()
        with chat_diagnostic_scope(StructuredLogger(stream), endpoint="generate_summary"):
            result = await service.generate(sent.message.conversation_id, request, 0, "summarize")
        assert result["state"] == "failed"
        (row,) = records(stream)
        assert row["stage"] == "summary_generate" and row["code"] == "memory_model_unavailable"
        store.finish.assert_awaited_once()

    asyncio.run(run())


def test_parallel_attempts_do_not_mix_trace_turn_or_invocation_ids():
    async def run():
        stream = io.StringIO()
        services, sends = [], []
        for _ in range(2):
            sent, character = _sent()
            calls = []
            service = _service(sent, character, _Gateway(calls, text=""), calls)
            service._logger = StructuredLogger(stream)
            services.append(service)
            sends.append(sent)
        errors = await asyncio.gather(
            *(s.reply(t) for s, t in zip(services, sends, strict=True)), return_exceptions=True
        )
        assert all(isinstance(e, ChatReplyValidationError) for e in errors)
        rows = records(stream)
        assert {r["turn_id"] for r in rows} == {str(t.turn_id.value) for t in sends}
        assert len({r["trace_id"] for r in rows}) == len({r["invocation_id"] for r in rows}) == 2

    asyncio.run(run())


def test_partial_group_failure_keeps_prior_reply_and_blocks_replay(tmp_path):
    from livingworld.application.errors import ChatTurnUnavailableError
    from livingworld.application.group_chat_reply import GroupChatReplyService
    from livingworld.domain.contracts import RequestId
    from test_group_chat_reply import _environment
    from test_scheduler_model import RecordingProvider, route

    async def run():
        db, group, messages, context = await _environment(tmp_path)
        try:
            one, two = group.participants
            stream = io.StringIO()
            provider = RecordingProvider(
                (json.dumps({"reply": "SAVED_REPLY"}), '{"reply":"unfinished')
            )
            selector = RecordingProvider((str(two.character_id.value),))
            service = GroupChatReplyService(
                messages,
                context,
                *route(provider, "body"),
                scheduler_configuration=route(selector, "scheduler"),
                event_capture=True,
                logger=StructuredLogger(stream),
            )
            sent = await messages.send_group_player(
                RequestId(uuid4()), group.conversation_id, f"@{one.character_name} 合成问题", 50000
            )
            with pytest.raises(ChatReplyValidationError):
                await service.reply(sent)
            view = await messages.group_turn(group.conversation_id, sent.turn_id)
            assert [message.text for message in view.replies] == ["SAVED_REPLY"]
            recovery = await messages.reply_recovery(group.conversation_id, sent.turn_id)
            assert not recovery["can_create"] and recovery["reason"] == "chat_recovery_has_replies"
            (row,) = [r for r in records(stream) if r.get("code") == "chat_reply_format_invalid"]
            assert row["stage"] == "reply_decode" and row["ordinal"] == 1
            assert row["reason"] == "invalid_json"
            with pytest.raises(ChatTurnUnavailableError):
                await service.reply(sent)
            assert provider.calls == 2 and selector.calls == 1
        finally:
            await db.close()

    asyncio.run(run())


def test_failed_first_reply_allows_only_explicit_idempotent_new_attempt(tmp_path):
    from livingworld.application.group_chat_reply import GroupChatReplyService
    from livingworld.domain.contracts import RequestId
    from test_group_chat_reply import _environment
    from test_scheduler_model import RecordingProvider, route

    async def run():
        db, group, messages, context = await _environment(tmp_path)
        try:
            one = group.participants[0]
            provider, selector = RecordingProvider(('{"reply":"unfinished',)), RecordingProvider(())
            service = GroupChatReplyService(
                messages,
                context,
                *route(provider, "body"),
                scheduler_configuration=route(selector, "scheduler"),
                event_capture=True,
            )
            sent = await messages.send_group_player(
                RequestId(uuid4()), group.conversation_id, f"@{one.character_name} 合成问题", 50000
            )
            with pytest.raises(ChatReplyValidationError):
                await service.reply(sent)
            recovery = await messages.reply_recovery(group.conversation_id, sent.turn_id)
            assert recovery["can_create"] and recovery["state"] == "failed"
            receipt = RequestId(uuid4())
            first = await messages.create_reply_recovery(
                receipt, group.conversation_id, sent.turn_id, sent.turn_id.value, 50000
            )
            repeat = await messages.create_reply_recovery(
                receipt, group.conversation_id, sent.turn_id, sent.turn_id.value, 50000
            )
            assert first == repeat and first["turn_id"] != str(sent.turn_id.value)
            assert provider.calls == 1 and selector.calls == 0
            original = await messages.group_turn(group.conversation_id, sent.turn_id)
            assert original.replies == ()
        finally:
            await db.close()

    asyncio.run(run())


@pytest.mark.parametrize(
    "extra",
    [
        {"reason": CANARY},
        {"code": CANARY},
        {"provider_code": CANARY},
        {"error_type": CANARY},
        {"private_context": "false"},
        {"reply_shape": CANARY},
        {"endpoint": CANARY},
        {"frames": [{"module": CANARY, "function": "sample", "line": 1}]},
    ],
)
def test_logger_rejects_non_allowlisted_fields(extra):
    fields = dict(
        kind="direct",
        operation="reply",
        stage="reply_decode",
        code="chat_reply_invalid",
        outcome="failed",
        trace_id=str(uuid4()),
    )
    fields.update(extra)
    stream = io.StringIO()
    with pytest.raises(ValueError):
        StructuredLogger(stream).emit_chat_diagnostic(**fields)
    assert stream.getvalue() == ""
