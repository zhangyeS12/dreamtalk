"""Offline group-span audiences, conservative model output, and durable derived sources."""

import asyncio
import io
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from livingworld.adapters.http.app import create_app
from livingworld.adapters.http.services import HttpServices
from livingworld.application.chat_event_annotations import (
    AnnotatedDialogue,
    decode_optional_dialogue,
)
from livingworld.application.chat_privacy import (
    boundaries,
    normalize_privacy,
    reply_privacy,
    validate_targets,
    visible_text,
)
from livingworld.application.errors import IdempotencyConflictError
from livingworld.application.group_chat_reply import GroupChatReplyService
from livingworld.application.long_chat_memory import MemoryAnnotation
from livingworld.application.runtime import RuntimeStatus, ShutdownRequests
from livingworld.domain.contracts import RequestId
from livingworld.infrastructure.logging import StructuredLogger
from livingworld.infrastructure.persistence.long_chat_memory import SqlAlchemyLongChatMemoryStore
from livingworld.infrastructure.persistence.long_memory_models import LongChatMemoryRecord
from sqlalchemy import select
from test_group_chat_reply import _environment
from test_recent_dialogue import bodies, direct, fitted
from test_scheduler_model import RecordingProvider, route


def span_for(text, person):
    return (
        {"start": 0, "end": max(boundaries(text)), "character_id": str(person.character_id.value)},
    )


def test_unicode_offsets_and_private_actions_are_filtered_before_use():
    owner, other = str(uuid4()), str(uuid4())
    text = "公开😀@甲（轻声）秘密随后公开"
    spans = ({"start": 4, "end": 12, "character_id": owner},)
    assert visible_text(text, spans, owner) == text
    assert visible_text(text, spans, other) == "公开😀随后公开"
    assert visible_text(text, spans) == "公开😀随后公开"
    with pytest.raises(ValueError):
        normalize_privacy(text, [{"start": 3, "end": 12, "character_id": owner}])


@pytest.mark.parametrize(
    "bad",
    [
        {"start": True, "end": 2},
        {"start": 2, "end": 1},
        {"start": 0, "end": 999},
        {"start": -1, "end": 2},
        {"start": 0, "end": 2, "extra": True},
    ],
)
def test_bad_ranges_are_rejected_not_reinterpreted_as_public(bad):
    with pytest.raises(ValueError):
        normalize_privacy("@甲 秘密", [{"character_id": str(uuid4()), **bad}])


def test_selected_span_requires_exactly_one_unambiguous_member():
    one, two = str(uuid4()), str(uuid4())
    text = "@甲（悄悄说）内容"
    span = ({"start": 0, "end": len(text), "character_id": one},)
    validate_targets(text, span, [(one, "甲"), (two, "乙")])
    for people in ([(one, "丙"), (two, "乙")], [(one, "甲"), (two, "甲")]):
        with pytest.raises(ValueError):
            validate_targets(text, span, people)


@pytest.mark.parametrize(
    "parts",
    [None, (), ({"text": "遗漏", "private": False},), ({"text": "秘密", "private": "false"},)],
)
def test_missing_or_invalid_model_markers_default_to_whole_private(parts):
    owner = SimpleNamespace(value=uuid4())
    dialogue = AnnotatedDialogue("秘密", privacy_parts=parts)
    assert visible_text(dialogue.text, reply_privacy(dialogue, owner)) == ""


def test_model_can_classify_reply_parts_without_choosing_audience():
    owner = SimpleNamespace(value=uuid4())
    decoded = decode_optional_dialogue(
        json.dumps(
            {
                "reply": "私密回应。公开回应。",
                "privacy_parts": [
                    {"text": "私密回应。", "private": True},
                    {"text": "公开回应。", "private": False},
                ],
            },
            ensure_ascii=False,
        )
    )
    spans = reply_privacy(decoded, owner)
    assert visible_text(decoded.text, spans) == "公开回应。"
    assert visible_text(decoded.text, spans, owner) == decoded.text


