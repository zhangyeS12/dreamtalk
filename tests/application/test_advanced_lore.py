"""Independent synthetic lore rules, persistence and prompt-placement regression."""

import asyncio
import json
from dataclasses import replace
from uuid import uuid4

from livingworld.application.chat_capacity import ContextLayout, ContextPacker
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
from livingworld.application.lore_activation import (
    ActivationContext,
    active_common_lore,
    entry_key,
    select_common_background,
)
from livingworld.application.world_content import CommonLoreEntry
from livingworld.domain.content.identifiers import LoreEntryId
from livingworld.domain.content.models import ContentProvenance, ContentSourceKind, LoreEntry
from livingworld.domain.contracts import RequestId
from livingworld.infrastructure.persistence.chat_path_models import ChatLoreActivationRecord
from sqlalchemy import func, select
from test_chat_paths import mutate, reply, setup


def lore(text="seed", *, keys=("seed",), meta=None, insertion=None, priority=0, group=None):
    return CommonLoreEntry(
        uuid4(),
        LoreEntry(
            content_id=LoreEntryId(uuid4()),
            collection_id=None,
            provenance=ContentProvenance(
                source_kind=ContentSourceKind.NATIVE, source_format="synthetic"
            ),
            title=text,
            content=text,
            keywords=keys,
            activation_metadata=meta or {},
            insertion_metadata=insertion or {},
            priority=priority,
            group=group,
        ),
    )


def test_probability_recursive_flags_delay_and_groups():
    root = lore("bridge", meta={"constant": True})
    child = lore("target", keys=("bridge",), meta={"delayUntilRecursion": 1})
    never = lore("never", meta={"constant": True, "useProbability": True, "probability": 0})
    delay = lore("later", meta={"constant": True, "delay": 4})
    excluded = lore("excluded", keys=("bridge",), meta={"excludeRecursion": True})
    weak = lore("weak", meta={"constant": True}, priority=1, group="weather")
    strong = lore("strong", meta={"constant": True}, priority=2, group="weather")
    entries = (root, child, never, delay, excluded, weak, strong)
    context = ActivationContext("stable", 2)
    selected = active_common_lore(entries, ("unrelated",), context=context)
    assert {item.entry.content for item in selected} == {"bridge", "target", "strong"}
    assert selected == active_common_lore(entries, ("unrelated",), context=context)
    stopped = replace(
        root,
        entry=replace(root.entry, activation_metadata={"constant": True, "preventRecursion": True}),
    )
    assert child not in active_common_lore((stopped, child), ("unrelated",), context=context)
    half = lore("half", meta={"constant": True, "useProbability": True, "probability": 50})
    outcomes = [
        bool(active_common_lore((half,), (), context=ActivationContext(str(n), 10)))
        for n in range(100)
    ]
    assert any(outcomes) and not all(outcomes)


def test_sticky_does_not_refresh_and_cooldown_is_message_based():
    item = lore(meta={"sticky": 3, "cooldown": 2, "useProbability": True, "probability": 0})
    key = entry_key(item)
    assert active_common_lore(
        (item,), ("unrelated",), context=ActivationContext("s", 5, {key: 2})
    ) == (item,)
    assert not active_common_lore((item,), ("seed",), context=ActivationContext("s", 6, {key: 3}))
    assert not active_common_lore(
        (item,), ("seed",), context=ActivationContext("s", 8, {key: 5})
    )  # probability resumes


def test_timing_inherits_only_visible_prefix_and_source_changes_invalidate(tmp_path):
    async def run():
        async with setup(tmp_path) as (db, convo, messages, paths):
            store = db.chat_lore_reader()

            async def reader(conversation, anchor, entries, texts):
                selected = await store(conversation, anchor, entries, texts)
                await store.commit(
                    conversation,
                    anchor,
                    tuple(
                        item["_lore_start_key"] for item in selected if "_lore_start_key" in item
                    ),
                )
                return selected

            item = lore("persistent", meta={"sticky": 4, "cooldown": 3})
            first, answer = await reply(messages, convo, "seed", "answer")
            assert await reader(convo.conversation_id, first.message, (item,), ("seed",))
            assert await reader(convo.conversation_id, first.message, (item,), ("seed",))
            second = await messages.send_player(
                RequestId(uuid4()), convo.conversation_id, "unrelated", 50000
            )
            assert await reader(convo.conversation_id, second.message, (item,), ("unrelated",))
            changed = replace(item, entry=replace(item.entry, content="new source"))
            assert not await reader(
                convo.conversation_id, second.message, (changed,), ("unrelated",)
            )
            # Fork before activation: the discarded future's timing cannot activate this route.
            await mutate(
                paths,
                convo,
                "edit",
                message_id=first.message.message_id.value,
                text="other question",
            )
            current = (await messages.list_messages(convo.conversation_id))[-1]
            assert not await reader(convo.conversation_id, current, (item,), ("unrelated",))
            async with db._sessions() as session:
                assert (
                    await session.scalar(select(func.count()).select_from(ChatLoreActivationRecord))
                    == 1
                )
            # Restore main, then fork after the original answer: sticky start is inherited.
            await mutate(paths, convo, "switch", path_id=convo.conversation_id.value)
            await mutate(paths, convo, "branch", message_id=answer.message_id.value)
            current = await messages.send_player(
                RequestId(uuid4()), convo.conversation_id, "no keyword", 50000
            )
            assert await reader(convo.conversation_id, current.message, (item,), ("unrelated",))

    asyncio.run(run())


