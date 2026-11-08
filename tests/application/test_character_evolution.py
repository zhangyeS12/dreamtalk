"""Automatic, reversible character changes on disposable synthetic databases."""

import asyncio
import json
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from livingworld.application.chat_context import DirectChatContextBuilder
from livingworld.application.chat_event_annotations import (
    ANNOTATION_INSTRUCTIONS,
    decode_optional_dialogue,
)
from livingworld.application.chat_reply import DirectChatReplyService
from livingworld.domain.contracts import RequestId
from livingworld.infrastructure.persistence import Database
from livingworld.infrastructure.persistence.models import ChatMessageRecord
from sqlalchemy import func, select
from test_group_chat_reply import ScriptedProvider, _environment, _service
from test_offline_contact_capacity import seed


def proposal(text="Calm, and now consistently considerate.", **changes):
    return dict(
        field="personality",
        scope="global",
        text=text,
        quote="consistently considerate",
        confidence=0.9,
        change_kind="addition",
        **changes,
    )


async def change(store, world, root, entry, operation):
    return await store.change(
        world,
        root,
        field=entry["field"],
        scope=entry["scope"],
        text="",
        operation=operation,
        entry_id=UUID(entry["entry_id"]),
        locked=False,
        source="user",
    )


@pytest.mark.parametrize("kind", ["addition", "replacement"])
def test_model_change_is_immediately_effective_and_retains_provenance(tmp_path, kind):
    async def run():
        db = Database(tmp_path)
        try:
            world, player, _, contacts = await seed(db, 2)
            store = db.character_evolution_store()
            root = contacts[0].root_import_id
            data = proposal()
            data["change_kind"] = kind
            saved = await store.propose(world, root, **data)
            assert saved["selected"] and saved["state"] == "active"
            assert saved["change_kind"] == kind
            assert saved["quote"] == data["quote"] and saved["confidence"] == 0.9
            assert await store.list(world, root, ("global", f"player:{player.value}")) == [saved]
            assert await store.list(world, contacts[1].root_import_id) == []
            private = proposal("A player-specific, consistently considerate change.")
            private["scope"] = f"player:{player.value}"
            await store.propose(world, root, **private)
            assert len(await store.list(world, root, ("global", "player:other"))) == 1
            assert len(await store.list(world, root, ("global", private["scope"]))) == 2
            await db.close()
            db = Database(tmp_path)
            await db.initialize()
            assert len(await db.character_evolution_store().list(world, root)) == 2
        finally:
            await db.close()

    asyncio.run(run())


def test_replacement_rollback_repeated_output_and_lock_are_respected(tmp_path):
    async def run():
        db = Database(tmp_path)
        try:
            world, player, _, contacts = await seed(db, 1)
            store, root = db.character_evolution_store(), contacts[0].root_import_id
            first = await store.propose(world, root, **proposal())
            second = await store.propose(world, root, **proposal("More open and considerate."))
            history = await store.list(world, root)
            assert len(history) == 2
            assert not history[0]["selected"] and history[0]["state"] == "inactive"
            assert history[1]["selected"]
            await change(store, world, root, first, "restore")
            assert await store.list(world, root, ("global",)) == [
                {**first, "selected": True, "state": "active"}
            ]
            # A repeat must not undo a user's rollback or add another version.
            await store.propose(world, root, **proposal("More open and considerate."))
            assert len(await store.list(world, root)) == 2
            assert (await store.list(world, root, ("global",)))[0]["entry_id"] == first["entry_id"]
            await change(store, world, root, first, "lock")
            with pytest.raises(ValueError, match="character_evolution_locked"):
                await store.propose(world, root, **proposal("A different change."))
            with pytest.raises(ValueError, match="character_evolution_locked"):
                await change(store, world, root, second, "restore")
            await change(store, world, root, first, "unlock")
            await change(store, world, root, first, "deactivate")
            assert await store.list(world, root, ("global", f"player:{player.value}")) == []
            await store.propose(world, root, **proposal())
            assert await store.list(world, root, ("global",)) == []
        finally:
            await db.close()

    asyncio.run(run())


@pytest.mark.parametrize(
    "invalid", [{"confidence": 0.59}, {"quote": "not in reply"}, {"change_kind": "invalid"}]
)
def test_annotation_rejects_invalid_changes_without_discarding_the_reply(invalid):
    data = proposal()
    data.update(invalid)
    reply = "I have become consistently considerate."
    decoded = decode_optional_dialogue(json.dumps({"reply": reply, "character_updates": [data]}))
    assert decoded.text == reply and not decoded.character_updates
    assert "自动生效" in ANNOTATION_INSTRUCTIONS
    assert "完整当前版本" in ANNOTATION_INSTRUCTIONS


def test_same_reply_cannot_apply_two_conflicting_versions_to_one_field_and_scope():
    decoded = decode_optional_dialogue(
        json.dumps(
            {
                "reply": "I have become consistently considerate.",
                "character_updates": [proposal(), proposal("A conflicting version.")],
            }
        )
    )
    assert len(decoded.character_updates) == 1
    assert decoded.character_updates[0].text == proposal()["text"]


