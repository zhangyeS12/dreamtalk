"""Canonical structure, immutable snapshots, versions and lossless semantic JSON."""

import json
from dataclasses import FrozenInstanceError, fields, replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from uuid import UUID, uuid4

import pytest
from livingworld.domain.content import LIVINGWORLD_CONTENT_VERSION
from livingworld.domain.content.identifiers import (
    CharacterDefinitionId,
    ContentAssetId,
    LoreEntryId,
    RawImportId,
    WorldContentId,
)
from livingworld.domain.content.models import (
    AssetReference,
    AuthoredFaction,
    AuthoredPlace,
    ContentRevision,
    ContentSourceKind,
)
from livingworld.domain.content.serialization import (
    deserialize_content,
    semantic_hash,
    serialize_content,
)
from livingworld.domain.errors import DomainInvariantError
from livingworld.domain.identifiers import CharacterId, WorldId
from livingworld.domain.participants import Character
from livingworld.domain.values import Revision
from livingworld.domain.world import World


def test_content_is_independent_of_runtime_identity_and_state(canonical_draft):
    character, world, lore = canonical_draft.contents
    runtime_id = CharacterId(WorldId(uuid4()), character.content_id.value)
    assert character.content_id != runtime_id
    assert not isinstance(character, Character)
    assert not isinstance(world, World)
    assert len({character.content_id, world.content_id, lore.content_id}) == 3
    for content in canonical_draft.contents:
        assert not {
            "world_id",
            "location_id",
            "memory",
            "memories",
            "relationships",
            "ledger_position",
            "knowledge",
            "observations",
        } & {field.name for field in fields(content)}
        assert content.content_version == LIVINGWORLD_CONTENT_VERSION
        assert type(content.revision) is ContentRevision
        assert content.revision != Revision()
    with pytest.raises(DomainInvariantError):
        replace(character, content_id=runtime_id)
    with pytest.raises(DomainInvariantError):
        replace(world, revision=Revision())


@pytest.mark.parametrize("index", [0, 1, 2])
def test_complete_canonical_roundtrip_and_sha256(canonical_draft, index):
    content = canonical_draft.contents[index]
    payload = serialize_content(content)
    assert deserialize_content(payload) == content
    assert serialize_content(deserialize_content(payload)) == payload
    assert semantic_hash(content) == sha256(payload.encode("utf-8")).hexdigest()
    assert json.loads(payload)["data"]["content_version"] == LIVINGWORLD_CONTENT_VERSION
    assert "original_payload" not in payload
    assert "world_id" not in payload
    assert deserialize_content(payload).provenance == content.provenance


def test_deterministic_hash_sorts_objects_preserves_authored_order(canonical_draft):
    content = canonical_draft.contents[0]
    a = replace(content, extensions={"b": [1, None], "a": {"z": True, "x": "值"}})
    b = replace(content, extensions={"a": {"x": "值", "z": True}, "b": [1, None]})
    assert serialize_content(a) == serialize_content(b)
    assert semantic_hash(a) == semantic_hash(b)
    assert semantic_hash(a) != semantic_hash(
        replace(a, extensions={"b": [None, 1], "a": {"z": True, "x": "值"}})
    )
    assert semantic_hash(a) != semantic_hash(replace(a, revision=ContentRevision(1)))
    assert deserialize_content(serialize_content(a)).extensions["a"]["x"] == "值"


def test_content_edit_is_new_snapshot_and_metadata_is_defensively_frozen(canonical_draft):
    original = canonical_draft.contents[0]
    external = {"nested": {"values": [1]}}
    content = replace(original, extensions=external, aliases=["First"])
    external["nested"]["values"].append(2)
    assert content.extensions["nested"]["values"] == (1,)
    assert content.aliases == ("First",)
    with pytest.raises(TypeError):
        content.extensions["nested"]["new"] = True
    with pytest.raises(FrozenInstanceError):
        content.display_name = "Changed"
    edited = replace(content, display_name="Changed", revision=ContentRevision(1))
    assert edited.content_id == content.content_id
    assert content.display_name == "Alice"


def test_repeated_authored_material_is_preserved(canonical_draft):
    character = replace(canonical_draft.contents[0], example_dialogue=("Echo", "Echo"))
    world = replace(canonical_draft.contents[1], rules=("Repeated rule", "Repeated rule"))
    assert deserialize_content(serialize_content(character)).example_dialogue == ("Echo", "Echo")
    assert deserialize_content(serialize_content(world)).rules == ("Repeated rule", "Repeated rule")


