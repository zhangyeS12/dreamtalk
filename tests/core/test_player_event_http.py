import io
from uuid import uuid4

from fastapi.testclient import TestClient
from livingworld.adapters.http.app import create_app
from livingworld.application.player_event_feed import (
    KnownWorldEvent,
    LocalPlayerPresence,
    PlayerEventFeedService,
    SelectablePlayer,
)
from livingworld.application.runtime import RuntimeStatus, ShutdownRequests
from livingworld.domain.contracts import API_PROTOCOL
from livingworld.domain.identifiers import EventId, PlayerId, WorldId
from livingworld.domain.participants import PlayerAvailability
from livingworld.domain.values import Revision, WorldTime
from livingworld.infrastructure.logging import StructuredLogger


class FakeFeed:
    def __init__(self, world):
        self.player = PlayerId(world, uuid4())
        self.calls = []
        self.world = world

    async def list_players(self, world_id):
        assert world_id == self.world
        return (SelectablePlayer(self.player, "玩家"),)

    async def selected_player(self, world_id):
        assert world_id == self.world
        return self.player

    async def selected_presence(self, world_id):
        assert world_id == self.world
        return LocalPlayerPresence(self.player, PlayerAvailability.BUSY, Revision())

    async def bind_player(self, player_id):
        self.calls.append(player_id)

    async def known_events(self, world_id, limit):
        assert world_id == self.world
        assert limit == 100
        return (
            KnownWorldEvent(
                EventId(world_id, uuid4()), "PlayerMoved", WorldTime(5), WorldTime(7), 2
            ),
        )


def test_known_event_http_requires_auth_and_returns_only_safe_display_fields():
    world = WorldId(uuid4())
    feed = FakeFeed(world)
    app = create_app(
        RuntimeStatus("test", "generation"),
        ShutdownRequests(),
        "session-secret",
        lambda: None,
        StructuredLogger(io.StringIO()),
        player_event_feed=PlayerEventFeedService(feed),
    )
    path = f"/api/v{API_PROTOCOL}/worlds/{world.value}"
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.get(f"{path}/known-events").status_code == 401
        headers = {"Authorization": "Bearer session-secret"}
        assert client.get(f"{path}/me/player", headers=headers).json() == {
            "player_id": str(feed.player.value),
            "availability": "busy",
            "presence_revision": 0,
        }
        assert client.get(f"{path}/players", headers=headers).json() == [
            {"player_id": str(feed.player.value), "name": "玩家"}
        ]
        response = client.get(f"{path}/known-events", headers=headers)
        assert response.status_code == 200
        event = response.json()[0]
        assert event["title"] == "有人移动了位置"
        assert event["occurred_at"] == "5"
        assert event["observed_at"] == "7"
        assert set(event) == {"event_id", "title", "occurred_at", "observed_at", "ledger_position"}
        assert (
            client.post(
                f"{path}/me/player", headers=headers, json={"player_id": str(feed.player.value)}
            ).status_code
            == 200
        )
        assert feed.calls == [feed.player]


def test_start_at_home_requires_auth_and_returns_bound_player():
    world = WorldId(uuid4())
    feed = FakeFeed(world)

    class FakeOnboarding:
        async def start_at_home(self, world_id):
            assert world_id == world
            return feed.player

        async def set_availability(self, world_id, availability, expected_revision, request_id):
            assert world_id == world
            assert availability is PlayerAvailability.AVAILABLE
            assert expected_revision == Revision(0)
            assert request_id.value
            return Revision(1)

    app = create_app(
        RuntimeStatus("test", "generation"),
        ShutdownRequests(),
        "session-secret",
        lambda: None,
        StructuredLogger(io.StringIO()),
        player_event_feed=PlayerEventFeedService(feed),
        player_onboarding=FakeOnboarding(),
    )
    path = f"/api/v{API_PROTOCOL}/worlds/{world.value}/me/start"
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.post(path).status_code == 401
        response = client.post(path, headers={"Authorization": "Bearer session-secret"})
        assert response.status_code == 200
        assert response.json() == {"player_id": str(feed.player.value)}
        headers = {"Authorization": "Bearer session-secret", "X-Request-Id": str(uuid4())}
        changed = client.post(
            f"/api/v{API_PROTOCOL}/worlds/{world.value}/me/availability",
            headers=headers,
            json={"availability": "available", "expected_presence_revision": 0},
        )
        assert changed.status_code == 200
        assert changed.json() == {"availability": "available", "presence_revision": 1}
