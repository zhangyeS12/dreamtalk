import importlib
import json
import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest
from livingworld.bootstrap import mobile_host
from livingworld.bootstrap.mobile_notifications import poll
from livingworld.infrastructure.llm.production_config import (
    load_scheduler_configurations,
    load_world_configurations,
)


class Host:
    def __init__(self, root):
        self.root, self.secure = root, "{}"
        self.foreground, self.background = True, False
        self.notifications, self.allowed = [], True

    def dataDirectory(self):
        return str(self.root)

    def secureRead(self):
        return self.secure

    def secureWrite(self, value):
        self.secure = value

    def isForeground(self):
        return self.foreground

    def isBackgroundRunning(self):
        return self.background

    def postContactNotification(self, raw):
        if not self.allowed:
            return False
        self.notifications.append(json.loads(raw))
        return True


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    import httpx

    async def no_provider(*args, **kwargs):
        raise AssertionError("No remote provider is permitted during offline settings checks")

    monkeypatch.setattr(httpx.AsyncClient, "send", no_provider)
    runtime = importlib.reload(mobile_host)
    host = Host(tmp_path / "mobile")
    yield runtime, host
    if runtime._thread and runtime._thread.is_alive():
        runtime._stop_if_idle()


def call(runtime, host, operation, value=None):
    return json.loads(runtime.dispatch(operation, json.dumps(value or {}), host))["result"]


def model(name="synthetic-model"):
    return {
        "provider_kind": "openai-compatible",
        "model_id": name,
        "base_url": "https://example.invalid/v1",
        "max_billable_input_tokens": 8192,
        "max_output_tokens": 1024,
        "timeout_ms": 30000,
        "native_json": True,
    }


def test_scoped_models_inheritance_and_safe_persistence(runtime):
    runtime, host = runtime
    call(runtime, host, "connection")
    secret = "synthetic-test-secret"
    call(
        runtime,
        host,
        "configure_chat_model",
        {"setup": model(), "streaming": True, "secret": secret},
    )
    world = str(uuid4())
    inherited = call(runtime, host, "managed_chat_model_setup", {"worldId": world})
    assert inherited["inherited"] and "secret" not in inherited
    call(
        runtime,
        host,
        "configure_chat_model",
        {"worldId": world, "setup": model("world-model"), "streaming": True, "secret": secret},
    )
    call(
        runtime,
        host,
        "configure_scheduler_model",
        {"worldId": world, "setup": model("selector-model"), "secret": secret},
    )
    assert (
        call(runtime, host, "managed_chat_model_setup", {"worldId": world})["model_id"]
        == "world-model"
    )
    assert (
        call(runtime, host, "managed_scheduler_model_setup", {"worldId": world})["model_id"]
        == "selector-model"
    )
    public = (host.root / "llm.json").read_text()
    assert secret not in public
    default, worlds = load_world_configurations(host.root / "llm.json")
    scheduler, explicit, schedulers = load_scheduler_configurations(host.root / "llm.json")
    assert len(worlds) == len(schedulers) == 1
    call(runtime, host, "use_default_chat_model", {"worldId": world})
    assert (
        call(runtime, host, "managed_chat_model_setup", {"worldId": world})["model_id"]
        == "synthetic-model"
    )
    assert (
        call(runtime, host, "managed_scheduler_model_setup", {"worldId": world})["model_id"]
        == "selector-model"
    )


def test_hidden_core_requires_running_background_session(runtime):
    runtime, host = runtime
    call(runtime, host, "connection")
    import asyncio

    host.foreground = False
    call(runtime, host, "visibility")
    asyncio.run_coroutine_threadsafe(asyncio.sleep(0.01), runtime._loop).result()
    assert runtime._maintenance.suspended
    host.background = True
    call(runtime, host, "visibility")
    asyncio.run_coroutine_threadsafe(asyncio.sleep(0.01), runtime._loop).result()
    assert not runtime._maintenance.suspended
    host.background = False
    call(runtime, host, "visibility")
    asyncio.run_coroutine_threadsafe(asyncio.sleep(0.01), runtime._loop).result()
    assert runtime._maintenance.suspended