def test_private_input_reply_and_later_private_group_timeline_are_owner_scoped(tmp_path):
    async def run():
        db, group, messages, context = await _environment(tmp_path)
        try:
            one, two = group.participants
            secret = f"@{one.character_name}（轻声）INPUT_PRIVATE_CANARY。"
            text = secret + "PUBLIC_MEAL。"
            spans = span_for(secret, one)
            request = RequestId(uuid4())
            sent = await messages.send_group_player(
                request, group.conversation_id, text, 50000, privacy=spans
            )
            retried = await messages.send_group_player(
                request, group.conversation_id, text, 50000, privacy=spans
            )
            assert retried.message.privacy == spans and retried.turn_id == sent.turn_id
            with pytest.raises(IdempotencyConflictError):
                await messages.send_group_player(request, group.conversation_id, text, 50000)
            assert (await context.mentioned_character(sent)) == one.character_id
            for role in (two.character_id, None):
                built = (
                    await context.build_reply(sent, role)
                    if role
                    else await context.build_selection(sent)
                )
                rendered = bodies(fitted(built) if role else built)
                assert "INPUT_PRIVATE_CANARY" not in rendered
                assert "PUBLIC_MEAL" in rendered
            own = await context.build_reply(sent, one.character_id)
            assert own.private_context and "INPUT_PRIVATE_CANARY" in bodies(fitted(own))
            claim = await messages.claim_group(group.conversation_id, sent.turn_id)
            reply = "REPLY_PRIVATE_CANARY。PUBLIC_REPLY。"
            await messages.complete_group_reply(
                claim,
                one.character_id,
                0,
                reply,
                privacy=span_for("REPLY_PRIVATE_CANARY。", one),
                private_context=True,
            )
            await messages.finish_group(claim)
            loaded = await messages.list_messages(group.conversation_id)
            assert loaded[0].privacy == spans and loaded[1].privacy
            latest = await messages.send_group_player(
                RequestId(uuid4()), group.conversation_id, "NEXT_PUBLIC", 50000
            )
            for role in (one.character_id, two.character_id):
                body = bodies(fitted(await context.build_reply(latest, role)))
                assert ("INPUT_PRIVATE_CANARY" in body) == (role == one.character_id)
                assert ("REPLY_PRIVATE_CANARY" in body) == (role == one.character_id)
                assert "PUBLIC_REPLY" in body
                conversation = await context._conversations.open_direct(
                    group.conversation_id.world_id,
                    one.root_import_id if role == one.character_id else two.root_import_id,
                )
                current = await direct(messages, conversation, "现在呢？")
                recent = await messages.recent_dialogue(role, current.message)
                history = " ".join(entry.message.text for entry in recent)
                assert ("INPUT_PRIVATE_CANARY" in history) == (role == one.character_id)
                assert ("REPLY_PRIVATE_CANARY" in history) == (role == one.character_id)
        finally:
            await db.close()

    asyncio.run(run())


@pytest.mark.parametrize("structured", [False, True])
def test_same_call_model_visibility_and_selector_never_receive_private_reply(tmp_path, structured):
    async def run():
        db, group, messages, context = await _environment(tmp_path)
        try:
            one = group.participants[0]
            secret = f"@{one.character_name}（轻声）INPUT_PRIVATE_CANARY。"
            reply = "REPLY_PRIVATE_CANARY。PUBLIC_REPLY。"
            raw = (
                json.dumps(
                    {
                        "reply": reply,
                        "privacy_parts": [
                            {"text": "REPLY_PRIVATE_CANARY。", "private": True},
                            {"text": "PUBLIC_REPLY。", "private": False},
                        ],
                    },
                    ensure_ascii=False,
                )
                if structured
                else reply
            )
            provider, selector = RecordingProvider((raw,)), RecordingProvider(("STOP",))
            service = GroupChatReplyService(
                messages,
                context,
                *route(provider, "body"),
                scheduler_configuration=route(selector, "scheduler"),
            )
            sent = await messages.send_group_player(
                RequestId(uuid4()),
                group.conversation_id,
                secret + "PUBLIC_MEAL。",
                5000,
                privacy=span_for(secret, one),
            )
            progress = []

            async def record(event):
                progress.append(event)

            finished = await service.reply(sent, progress=record)
            result = finished.replies[0]
            assert result.privacy
            assert visible_text(result.text, result.privacy) == (
                "PUBLIC_REPLY。" if structured else ""
            )
            assert provider.calls == 1 and selector.calls == 1
            assert "INPUT_PRIVATE_CANARY" in bodies(
                SimpleNamespace(messages=provider.requests[0].messages)
            )
            assert "REPLY_PRIVATE_CANARY" not in bodies(
                SimpleNamespace(messages=selector.requests[0].messages)
            )
            assert "INPUT_PRIVATE_CANARY" not in bodies(
                SimpleNamespace(messages=selector.requests[0].messages)
            )
            assert not any(event.kind == "delta" for event in progress)
        finally:
            await db.close()

    asyncio.run(run())