def test_depth_is_placed_after_trimming_without_duplicate_background():
    item = lore("DEPTH_CANARY", meta={"constant": True}, insertion={"position": 4, "depth": 1})
    background = select_common_background((item,), ())
    request = LLMRequest(
        invocation_id=InvocationId(uuid4()),
        model=ModelRef(ProviderId("synthetic"), "synthetic"),
        purpose=LLMPurpose("character_dialogue"),
        max_output_tokens=128,
        messages=(
            LLMMessage(MessageRole.SYSTEM, (TextContent("card"),)),
            LLMMessage(
                MessageRole.USER,
                (TextContent(json.dumps({"common_world_background": background})),),
            ),
            LLMMessage(MessageRole.USER, (TextContent("example"),)),
            LLMMessage(MessageRole.USER, (TextContent("old"),)),
            LLMMessage(MessageRole.ASSISTANT, (TextContent("old reply"),)),
            LLMMessage(MessageRole.USER, (TextContent("current"),)),
        ),
    )
    packer = ContextPacker(request, ContextLayout(direct_turns=((3, 4), (5,)), current_turn=1))
    result = packer.render()
    assert result.messages[-1].content[0].text == "current"
    assert "DEPTH_CANARY" in result.messages[-2].content[0].text
    assert sum("DEPTH_CANARY" in msg.content[0].text for msg in result.messages) == 1
    packer.dropped = [(1, "direct_history", 0), (1, "common_world_background", 0)]
    result = packer.render()
    assert all("DEPTH_CANARY" not in msg.content[0].text for msg in result.messages)
    assert all(msg.content[0].text != "old reply" for msg in result.messages)


def test_sparse_editor_roundtrip_preserves_opaque_metadata_and_applies_controls(tmp_path):
    from card_fixtures import json_bytes
    from livingworld.adapters.http.content_editor_pages import EditorPatchRequest
    from livingworld.application.content_authoring import authored_graph
    from livingworld.application.content_editor_pages import editor_page, merge_editor_patch

    async def run():
        async with setup(tmp_path) as (db, convo, _, _):
            service = db.world_content_service()
            document = {
                "entries": {
                    "0": {
                        "uid": 0,
                        "key": ["seed"],
                        "content": "background",
                        "constant": False,
                        "disable": False,
                        "future_extension": {"keep": "opaque"},
                    }
                }
            }
            pending = await service.prepare(
                convo.conversation_id.world_id, "lorebook", json_bytes(document)
            )
            book = await service.commit(
                convo.conversation_id.world_id, pending.item.import_id, pending.item.reviewed_hash
            )
            page = editor_page(book, 0)
            row = page["draft"]["entries"][0]
            patch = EditorPatchRequest.model_validate(
                {
                    "fields": {},
                    "updates": [
                        {
                            "source_entry_id": str(row["source_entry_id"]),
                            "fields": {
                                "advanced": {
                                    **row["advanced"],
                                    "use_probability": True,
                                    "probability": 70,
                                    "sticky": 3,
                                    "insertion_depth": 0,
                                }
                            },
                        }
                    ],
                }
            )
            fields = merge_editor_patch(
                book,
                {},
                [
                    (item.source_entry_id, item.fields.model_dump(exclude_unset=True))
                    for item in patch.updates
                ],
                [],
                [],
            )
            draft = await authored_graph(fields, book, db.content_repository())
            changed = next(item for item in draft.contents if isinstance(item, LoreEntry))
            original = next(item for item in book.contents if isinstance(item, LoreEntry))
            assert changed.activation_metadata["probability"] == 70
            assert changed.activation_metadata["sticky"] == 3
            assert changed.insertion_metadata == {"position": 4, "depth": 0}
            assert changed.extensions == original.extensions
            assert original.activation_metadata.get("probability") != 70

    asyncio.run(run())


def test_capacity_admission_commits_only_retained_lore_and_hides_internal_keys():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from livingworld.application.chat_capacity import fit_chat_context
    from livingworld.application.llm_budget import UsageUpperBound

    commit = AsyncMock()
    request = LLMRequest(
        invocation_id=InvocationId(uuid4()),
        model=ModelRef(ProviderId("synthetic"), "synthetic"),
        purpose=LLMPurpose("character_dialogue"),
        max_output_tokens=128,
        messages=(
            LLMMessage(MessageRole.SYSTEM, (TextContent("card"),)),
            LLMMessage(
                MessageRole.USER,
                (
                    TextContent(
                        json.dumps(
                            {
                                "common_world_background": [
                                    {
                                        "title": "discard",
                                        "content": "X" * 1000,
                                        "_lore_start_key": "a" * 64,
                                    },
                                    {
                                        "title": "keep",
                                        "content": "short",
                                        "_lore_start_key": "b" * 64,
                                    },
                                ]
                            }
                        )
                    ),
                ),
            ),
            LLMMessage(MessageRole.USER, (TextContent("question"),)),
        ),
    )

    class Bounder:
        def bound(self, fitted):
            size = sum(len(message.content[0].text) for message in fitted.messages)
            return UsageUpperBound(size, fitted.max_output_tokens)

        def packing_feedback(self, fitted):
            size = sum(len(message.content[0].text) for message in fitted.messages)
            return size, 300

    gateway = SimpleNamespace(
        plan=lambda *args, **kwargs: SimpleNamespace(candidates=(request.model,))
    )
    layout = ContextLayout(direct_turns=((2,),), current_turn=0, lore_commit=commit)
    fitted, _ = asyncio.run(fit_chat_context(request, layout, gateway, Bounder(), None, 500))
    commit.assert_awaited_once_with(("b" * 64,))
    body = "\n".join(message.content[0].text for message in fitted.messages)
    assert "_lore_start_key" not in body and "a" * 64 not in body and "X" * 50 not in body
    assert "short" in body and "question" in body