@pytest.mark.parametrize(
    "kind", [CharacterDefinitionId, WorldContentId, LoreEntryId, ContentAssetId, RawImportId]
)
def test_content_ids_require_uuid_and_have_no_world_scope(kind):
    identity = kind(UUID(int=1))
    assert not hasattr(identity, "world_id")
    with pytest.raises(DomainInvariantError):
        kind("not a uuid")


@pytest.mark.parametrize("value", [True, -1, 0.5, "1", Revision()])
def test_content_revision_rejects_runtime_and_non_integer_values(value):
    with pytest.raises(DomainInvariantError):
        ContentRevision(value)


@pytest.mark.parametrize(
    "index,changes",
    [
        (0, {"display_name": " "}),
        (1, {"title": ""}),
        (2, {"content": "\n"}),
        (0, {"content_version": 2}),
        (0, {"content_version": True}),
        (0, {"aliases": "not array"}),
        (0, {"assets": ["not reference"]}),
        (0, {"lore_entry_ids": [LoreEntryId(UUID(int=3)), LoreEntryId(UUID(int=3))]}),
        (0, {"assets": [AssetReference(asset_id=ContentAssetId(UUID(int=3)), role="avatar")] * 2}),
        (0, {"extensions": []}),
        (0, {"extensions": {"bad": float("nan")}}),
        (0, {"authored_instructions": "not object"}),
        (2, {"enabled": 1}),
        (2, {"priority": True}),
        (2, {"order": 0.5}),
        (2, {"keywords": [""]}),
        (2, {"keywords": [], "secondary_keywords": ["orphan"]}),
        (
            1,
            {
                "locations": [
                    AuthoredPlace(key="same", name="One"),
                    AuthoredPlace(key="same", name="Two"),
                ]
            },
        ),
        (
            1,
            {
                "factions": [
                    AuthoredFaction(key="same", name="One"),
                    AuthoredFaction(key="same", name="Two"),
                ]
            },
        ),
    ],
)
def test_invalid_canonical_structures_rejected(canonical_draft, index, changes):
    with pytest.raises(DomainInvariantError):
        replace(canonical_draft.contents[index], **changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"source_kind": "import"},
        {"source_format": " "},
        {"content_hash": "bad"},
        {"imported_at": datetime(2026, 9, 17)},
        {"imported_at": None},
        {"raw_import_id": None},
        {"source_identifier": ""},
    ],
)
def test_malformed_provenance_rejected(canonical_draft, changes):
    with pytest.raises(DomainInvariantError):
        replace(canonical_draft.contents[0].provenance, **changes)


def test_provenance_normalizes_aware_utc_and_native_requires_no_fake_source(canonical_draft):
    provenance = canonical_draft.contents[0].provenance
    offset = datetime(2026, 9, 17, 8, tzinfo=timezone(timedelta(hours=8)))
    assert replace(provenance, imported_at=offset) == provenance
    native = replace(
        provenance,
        source_kind=ContentSourceKind.NATIVE,
        imported_at=None,
        raw_import_id=None,
        content_hash=None,
    )
    assert (
        deserialize_content(
            serialize_content(replace(canonical_draft.contents[0], provenance=native))
        ).provenance
        == native
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda data: data.update(extra="unknown top field"),
        lambda data: data["data"].update(location_id="runtime injection"),
        lambda data: data["data"].update(content_version=99),
        lambda data: data["data"].update(revision=True),
        lambda data: data["data"].update(assets={}),
        lambda data: data["data"]["provenance"].update(imported_at="2026-09-17T00:00:00"),
        lambda data: data.update(kind="world_event"),
    ],
)
def test_deserializer_fails_closed(canonical_draft, mutation):
    data = json.loads(serialize_content(canonical_draft.contents[0]))
    mutation(data)
    with pytest.raises(DomainInvariantError):
        deserialize_content(json.dumps(data))


@pytest.mark.parametrize("payload", ['{"kind":1,"kind":2}', '{"kind":NaN}', "not json"])
def test_malformed_or_duplicate_json_rejected(payload):
    with pytest.raises(DomainInvariantError):
        deserialize_content(payload)
