"""Designed books: bounded, local-only appearance stored with the world's cover."""

import io
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from livingworld.adapters.http.app import create_app
from livingworld.adapters.http.services import HttpServices
from livingworld.application.errors import EntityNotFoundError
from livingworld.application.runtime import RuntimeStatus, ShutdownRequests
from livingworld.application.world_covers import WorldCoverService
from livingworld.domain.contracts import API_PROTOCOL
from livingworld.domain.errors import ConcurrencyConflictError
from livingworld.infrastructure.logging import StructuredLogger

WORLD = uuid4()
PREFIX = f"/api/v{API_PROTOCOL}"
HEADERS = {"Authorization": "Bearer session-secret"}
STICKER_DIGEST = "a" * 64


class MemoryCovers:
    def __init__(self):
        self.cover = None
        self.images = {
            STICKER_DIGEST: {
                "digest": STICKER_DIGEST,
                "size": 10,
                "media_type": "image/png",
                "width": 64,
                "height": 64,
            }
        }

    async def world_name(self, world):
        if world.value != WORLD:
            raise EntityNotFoundError("world_not_found")
        return "璃月"

    async def list_covers(self):
        return [self.cover] if self.cover else []

    async def load(self, world):
        return self.cover

    async def image(self, world, digest):
        if digest not in self.images:
            raise EntityNotFoundError("cover_image_not_found")
        return self.images[digest]

    async def add_image(self, world, image):
        self.images[image["digest"]] = image

    async def save(self, world, value, revision):
        current = self.cover["revision"] if self.cover else 0
        if current != revision:
            raise ConcurrencyConflictError("cover_edit_conflict")
        self.cover = {**value, "world_id": str(world.value), "revision": revision + 1}
        return self.cover


class NoAssets:
    async def read(self, binding):
        raise AssertionError("designs without face images never read assets")

    async def materialize(self, blob):
        raise AssertionError("designs without face images never write assets")


def design(**changes):
    value = {
        "version": 1,
        "template": "vhs",
        "material": "gloss",
        "case_color": "#111218",
        "edge": "gilt",
        "thickness": "thick",
        "wrap": False,
        "brand": False,
        "title": {
            "text": "",
            "font": "song",
            "color": "#f3d27d",
            "size": 40,
            "vertical": True,
            "x": 70,
            "y": 40,
        },
        "sky_window": {"on": True, "x": 30, "y": 30, "w": 34, "h": 22},
        "stickers": {
            "front": [
                {
                    "kind": "builtin",
                    "ref": "sakura",
                    "x": 40,
                    "y": 70,
                    "w": 24,
                    "r": -12,
                    "opacity": 1,
                },
                {
                    "kind": "image",
                    "ref": STICKER_DIGEST,
                    "x": 75,
                    "y": 80,
                    "w": 30,
                    "r": 0,
                    "opacity": 0.8,
                },
            ],
            "spine": [],
            "back": [],
        },
    }
    value.update(changes)
    return value


@pytest.fixture
def api():
    repository = MemoryCovers()
    service = WorldCoverService(repository, NoAssets(), processor=None)
    app = create_app(
        status=RuntimeStatus("test", "generation"),
        shutdown=ShutdownRequests(),
        session_token="session-secret",
        initialize=lambda: None,
        logger=StructuredLogger(io.StringIO()),
        services=HttpServices(world_covers=service),
    )
    with TestClient(app, base_url="http://127.0.0.1") as client:
        yield client, repository


def write(body_design, revision=0, title=""):
    body = {
        "mode": "text",
        "title": title,
        "show_title": True,
        "faces": {},
        "expected_revision": revision,
    }
    if body_design is not None:
        body["design"] = body_design
    return body


def test_design_round_trips_and_may_omit_title_and_brand(api):
    client, _ = api
    saved = client.put(f"{PREFIX}/worlds/{WORLD}/cover", headers=HEADERS, json=write(design()))
    assert saved.status_code == 200, saved.text
    assert saved.json()["design"] == design()
    loaded = client.get(f"{PREFIX}/worlds/{WORLD}/cover", headers=HEADERS).json()
    assert loaded["design"]["brand"] is False
    assert loaded["design"]["stickers"]["front"][1]["ref"] == STICKER_DIGEST
    assert client.get(f"{PREFIX}/world-covers", headers=HEADERS).json()[0]["revision"] == 1


def test_legacy_text_cover_still_requires_a_title(api):
    client, _ = api
    response = client.put(f"{PREFIX}/worlds/{WORLD}/cover", headers=HEADERS, json=write(None))
    assert response.status_code == 422
    assert response.json()["detail"] == "cover_title_required"
    legacy = client.put(
        f"{PREFIX}/worlds/{WORLD}/cover", headers=HEADERS, json=write(None, title="璃月")
    )
    assert legacy.status_code == 200 and "design" not in legacy.json()


@pytest.mark.parametrize(
    "broken",
    [
        design(material="velvet"),
        design(case_color="red"),
        design(thickness="huge"),
        design(version=2),
        design(title={**design()["title"], "font": "Comic Sans"}),
        design(title={**design()["title"], "text": "长" * 61}),
        design(
            stickers={
                "front": [
                    {
                        "kind": "builtin",
                        "ref": "skull",
                        "x": 1,
                        "y": 1,
                        "w": 10,
                        "r": 0,
                        "opacity": 1,
                    }
                ],
                "spine": [],
                "back": [],
            }
        ),
        design(
            stickers={
                "front": [
                    {
                        "kind": "image",
                        "ref": "../../etc",
                        "x": 1,
                        "y": 1,
                        "w": 10,
                        "r": 0,
                        "opacity": 1,
                    }
                ],
                "spine": [],
                "back": [],
            }
        ),
        design(
            stickers={"front": [design()["stickers"]["front"][0]] * 25, "spine": [], "back": []}
        ),
        design(script="<script>"),
    ],
)
def test_out_of_bounds_designs_are_rejected_without_saving(api, broken):
    client, repository = api
    response = client.put(f"{PREFIX}/worlds/{WORLD}/cover", headers=HEADERS, json=write(broken))
    assert response.status_code == 422
    assert repository.cover is None


def test_sticker_images_must_be_this_worlds_uploads(api):
    client, repository = api
    missing = design(
        stickers={
            "front": [
                {"kind": "image", "ref": "b" * 64, "x": 50, "y": 50, "w": 20, "r": 0, "opacity": 1}
            ],
            "spine": [],
            "back": [],
        }
    )
    response = client.put(f"{PREFIX}/worlds/{WORLD}/cover", headers=HEADERS, json=write(missing))
    assert response.status_code == 422
    assert response.json()["detail"] == "cover_sticker_image_missing"
    assert repository.cover is None


def test_design_edits_keep_optimistic_revisions(api):
    client, _ = api
    assert (
        client.put(
            f"{PREFIX}/worlds/{WORLD}/cover", headers=HEADERS, json=write(design())
        ).status_code
        == 200
    )
    stale = client.put(
        f"{PREFIX}/worlds/{WORLD}/cover", headers=HEADERS, json=write(design(material="paper"))
    )
    assert stale.status_code == 409
    fresh = client.put(
        f"{PREFIX}/worlds/{WORLD}/cover",
        headers=HEADERS,
        json=write(design(material="paper"), revision=1),
    )
    assert fresh.status_code == 200 and fresh.json()["design"]["material"] == "paper"
