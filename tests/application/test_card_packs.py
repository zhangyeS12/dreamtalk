"""Real HTTP/SQLite pack regressions using synthetic cards and isolated assets."""

import asyncio
import copy
import io
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from livingworld.adapters.http.app import create_app
from livingworld.adapters.http.services import HttpServices
from livingworld.application.runtime import RuntimeStatus, ShutdownRequests
from livingworld.infrastructure.logging import StructuredLogger
from livingworld.infrastructure.persistence import Database
from PIL import Image

HEADERS = {"Authorization": "Bearer synthetic-session"}
BASE = "/api/v1/card-packs"
LIBRARY = "/api/v1/card-library"


def design():
    face = dict(
        color="#273449",
        accent="#dfcc93",
        material="metal",
        frame=True,
        glyph="☾",
        image=None,
        source=None,
        crop=None,
        imageOpacity=82,
        layers=[],
    )
    return {"version": 1, "front": face, "back": {**face, "glyph": "✧"}}


def make_app(db):
    content = db.world_content_service()
    return create_app(
        status=RuntimeStatus("test", "generation"),
        shutdown=ShutdownRequests(),
        session_token="synthetic-session",
        initialize=lambda: None,
        logger=StructuredLogger(io.StringIO()),
        services=HttpServices(
            world_content=content,
            card_library=db.card_library_service(content, None),
            card_packs=db.card_pack_service(),
        ),
    )


@pytest.fixture
def api(tmp_path):
    db = Database(tmp_path)
    asyncio.run(db.initialize())
    with TestClient(make_app(db), base_url="http://127.0.0.1") as client:
        yield client, db
    asyncio.run(db.close())


def card(client, name="Synthetic"):
    preview = client.post(
        LIBRARY + "/editor/preview",
        headers=HEADERS,
        json={"draft": {"kind": "character", "name": name}},
    ).json()
    saved = client.post(
        LIBRARY + f"/previews/{preview['preview_id']}/commit",
        headers=HEADERS,
        json={"card_id": preview["card_id"], "reviewed_hash": preview["reviewed_hash"]},
    )
    assert saved.status_code == 200, saved.text
    return saved.json()


def body(ids=(), **changes):
    return (
        dict(
            expected_revision=0,
            name="月下拾光",
            subtitle="A synthetic pack",
            cardIds=list(ids),
            design=design(),
        )
        | changes
    )


def put(client, path, payload):
    return client.put(path, headers=HEADERS, json=payload)


def test_atomic_membership_cas_order_idempotence_and_source_retention(api):
    client, _ = api
    assert client.get(BASE).status_code == 401
    assert client.get(BASE, headers=HEADERS).json() == []
    cards = [card(client, f"角色 {index}") for index in range(3)]
    ids = [item["card_id"] for item in cards]
    first, second = [BASE + "/" + str(uuid4()) for _ in range(2)]
    payload = body(reversed(ids[:2]))
    saved = put(client, first, payload)
    assert saved.status_code == 200, saved.text
    assert saved.json()["cardIds"] == list(reversed(ids[:2]))
    assert put(client, first, payload).json() == saved.json()  # exact retry
    assert put(client, first, payload | {"name": "stale"}).status_code == 409
    assert put(client, second, body([ids[0]])).status_code == 200  # same source, two packs
    assert put(client, first, body([str(uuid4())], expected_revision=1)).status_code == 404
    assert put(client, first, body([ids[0], ids[0]], expected_revision=1)).status_code == 409
    assert client.get(BASE, headers=HEADERS).json()[0] == saved.json()
    member = first + "/members/" + ids[2]
    assert put(client, member, {"expected_revision": 9}).status_code == 409
    included = put(client, member, {"expected_revision": 1}).json()
    assert included["revision"] == 2 and included["cardIds"] == [ids[1], ids[0], ids[2]]
    assert put(client, member, {"expected_revision": 1}).json() == included
    removed = put(client, first, body([], expected_revision=2))
    assert removed.status_code == 200
    assert client.get(LIBRARY, headers=HEADERS).json() == cards
    assert all(not item["world_ids"] for item in cards)


