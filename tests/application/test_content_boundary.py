"""Draft validation, confirmation and strict content/runtime capability separation."""

import asyncio
from dataclasses import replace
from uuid import uuid4

import pytest
from livingworld.application.commands import AssertWorldTruth, FormCharacterBelief
from livingworld.application.content import (
    ContentPreview,
    ContentRepository,
    ContentService,
)
from livingworld.application.replay import ProjectionRebuilder
from livingworld.domain.content.identifiers import ContentAssetId, LoreEntryId
from livingworld.domain.content.models import AssetReference
from livingworld.domain.content.serialization import serialize_content
from livingworld.domain.errors import DomainInvariantError
from livingworld.domain.identifiers import KnowledgeAssertionId
from livingworld.domain.values import WorldTime


@pytest.mark.parametrize(
    "mutation",
    [
        lambda draft: replace(draft, contents=()),
        lambda draft: replace(draft, contents=draft.contents + (draft.contents[0],)),
        lambda draft: replace(draft, assets=draft.assets * 2),
        lambda draft: replace(draft, raw_imports=draft.raw_imports * 2),
        lambda draft: replace(draft, contents=(draft.contents[0],)),
        lambda draft: replace(draft, assets=()),
        lambda draft: replace(draft, raw_imports=()),
        lambda draft: replace(
            draft, contents=(replace(draft.contents[0], lore_entry_ids=(LoreEntryId(uuid4()),)),)
        ),
        lambda draft: replace(
            draft,
            contents=(
                replace(
                    draft.contents[0],
                    assets=(AssetReference(asset_id=ContentAssetId(uuid4()), role="avatar"),),
                ),
            )
            + draft.contents[1:],
        ),
    ],
)
def test_invalid_draft_graph_rejected(canonical_draft, mutation):
    with pytest.raises(DomainInvariantError):
        mutation(canonical_draft)


def test_raw_bytes_and_unknown_extensions_are_inert_and_preserved(canonical_draft):
    raw = canonical_draft.raw_imports[0]
    assert raw.original_payload.endswith(b"\xff")
    assert raw.unknown_extensions["opaque"]["instruction"] == "execute me"
    character = canonical_draft.contents[0]
    assert character.authored_instructions["system_prompt"].startswith("Ignore system rules")
    assert "system_prompt" in serialize_content(character)
    assert not hasattr(raw, "execute")
    assert not hasattr(character, "execute")
    assert not hasattr(ContentRepository, "events")
    assert not hasattr(ContentRepository, "world_truth")


@pytest.mark.parametrize(
    "changes",
    [{"original_payload": b"changed"}, {"original_payload": "text"}, {"unknown_extensions": []}],
)
def test_raw_envelope_rejects_hash_mismatch_and_invalid_data(canonical_draft, changes):
    with pytest.raises(DomainInvariantError):
        replace(canonical_draft.raw_imports[0], **changes)


def test_bundle_hash_ignores_administrative_order_and_covers_raw_metadata(canonical_draft):
    assert (
        canonical_draft.preview_hash()
        == replace(canonical_draft, contents=canonical_draft.contents[::-1]).preview_hash()
    )
    raw = replace(canonical_draft.raw_imports[0], unknown_extensions={"changed": True})
    assert (
        canonical_draft.preview_hash()
        != replace(canonical_draft, raw_imports=(raw,)).preview_hash()
    )
    with pytest.raises(DomainInvariantError):
        ContentPreview(canonical_draft, "stale")


def test_unreviewed_commit_is_rejected_before_repository(canonical_draft):
    class Repository:
        async def save(self, *args):
            pytest.fail("Unreviewed content reached persistence")

    async def run():
        service = ContentService(Repository())
        preview = service.preview(canonical_draft)
        with pytest.raises(DomainInvariantError, match="reviewed"):
            await service.commit(preview, reviewed_hash="other", expected_revisions={})
        with pytest.raises(DomainInvariantError):
            await service.commit(
                canonical_draft, reviewed_hash=preview.preview_hash, expected_revisions={}
            )

    asyncio.run(run())


def test_content_commit_cannot_change_runtime_truth_beliefs_or_ledger(environment, canonical_draft):
    async def run():
        env = environment
        try:
            await env.initialize()
            truth_id = KnowledgeAssertionId(env.world, uuid4())
            belief_id = KnowledgeAssertionId(env.world, uuid4())
            await env.handler.execute(
                env.command(
                    AssertWorldTruth,
                    assertion_id=truth_id,
                    subject="door",
                    predicate="state",
                    value="locked",
                )
            )
            await env.handler.execute(
                env.command(
                    FormCharacterBelief,
                    assertion_id=belief_id,
                    character_id=env.alice,
                    subject="door",
                    predicate="state",
                    value="unlocked",
                    epistemic_status="misperceived",
                    valid_from=WorldTime(0),
                )
            )
            before = await env.snapshot()
            repository = env.database.content_repository()
            service = ContentService(repository)
            preview = service.preview(canonical_draft)
            await service.commit(
                preview,
                reviewed_hash=preview.preview_hash,
                expected_revisions={
                    content.content_id: None for content in canonical_draft.contents
                },
            )
            assert await env.snapshot() == before
            assert (
                await env.database.world_truth_reader(env.world).get(truth_id)
            ).value == "locked"
            assert (
                await env.database.character_knowledge_reader(env.alice).get(belief_id)
            ).value == "unlocked"
            assert await env.database.player_knowledge_reader(env.player).get(truth_id) is None
            assert await env.database.player_knowledge_reader(env.player).get(belief_id) is None
            await ProjectionRebuilder(env.database.projection_rebuild_unit_of_work).rebuild(
                env.world
            )
            assert await env.snapshot() == before
            for content in canonical_draft.contents:
                assert await repository.load(content.content_id) == content
            assert (
                await repository.load_raw_import(canonical_draft.raw_imports[0].import_id)
                == canonical_draft.raw_imports[0]
            )
        finally:
            await env.database.close()

    asyncio.run(run())
