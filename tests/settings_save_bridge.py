"""Test-only JSON-line transport to real ASGI routes and disposable SQLite; no sockets."""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

import httpx
from fastapi import FastAPI
from livingworld.adapters.http.player_persona import player_persona_router
from livingworld.adapters.http.world_style import world_style_router
from livingworld.application.player_persona import PlayerPersonaService
from livingworld.application.world_style import WorldStyleService
from livingworld.infrastructure.imports.character_cards import CharacterCardImporter
from livingworld.infrastructure.persistence import Database

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tests/application"))


def emit(value):
    print(json.dumps(value, ensure_ascii=True), flush=True)


async def serve(directory):
    from test_offline_contact_capacity import seed

    db = Database(directory / "database")
    try:
        world, player, _, _ = await seed(db, 1)
        app = FastAPI()
        app.include_router(
            world_style_router(WorldStyleService(db.world_style_store()), lambda: None)
        )
        app.include_router(
            player_persona_router(
                PlayerPersonaService(db.player_persona_store(), CharacterCardImporter()),
                lambda: None,
            )
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            emit({"ready": True, "world_id": str(world.value), "player_id": str(player.value)})
            for line in sys.stdin:
                data = json.loads(line)
                response = await client.request(
                    data["method"],
                    data["path"],
                    headers=data["headers"],
                    content=data["body"].encode("utf-8"),
                )
                emit(
                    {
                        "id": data["id"],
                        "status": response.status_code,
                        "headers": dict(response.headers),
                        "body": response.text,
                    }
                )
    finally:
        await db.close()


def main():
    parent = Path(os.environ["DREAMTALK_SAVE_CHECK_ROOT"]).resolve()
    if parent == ROOT or parent.is_relative_to(ROOT) or not parent.is_dir():
        raise ValueError("external_isolated_directory_required")
    with tempfile.TemporaryDirectory(prefix="settings-save-", dir=parent) as working:
        directory = Path(working).resolve()
        assert directory.is_relative_to(parent)
        asyncio.run(serve(directory))


if __name__ == "__main__":
    main()