def test_staged_images_cancel_owner_crop_restart_and_persisted_design(api):
    client, db = api
    path = BASE + "/" + str(uuid4())
    image = io.BytesIO()
    photo = Image.new("RGB", (160, 100), "red")
    photo.paste("blue", (80, 0, 160, 100))
    photo.save(image, format="PNG")
    uploaded = client.post(path + "/images", headers=HEADERS, content=image.getvalue())
    assert uploaded.status_code == 200, uploaded.text
    source = uploaded.json()["digest"]
    assert client.get(BASE, headers=HEADERS).json() == []  # upload is not a saved pack
    foreign = BASE + "/" + str(uuid4())
    assert client.get(foreign + "/images/" + source, headers=HEADERS).status_code == 404
    crop = dict(x=0, y=0, width=43.75, height=100, rotation=0)
    cropped = client.post(path + "/images/" + source + "/crop", headers=HEADERS, json=crop)
    assert cropped.status_code == 200, cropped.text
    digest = cropped.json()["digest"]
    result = client.get(path + "/images/" + digest, headers=HEADERS)
    preview = Image.open(io.BytesIO(result.content))
    assert preview.size == (900, 1286) and preview.getpixel((450, 640))[0] > 220
    assert client.get(path + "/images/not-a-digest", headers=HEADERS).status_code == 422
    invalid = body()
    invalid["design"]["front"]["image"] = source
    assert put(client, foreign, invalid).status_code == 404
    assert client.get(BASE, headers=HEADERS).json() == []
    payload = body()
    payload["design"]["front"].update(source=source, image=digest, crop=crop)
    payload["design"]["back"]["color"] = "#703550"
    saved = put(client, path, payload)
    assert saved.status_code == 200, saved.text
    # Recompose all services: staged process memory is gone, committed originals remain.
    with TestClient(make_app(db), base_url="http://127.0.0.1") as restarted:
        assert restarted.get(BASE, headers=HEADERS).json() == [saved.json()]
        assert (
            restarted.get(path + "/images/" + source, headers=HEADERS).content == image.getvalue()
        )
        assert (
            restarted.post(
                path + "/images/" + source + "/crop", headers=HEADERS, json=crop
            ).status_code
            == 200
        )
        restarted.post(path + "/discard", headers=HEADERS)
        assert restarted.get(path + "/images/" + digest, headers=HEADERS).status_code == 200
    staged = client.post(foreign + "/images", headers=HEADERS, content=image.getvalue()).json()
    client.post(foreign + "/discard", headers=HEADERS)
    assert client.get(foreign + "/images/" + staged["digest"], headers=HEADERS).status_code == 404
    assert len(client.get(BASE, headers=HEADERS).json()) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"name": " "},
        {"name": "x" * 61},
        {"cardIds": ["invalid-id"]},
        {"expected_revision": True},
        {"design": {"version": 2}},
        {"unknown": "field"},
    ],
)
def test_invalid_pack_never_creates_rows(api, change):
    client, _ = api
    assert put(client, BASE + "/" + str(uuid4()), body(**change)).status_code == 422
    assert client.get(BASE, headers=HEADERS).json() == []


def test_missing_card_or_image_leaves_saved_snapshot_untouched(api):
    client, _ = api
    item = card(client)
    path = BASE + "/" + str(uuid4())
    saved = put(client, path, body([item["card_id"]])).json()
    invalid = body([item["card_id"]], expected_revision=1)
    invalid["design"]["back"]["source"] = "a" * 64
    assert put(client, path, invalid).status_code == 404
    bad = copy.deepcopy(invalid)
    bad["design"]["back"]["source"] = "not-a-digest"
    assert put(client, path, bad).status_code == 422
    assert client.get(BASE, headers=HEADERS).json() == [saved]