def test_private_annotation_is_not_copied_to_other_group_members_or_shared_summary(tmp_path):
    async def run():
        db, group, messages, context = await _environment(tmp_path)
        try:
            one, two = group.participants
            secret = f"@{one.character_name} 我想叫SECRET_NAME。"
            sent = await messages.send_group_player(
                RequestId(uuid4()),
                group.conversation_id,
                secret + "PUBLIC_MEAL",
                50000,
                privacy=span_for(secret, one),
            )
            claim = await messages.claim_group(group.conversation_id, sent.turn_id)
            await messages.complete_group_reply(
                claim,
                one.character_id,
                0,
                "我记住了。",
                private_context=True,
                memories=(
                    MemoryAnnotation(
                        kind="identity",
                        topic="称呼",
                        content="玩家私下希望称呼SECRET_NAME",
                        source="player",
                        quote="我想叫SECRET_NAME。",
                        replaces=None,
                    ),
                ),
            )
            await messages.complete_group_reply(
                claim,
                two.character_id,
                1,
                "PUBLIC_ACK",
                memories=(
                    MemoryAnnotation(
                        kind="preference",
                        topic="公开话题",
                        content="PUBLIC_MEAL",
                        source="player",
                        quote="PUBLIC_MEAL",
                        replaces=None,
                    ),
                ),
            )
            await messages.finish_group(claim)
            async with db._sessions() as session:
                rows = (await session.scalars(select(LongChatMemoryRecord))).all()
                assert len(rows) == 3
                assert [row.character_id for row in rows if "SECRET_NAME" in row.content] == [
                    one.character_id.value
                ]
                assert {row.character_id for row in rows if row.content == "PUBLIC_MEAL"} == {
                    one.character_id.value,
                    two.character_id.value,
                }
                store = db.conversation_memory_store()
                sources = await store._source_messages(
                    session,
                    group.conversation_id,
                    claim.player_id,
                    [str(sent.message.message_id.value)],
                )
                assert "SECRET_NAME" not in json.dumps(sources, ensure_ascii=False)
            assert "SECRET_NAME" not in bodies(
                fitted(await context.build_reply(sent, two.character_id))
            )

            class Ranker:
                def __init__(self):
                    self.inputs = []

                async def query_terms(self, query):
                    self.inputs.append(query)
                    return tuple(query.split())

                async def rank_queries(self, queries, candidates, *, limit):
                    self.inputs.extend(queries)
                    self.inputs.extend(item.text for item in candidates)
                    return candidates[:limit]

            for person in (one, two):
                ranker = Ranker()
                store = SqlAlchemyLongChatMemoryStore(db._sessions, ranker)
                newest = await messages.send_group_player(
                    RequestId(uuid4()), group.conversation_id, "PUBLIC_QUERY", 50000
                )
                data = await store.for_character(
                    group.conversation_id, claim.player_id, person.character_id, newest.message
                )
                assert ("SECRET_NAME" in json.dumps(data, ensure_ascii=False)) == (person == one)
                assert data["_private_context"] == (person == one)
                if person == two:
                    assert "SECRET_NAME" not in " ".join(ranker.inputs)
        finally:
            await db.close()

    asyncio.run(run())