def test_media_credential_world_scope_and_restart(runtime):
    runtime, host = runtime
    call(runtime, host, "connection")
    world, reference = str(uuid4()), str(uuid4())
    call(
        runtime,
        host,
        "media_credential_put",
        {"worldId": world, "secretRef": reference, "secret": "synthetic-media-secret"},
    )
    with pytest.raises(ValueError):
        call(
            runtime,
            host,
            "speech_credential_put",
            {"worldId": str(uuid4()), "secretRef": reference, "secret": "other"},
        )
    runtime._stop_if_idle()
    call(runtime, host, "connection")
    from livingworld.application.llm_config import SecretRef

    assert runtime._credentials.media_reference_owned(
        __import__("uuid").UUID(world), SecretRef(__import__("uuid").UUID(reference))
    )
    assert "synthetic-media-secret" not in (host.root / "llm.json").read_text()
    call(runtime, host, "forget_media_credentials", {"worldId": world, "secretRef": reference})
    assert "synthetic-media-secret" not in host.secure
    assert not runtime._credentials.media_reference_owned(
        __import__("uuid").UUID(world), SecretRef(__import__("uuid").UUID(reference))
    )


def test_mobile_five_slots_export_import_and_load(runtime):
    runtime, host = runtime
    call(runtime, host, "connection")
    state = call(runtime, host, "save_slots_status")
    assert len(state["slots"]) == 5 and state["slots"][0]
    state = call(
        runtime,
        host,
        "operate_save_slot",
        {
            "request": {
                "action": "rename",
                "slot": 0,
                "revision": state["revision"],
                "name": "合成自动位置",
                "confirmed": True,
            }
        },
    )
    runtime._stop_if_idle()
    runtime._startup_backup_done = False
    call(runtime, host, "connection")
    state = call(runtime, host, "save_slots_status")
    assert state["slots"][0]["name"] == "合成自动位置"

    state = call(
        runtime,
        host,
        "operate_save_slot",
        {
            "request": {
                "action": "save",
                "slot": 1,
                "revision": state["revision"],
                "name": "合成检查",
                "confirmed": True,
            }
        },
    )
    exported = call(
        runtime, host, "mobile_export_path", {"request": {"slot": 1, "revision": state["revision"]}}
    )
    assert Path(exported).is_file()
    with __import__("zipfile").ZipFile(exported) as archive:
        assert all(
            "llm.json" not in name and "encrypted-config" not in name for name in archive.namelist()
        )
    state = call(
        runtime,
        host,
        "operate_save_slot",
        {
            "request": {
                "action": "import",
                "slot": 2,
                "revision": state["revision"],
                "name": "导入检查",
                "source": exported,
                "confirmed": True,
            }
        },
    )
    assert state["slots"][2] and not Path(exported).exists()
    assert call(
        runtime,
        host,
        "operate_save_slot",
        {
            "request": {
                "action": "load",
                "slot": 2,
                "revision": state["revision"],
                "confirmed": True,
            }
        },
    )["loaded"]


@pytest.fixture
def messages(tmp_path):
    root = tmp_path
    (root / "data").mkdir()
    db = sqlite3.connect(root / "data/runtime.sqlite3")
    db.executescript("""
    create table chat_messages(world_id text,message_id text,conversation_id text,
                              turn_id text,sender_character_id text,text text);
    create table chat_turns(world_id text,turn_id text,kind text);
    create table chat_conversations(world_id text,conversation_id text,player_id text);
    create table local_player_bindings(world_id text,player_id text);
    create table characters(world_id text,character_id text,name text);
    """)
    world, conversation, player, character = [str(uuid4()) for _ in range(4)]
    db.execute("insert into chat_conversations values (?,?,?)", (world, conversation, player))
    db.execute("insert into local_player_bindings values (?,?)", (world, player))
    db.execute("insert into characters values (?,?,?)", (world, character, "合成角色"))
    db.commit()
    host = Host(root)
    host.foreground = False
    host.background = True
    assert poll(root, host) == 0

    def add(kind="outreach", commit=True):
        turn, message = str(uuid4()), str(uuid4())
        db.execute("insert into chat_turns values (?,?,?)", (world, turn, kind))
        db.execute(
            "insert into chat_messages values (?,?,?,?,?,?)",
            (world, message, conversation, turn, character, "PRIVATE SYNTHETIC BODY"),
        )
        if commit:
            db.commit()
        return message

    yield root, db, host, add
    db.close()