def test_delete_pack_is_authenticated_revision_checked_and_preserves_original_cards(api):
    client, db = api
    item = card(client)
    path = BASE + "/" + str(uuid4())
    saved = put(client, path, body([item["card_id"]])).json()
    image = io.BytesIO()
    Image.new("RGB", (32, 32), "red").save(image, format="PNG")
    digest = client.post(path + "/images", headers=HEADERS, content=image.getvalue()).json()[
        "digest"
    ]
    assert client.request("DELETE", path, json={"expected_revision": 1}).status_code == 401
    assert (
        client.request("DELETE", path, headers=HEADERS, json={"expected_revision": 9}).status_code
        == 409
    )
    assert client.get(BASE, headers=HEADERS).json() == [saved]
    result = client.request("DELETE", path, headers=HEADERS, json={"expected_revision": 1})
    assert result.status_code == 200 and result.json() == {"removed": True}
    assert client.request(
        "DELETE", path, headers=HEADERS, json={"expected_revision": 1}
    ).json() == {"removed": False}
    assert client.get(path + "/images/" + digest, headers=HEADERS).status_code == 404
    assert put(client, path, body([item["card_id"]], expected_revision=1)).status_code == 409
    with TestClient(make_app(db), base_url="http://127.0.0.1") as restarted:
        assert restarted.get(BASE, headers=HEADERS).json() == []
        assert restarted.get(LIBRARY, headers=HEADERS).json() == [item]


def test_delete_library_card_updates_all_pack_revisions_order_and_blocks_stale_save(api):
    client, db = api
    cards = [card(client, str(index)) for index in range(4)]
    ids = [value["card_id"] for value in cards]
    paths = [BASE + "/" + str(uuid4()) for _ in range(3)]
    for path, members in zip(paths, [ids[:3], [ids[1]], [ids[3]]], strict=True):
        assert put(client, path, body(members)).status_code == 200
    target = LIBRARY + "/" + ids[1]
    image = io.BytesIO()
    Image.new("RGB", (32, 32), "blue").save(image, format="PNG")
    digest = client.post(target + "/images", headers=HEADERS, content=image.getvalue()).json()[
        "digest"
    ]
    assert client.request("DELETE", target, json={"expected_revision": 1}).status_code == 401
    assert (
        client.request("DELETE", target, headers=HEADERS, json={"expected_revision": 9}).status_code
        == 409
    )
    response = client.request("DELETE", target, headers=HEADERS, json={"expected_revision": 1})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["removed"] is True
    assert [pack["cardIds"] for pack in result["packs"]] == [[ids[0], ids[2]], [], [ids[3]]]
    assert [pack["revision"] for pack in result["packs"]] == [2, 2, 1]
    # A concurrent editor cannot write back the deleted member or its old pack snapshot.
    assert put(client, paths[0], body(ids[:3], expected_revision=1)).status_code == 409
    assert put(client, paths[0] + "/members/" + ids[3], {"expected_revision": 2}).json()[
        "cardIds"
    ] == [ids[0], ids[2], ids[3]]
    assert client.get(target, headers=HEADERS).status_code == 404
    assert client.get(target + "/images/" + digest, headers=HEADERS).status_code == 404
    assert (
        client.request("DELETE", target, headers=HEADERS, json={"expected_revision": 1}).json()[
            "removed"
        ]
        is False
    )
    with TestClient(make_app(db), base_url="http://127.0.0.1") as restarted:
        assert [value["card_id"] for value in restarted.get(LIBRARY, headers=HEADERS).json()] == [
            ids[0],
            ids[2],
            ids[3],
        ]
        assert restarted.get(BASE, headers=HEADERS).json()[0]["cardIds"] == [ids[0], ids[2], ids[3]]


@pytest.mark.parametrize("revision", [0, -1, True, "1"])
def test_delete_requires_a_strict_reviewed_revision(api, revision):
    client, _ = api
    for base in (BASE, LIBRARY):
        assert (
            client.request(
                "DELETE",
                base + "/" + str(uuid4()),
                headers=HEADERS,
                json={"expected_revision": revision},
            ).status_code
            == 422
        )