def test_http_span_schema_authorization_and_same_request_conflict(tmp_path):
    db, group, messages, _context = asyncio.run(_environment(tmp_path))
    app = create_app(
        status=RuntimeStatus("test", "privacy"),
        shutdown=ShutdownRequests(),
        session_token="fixture",
        initialize=lambda: None,
        logger=StructuredLogger(io.StringIO()),
        services=HttpServices(chat_messages=messages),
    )
    person = group.participants[0]
    text = f"@{person.character_name}（轻声）API_PRIVATE。"
    spans = list(span_for(text, person))
    path = (
        f"/api/v1/worlds/{group.conversation_id.world_id.value}"
        f"/conversations/{group.conversation_id.value}/group-messages"
    )
    headers = {"Authorization": "Bearer fixture", "X-Request-Id": str(uuid4())}
    try:
        with TestClient(app, base_url="http://127.0.0.1") as client:
            body = {"text": text, "token_ceiling": 50000, "privacy": spans}
            assert client.post(path, json=body).status_code == 401
            saved = client.post(path, headers=headers, json=body)
            assert saved.status_code == 202 and saved.json()["message"]["privacy"] == spans
            assert client.post(path, headers=headers, json=body).json() == saved.json()
            assert (
                client.post(path, headers=headers, json={**body, "privacy": []}).status_code == 409
            )
            for bad in (
                {**spans[0], "start": True},
                {**spans[0], "character_id": str(uuid4())},
                {**spans[0], "end": len(text) + 1},
            ):
                response = client.post(
                    path,
                    headers={**headers, "X-Request-Id": str(uuid4())},
                    json={**body, "privacy": [bad]},
                )
                assert response.status_code == 422
            read = client.get(path.replace("/group-messages", "/messages"), headers=headers)
            assert read.json()[0]["privacy"] == spans
    finally:
        asyncio.run(db.close())


def test_message_edit_preserves_audience_and_rejects_removed_target(tmp_path):
    from livingworld.application.chat_paths import ChatPathError
    from livingworld.infrastructure.persistence.chat_paths import SqlAlchemyChatPathStore
    from test_chat_paths import mutate

    async def run():
        db, group, messages, _context = await _environment(tmp_path)
        try:
            one = group.participants[0]
            secret = f"@{one.character_name} SECRET_BEFORE。"
            text = secret + "PUBLIC。"
            sent = await messages.send_group_player(
                RequestId(uuid4()),
                group.conversation_id,
                text,
                50000,
                privacy=span_for(secret, one),
            )
            claim = await messages.claim_group(group.conversation_id, sent.turn_id)
            await messages.complete_group_reply(claim, one.character_id, 0, "好的。")
            await messages.finish_group(claim)
            paths = SqlAlchemyChatPathStore(db._sessions)
            edited = text.replace("SECRET_BEFORE", "SECRET_AFTER_LONGER")
            await mutate(
                paths,
                group,
                "edit",
                message_id=sent.message.message_id.value,
                text=edited,
                token_ceiling=50000,
            )
            active = (await messages.list_messages(group.conversation_id))[-1]
            assert active.text == edited and active.privacy
            assert visible_text(active.text, active.privacy) == "PUBLIC。"
            with pytest.raises(ChatPathError, match="chat_path_privacy_invalid"):
                await mutate(
                    paths,
                    group,
                    "edit",
                    message_id=active.message_id.value,
                    text=edited.replace(f"@{one.character_name}", "移除目标"),
                    token_ceiling=50000,
                )
            assert (await messages.list_messages(group.conversation_id))[-1] == active
        finally:
            await db.close()

    asyncio.run(run())


def test_audiences_survive_database_restart(tmp_path):
    from livingworld.infrastructure.persistence import Database

    async def run():
        db, group, messages, _context = await _environment(tmp_path)
        try:
            one = group.participants[0]
            secret = f"@{one.character_name} RESTART_SECRET。"
            sent = await messages.send_group_player(
                RequestId(uuid4()),
                group.conversation_id,
                secret + "PUBLIC",
                50000,
                privacy=span_for(secret, one),
            )
            await db.close()
            fresh = Database(tmp_path)
            try:
                await fresh.initialize()
                loaded = (
                    await fresh.chat_message_store().list_for_player(
                        group.conversation_id, group.player_id
                    )
                )[0]
                assert loaded.privacy == sent.message.privacy
                assert visible_text(loaded.text, loaded.privacy) == "PUBLIC"
            finally:
                await fresh.close()
        finally:
            await db.close()

    asyncio.run(run())