def test_only_committed_outreach_and_no_private_preview(messages):
    root, db, host, add = messages
    add(commit=False)
    assert poll(root, host) == 0
    db.rollback()
    message = add()
    assert poll(root, host) == 1
    assert host.notifications[0]["id"] == message
    assert "PRIVATE" not in json.dumps(host.notifications)
    assert poll(root, host) == 0
    add("player")
    assert poll(root, host) == 0


def test_notification_permission_retry_does_not_regenerate(messages):
    root, db, host, add = messages
    message = add()
    host.allowed = False
    assert poll(root, host) == 0
    host.allowed = True
    assert poll(root, host) == 1
    assert host.notifications[0]["id"] == message
    assert poll(root, host) == 0


def test_foreground_and_other_player_do_not_alert(messages):
    root, db, host, add = messages
    host.foreground = True
    add()
    assert poll(root, host) == 0
    host.foreground = False
    assert poll(root, host) == 0
    add()
    db.execute("update local_player_bindings set player_id=?", (str(uuid4()),))
    db.commit()
    assert poll(root, host) == 0


def test_idle_wait_tracks_spawned_jobs_without_cancelling_them():
    import asyncio

    from livingworld.application.update_maintenance import UpdateMaintenance

    async def scenario():
        gate = UpdateMaintenance()
        release = asyncio.Event()
        with gate.operation() as admitted:
            assert admitted
            job = gate.spawn(release.wait())
            assert gate.active == 2
        assert gate.active == 1
        gate.prepare()
        with gate.operation() as admitted:
            assert not admitted
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(gate.wait_idle(), timeout=0.001)
        assert not job.cancelled()
        release.set()
        await job
        await asyncio.wait_for(gate.wait_idle(), timeout=1)
        assert gate.active == 0

    asyncio.run(scenario())


def test_inherited_key_copy_has_independent_reference_and_endpoint_consent(runtime):
    runtime, host = runtime
    call(runtime, host, "connection")
    call(
        runtime,
        host,
        "configure_chat_model",
        {"setup": model(), "streaming": True, "secret": "synthetic-inherited-key"},
    )
    original = json.loads(host.secure)["secret_ref"]
    world = str(uuid4())
    call(
        runtime,
        host,
        "update_chat_model",
        {"worldId": world, "setup": model("independent"), "streaming": True, "secret": ""},
    )
    saved = json.loads(host.secure)
    assert saved["worlds"][world]["secret_ref"] != original
    assert saved["worlds"][world]["secret"] == saved["secret"]
    altered = {**model("independent"), "base_url": "https://other.invalid/v1"}
    before = host.secure
    with pytest.raises(ValueError, match="model_update_new_secret_required"):
        call(
            runtime,
            host,
            "update_chat_model",
            {"worldId": world, "setup": altered, "streaming": True, "secret": ""},
        )
    assert host.secure == before
    call(runtime, host, "configure_scheduler_model", {"setup": model("selector"), "secret": ""})
    assert call(runtime, host, "managed_scheduler_model_setup")["inherited"] is False


def test_missing_current_database_requires_explicit_restore(runtime):
    runtime, host = runtime
    call(runtime, host, "connection")
    state = call(runtime, host, "save_slots_status")
    assert state["slots"][0]
    runtime._stop_if_idle()
    database = host.root / "data/runtime.sqlite3"
    preserved = database.with_suffix(".synthetic-missing")
    database.rename(preserved)
    try:
        with pytest.raises(ValueError, match="save_recovery_required"):
            call(runtime, host, "connection")
        assert not database.exists()
        catalog = call(runtime, host, "save_slots_status")
        assert catalog["slots"][0] == state["slots"][0]
    finally:
        preserved.rename(database)