def test_removed_internal_speaker_header_cannot_be_evidence_for_an_automatic_change(tmp_path):
    async def run():
        db, group, messages, context = await _environment(tmp_path)
        try:
            target = next(p for p in group.participants if p.character_name == "角色乙")
            header = f"角色乙（发言者标识：{target.character_id.value}）："
            data = proposal()
            data["quote"] = header
            provider = ScriptedProvider(
                (
                    json.dumps(
                        {
                            "reply": header + "\nA normal reply.",
                            "character_updates": [data],
                        }
                    ),
                    "STOP",
                )
            )
            service = _service(messages, context, provider)
            service._event_capture = True
            service._evolution_writer = db.character_evolution_store().propose
            sent = await messages.send_group_player(
                RequestId(UUID(int=75)), group.conversation_id, "@角色乙 hello", 500
            )
            completed = await service.reply(sent)
            assert completed.replies[0].text == "A normal reply."
            assert (
                await db.character_evolution_store().list(
                    group.conversation_id.world_id, target.root_import_id
                )
                == []
            )
        finally:
            await db.close()

    asyncio.run(run())


@pytest.mark.parametrize("fails", [False, True])
def test_group_changes_apply_only_after_the_corresponding_reply_is_saved(tmp_path, fails):
    async def run():
        db, group, messages, context = await _environment(tmp_path)
        try:
            payload = {
                "reply": "I have become consistently considerate.",
                "character_updates": [proposal()],
            }
            provider = ScriptedProvider((json.dumps(payload), "STOP"))
            service = _service(messages, context, provider)
            service._event_capture = True
            writer = db.character_evolution_store().propose

            async def after_message(*args, **kwargs):
                async with db._sessions() as session:
                    assert (
                        await session.scalar(
                            select(func.count())
                            .select_from(ChatMessageRecord)
                            .where(ChatMessageRecord.sender_character_id.is_not(None))
                        )
                        == 1
                    )
                return await writer(*args, **kwargs)

            service._evolution_writer = AsyncMock(side_effect=after_message)
            sent = await messages.send_group_player(
                RequestId(UUID(int=72)), group.conversation_id, "@角色乙 hello", 500
            )
            if fails:
                with patch.object(
                    messages,
                    "complete_group_reply",
                    AsyncMock(side_effect=RuntimeError("save_failed")),
                ):
                    with pytest.raises(RuntimeError, match="save_failed"):
                        await service.reply(sent)
            else:
                await service.reply(sent)
            target = next(p for p in group.participants if p.character_name == "角色乙")
            entries = await db.character_evolution_store().list(
                group.conversation_id.world_id, target.root_import_id
            )
            assert len(entries) == (0 if fails else 1)
            assert service._evolution_writer.await_count == (0 if fails else 1)
            if not fails:
                assert entries[0]["selected"] and entries[0]["change_kind"] == "addition"
        finally:
            await db.close()

    asyncio.run(run())


@pytest.mark.parametrize("fails", [False, True])
def test_direct_change_is_effective_in_the_next_prompt_only_after_delivery(tmp_path, fails):
    async def run():
        db, group, messages, group_context = await _environment(tmp_path)
        try:
            world = group.conversation_id.world_id
            target = group.participants[0]
            chats = group_context._conversations
            conversation = await chats.open_direct(world, target.root_import_id)
            store = db.character_evolution_store()
            context = DirectChatContextBuilder(
                chats,
                messages,
                db.local_profile_store(),
                db.character_memory_reader,
                evolution_reader=store.list,
            )
            payload = {
                "reply": "I have become consistently considerate.",
                "character_updates": [proposal()],
            }
            prototype = _service(messages, group_context, ScriptedProvider((json.dumps(payload),)))
            service = DirectChatReplyService(
                messages,
                context,
                prototype._gateway,
                prototype._token_bounder,
                prototype._model,
                80,
                event_capture=True,
                evolution_writer=store.propose,
            )
            sent = await messages.send_player(
                RequestId(UUID(int=73)), conversation.conversation_id, "Hello", 500
            )
            if fails:
                with patch.object(
                    messages, "complete_direct", AsyncMock(side_effect=RuntimeError("save_failed"))
                ):
                    with pytest.raises(RuntimeError, match="save_failed"):
                        await service.reply(sent)
                assert await store.list(world, target.root_import_id) == []
            else:
                await service.reply(sent)
                following = await messages.send_player(
                    RequestId(UUID(int=74)), conversation.conversation_id, "And now?", 500
                )
                built = await context.build(following)
                prompt = "\n".join(
                    part.text for message in built.messages for part in message.content
                )
                assert proposal()["text"] in prompt
                entries = await store.list(world, target.root_import_id)
                await change(store, world, target.root_import_id, entries[0], "deactivate")
                reverted = await context.build(following)
                assert proposal()["text"] not in "\n".join(
                    part.text for message in reverted.messages for part in message.content
                )
        finally:
            await db.close()

    asyncio.run(run())