def test_private_only_turn_does_not_ask_uninformed_members_to_reply(tmp_path):
    async def run():
        db, group, messages, context = await _environment(tmp_path)
        try:
            one = group.participants[0]
            secret = f"@{one.character_name} PRIVATE_ONLY。"
            provider, selector = RecordingProvider(("PRIVATE_ANSWER",)), RecordingProvider(())
            service = GroupChatReplyService(
                messages,
                context,
                *route(provider, "body"),
                scheduler_configuration=route(selector, "scheduler"),
            )
            sent = await messages.send_group_player(
                RequestId(uuid4()),
                group.conversation_id,
                secret,
                50000,
                privacy=span_for(secret, one),
            )
            finished = await service.reply(sent)
            assert len(finished.replies) == 1 and finished.replies[0].privacy
            assert selector.calls == 0
        finally:
            await db.close()

    asyncio.run(run())


def test_multiple_private_recipients_get_only_their_own_segments(tmp_path):
    async def run():
        db, group, messages, context = await _environment(tmp_path)
        try:
            one, two = group.participants
            first = f"@{one.character_name} SECRET_ONE。"
            second = f"@{two.character_name} SECRET_TWO。"
            spans = (
                *span_for(first, one),
                {
                    "start": len(first),
                    "end": len(first + second),
                    "character_id": str(two.character_id.value),
                },
            )
            provider, selector = (
                RecordingProvider(("PRIVATE_FIRST_ANSWER", "PRIVATE_SECOND_ANSWER")),
                RecordingProvider(()),
            )
            service = GroupChatReplyService(
                messages,
                context,
                *route(provider, "body"),
                scheduler_configuration=route(selector, "scheduler"),
            )
            sent = await messages.send_group_player(
                RequestId(uuid4()), group.conversation_id, first + second, 50000, privacy=spans
            )
            finished = await service.reply(sent)
            assert [reply.sender_id for reply in finished.replies] == [
                one.character_id,
                two.character_id,
            ]
            first_request = bodies(SimpleNamespace(messages=provider.requests[0].messages))
            second_request = bodies(SimpleNamespace(messages=provider.requests[1].messages))
            assert "SECRET_ONE" in first_request and "SECRET_TWO" not in first_request
            assert "SECRET_TWO" in second_request and "SECRET_ONE" not in second_request
            assert "PRIVATE_FIRST_ANSWER" not in second_request
            assert selector.calls == 0
        finally:
            await db.close()

    asyncio.run(run())


@pytest.mark.parametrize("format", ["json", "txt"])
def test_owner_export_keeps_private_audience_labels(tmp_path, format):
    from livingworld.application.chat_export import ChatExportService, ChatExportSnapshot
    from livingworld.infrastructure.clock import SystemWallClock

    async def run():
        db, group, messages, _context = await _environment(tmp_path)
        try:
            one = group.participants[0]
            secret = f"@{one.character_name} EXPORT_SECRET。"
            sent = await messages.send_group_player(
                RequestId(uuid4()),
                group.conversation_id,
                secret + "PUBLIC",
                50000,
                privacy=span_for(secret, one),
            )

            class Store:
                async def page(self, snapshot, cursor):
                    return (sent.message,) if cursor == 0 else ()

            snapshot = ChatExportSnapshot(
                group.conversation_id,
                group.player_id,
                "World",
                "group",
                "Player",
                tuple(
                    (str(person.character_id.value), person.character_name)
                    for person in group.participants
                ),
                1,
                1,
            )
            export = ChatExportService(Store(), None, SystemWallClock())
            output = b"".join([part async for part in export.stream(snapshot, format)]).decode(
                "utf-8"
            )
            if format == "json":
                assert json.loads(output)["messages"][0]["privacy"] == list(sent.message.privacy)
            else:
                assert (
                    f"[私密·仅你与{one.character_name}可见]" in output and "[/私密]PUBLIC" in output
                )
        finally:
            await db.close()

    asyncio.run(run())
