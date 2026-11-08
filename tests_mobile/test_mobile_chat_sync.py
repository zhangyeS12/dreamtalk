"""Exercise latest chat wiring through the Android host using synthetic storage only."""

import asyncio
import importlib
import json
import sqlite3
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

import pytest
from alembic import command
from livingworld.bootstrap import mobile_host
from livingworld.infrastructure.logging import StructuredLogger
from livingworld.infrastructure.persistence import Database
from livingworld.infrastructure.persistence.migration import HEAD_REVISION, _alembic_config


class SecureHost:
    def __init__(self, root):
        self.root = root

    def dataDirectory(self):
        return str(self.root)

    def isForeground(self):
        return True

    def secureRead(self):
        return "{}"

    def secureWrite(self, value):
        raise AssertionError("This check must not configure a provider")


def test_mobile_upgrades_synthetic_012_and_logs_chat_validation_safely(tmp_path, monkeypatch):
    bridge = SecureHost(tmp_path / "mobile-data")
    records = []
    monkeypatch.setattr(StructuredLogger, "_write", lambda self, record: records.append(record))

    async def old_save():
        database = Database(bridge.root / "data")
        try:
            async with database.engine.begin() as connection:
                await connection.run_sync(
                    lambda sync: command.upgrade(_alembic_config(sync), "0065_chat_privacy")
                )
        finally:
            await database.close()

    asyncio.run(old_save())
    host = importlib.reload(mobile_host)
    try:
        connection = json.loads(host.dispatch("connection", "{}", bridge))["result"]
        assert host._session is not None and host._maintenance is not None
        with sqlite3.connect(bridge.root / "data/runtime.sqlite3") as database:
            assert database.execute("SELECT version_num FROM alembic_version").fetchone() == (
                HEAD_REVISION,
            )
            columns = {row[1] for row in database.execute("PRAGMA table_info(chat_messages)")}
            assert "privacy_fallback" in columns
        canary = "SYNTHETIC_PRIVATE_TEXT_NOT_FOR_DIAGNOSTICS"
        request = Request(
            connection["endpoint"] + f"/api/v1/worlds/{uuid4()}/conversations/{uuid4()}/messages",
            data=json.dumps({"text": canary, "token_ceiling": False}).encode(),
            headers={
                "Authorization": "Bearer " + connection["token"],
                "Content-Type": "application/json",
            },
        )
        with pytest.raises(HTTPError) as error:
            urlopen(request, timeout=15)
        assert error.value.code == 422
        chat = [record for record in records if record.get("component") == "chat"]
        assert len(chat) == 1
        assert chat[0]["stage"] == "request"
        assert chat[0]["http_status"] == 422
        assert chat[0]["error_type"] == "RequestValidationError"
        assert chat[0]["trace_id"]
        assert canary not in json.dumps(records)
        assert connection["token"] not in json.dumps(records)
    finally:
        if host._thread and host._thread.is_alive():
            host._stop_if_idle()
