"""Whole-data save positions, with isolated synthetic stores and injected crashes."""

import asyncio
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from legacy_store import database_at
from livingworld.application.content import ContentService
from livingworld.infrastructure import save_safety as safety
from livingworld.infrastructure import save_slots as slots
from livingworld.infrastructure.persistence import Database
from livingworld.infrastructure.persistence.migration import HEAD_REVISION


@contextmanager
def connect(path):
    connection = sqlite3.connect(path)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


@pytest.fixture
def isolated(monkeypatch):
    with tempfile.TemporaryDirectory(prefix="dreamtalk-slots-check-") as temporary:
        # Match the canonical paths used by storage; Windows TEMP may use an
        # 8.3 user-directory alias that resolves to a different spelling.
        root = Path(temporary).resolve()
        assert not root.is_relative_to(Path(__file__).resolve().parents[2])
        for key in ("LOCALAPPDATA", "APPDATA", "HF_HOME", "XDG_CACHE_HOME", "TEMP", "TMP"):
            folder = root / key.lower()
            folder.mkdir()
            monkeypatch.setenv(key, str(folder))
        monkeypatch.setenv("HF_HUB_OFFLINE", "1")
        monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
        yield root


def seed(app, label, draft=None):
    async def initialize():
        database = Database(app / "data")
        try:
            await database.initialize()
            if draft:
                service = ContentService(database.content_repository())
                preview = service.preview(draft)
                await service.commit(
                    preview,
                    reviewed_hash=preview.preview_hash,
                    expected_revisions={item.content_id: None for item in draft.contents},
                )
        finally:
            await database.close()

    asyncio.run(initialize())
    world, player, conversation, turn, message = [uuid4().hex for _ in range(5)]
    stamp = "2026-10-17T00:00:00+00:00"
    with connect(app / "data/runtime.sqlite3") as connection:
        connection.execute("INSERT INTO worlds VALUES (?,?,0)", (world, label))
        connection.execute("INSERT INTO players VALUES (?,?,?,0)", (world, player, label))
        connection.execute("INSERT INTO local_player_bindings VALUES (?,?)", (world, player))
        connection.execute("INSERT INTO local_user_profile VALUES (1,?,?,1)", (label, label))
        connection.execute(
            "INSERT INTO world_player_personas VALUES (?,?,1,?,?)",
            (world, player, json.dumps({"identity_name": label}), uuid4().hex),
        )
        connection.execute(
            "INSERT INTO local_world_profiles VALUES (?,?,?,1)", (world, label, label)
        )
        # The extra records are intentionally synthetic; their full rows must round-trip.
        connection.execute(
            "INSERT INTO chat_conversations"
            " (world_id, conversation_id, player_id, kind, direct_root_import_id, created_at_utc)"
            " VALUES (?,?,?,'group',NULL,?)",
            (world, conversation, player, stamp),
        )
        connection.execute(
            "INSERT INTO chat_turns (world_id, turn_id, conversation_id, request_id, fingerprint,"
            " token_ceiling, status, created_at_utc, kind)"
            " VALUES (?,?,?,?,?,100,'pending',?,'player')",
            (world, turn, conversation, uuid4().hex, "a" * 64, stamp),
        )
        connection.execute(
            "INSERT INTO chat_messages (world_id, message_id, conversation_id, turn_id, position,"
            " sender_player_id, sender_character_id, text, created_at_utc, story_sent_at_utc,"
            " media_json) VALUES (?,?,?,?,1,?,NULL,?,?,NULL,NULL)",
            (world, message, conversation, turn, player, f"合成聊天 {label}", stamp),
        )
        connection.execute(
            "INSERT INTO llm_budgets (budget_id, enabled, mode, currency, limit_amount, start_utc,"
            " end_utc, purpose, provider_id, model_id, revision, created_at_utc, updated_at_utc)"
            " VALUES (?,1,'hard','USD','10',?,?,NULL,NULL,NULL,0,?,?)",
            (uuid4().hex, "2026-10-01", "2026-11-01", stamp, stamp),
        )
    for folder in ("avatars", "world-covers", "chat-media", "speech", "content-assets"):
        path = app / "data" / folder / "fixture.bin"
        path.parent.mkdir()
        path.write_bytes(f"{label}:{folder}".encode())
    (app / "config").mkdir()
    (app / "config/local.json").write_text(f'{{"synthetic_machine":"{label}"}}')
    safety.storage_id(app)


def contents(app):
    """Compare every persisted table except intentional operational quarantine/accounting."""
    with connect(app / "data/runtime.sqlite3") as connection:
        excluded = {*safety.ACCOUNTING, "chat_turn_dispatches", "chat_reply_executions"}
        tables = connection.execute(
            "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        return {
            name: sorted(connection.execute(f'SELECT * FROM "{name}"').fetchall(), key=repr)
            for (name,) in tables
            if name not in excluded
        }


def configured(root, draft=None):
    app = root / "app"
    seed(app, "current", draft)
    slots.configure(root / "saves", app, root / "program")
    return app


def write_slot(app, index, name="合成存档"):
    return slots.save(app, "0.1.81", index, name, slots.status()["revision"])


def test_five_positions_ignore_sixth_and_reject_stale_or_unsafe_operations(isolated):
    app = configured(isolated)
    assert slots.status()["slots"] == [None] * 5
    write_slot(app, 0, "启动时的自动档")
    value = safety.read_json(isolated / "saves" / slots.CATALOG)
    value["slots"].extend([{"not_an_archive": "never inspect this"}, None])
    safety.atomic_json(isolated / "saves" / slots.CATALOG, value)
    assert len(slots.status()["slots"]) == 5
    with pytest.raises(safety.SaveSafetyError, match="save_slot_changed"):
        slots.save(app, "0.1.81", 1, "过期操作", 0)
    with pytest.raises(safety.SaveSafetyError, match="save_slot_invalid"):
        slots.copy_automatic(5, "第六个", 1)
    with pytest.raises(safety.SaveSafetyError, match="save_backup_location_invalid"):
        slots.configure(app / "nested", app, isolated / "program")
    for index in range(1, 5):
        write_slot(app, index)
    assert sum(item is not None for item in slots.status()["slots"]) == 5


def test_import_registers_without_loading_and_auto_copy_uses_previous_auto(isolated):
    app = configured(isolated)
    write_slot(app, 0)
    original = safety.metadata(app / "data")
    original_auto = slots.status()["slots"][0]
    with connect(app / "data/runtime.sqlite3") as connection:
        connection.execute("UPDATE worlds SET name='later',revision=1")
    other = isolated / "other"
    seed(other, "other")
    legacy = safety.create_snapshot(other, "manual", "0.1.81")
    shared = isolated / "shared.dreamsave"
    safety.export_snapshot(legacy["id"], shared)
    before = safety.inventory(app)
    slots.import_file(shared, 2, "别人的存档", slots.status()["revision"])
    assert safety.inventory(app) == before
    assert slots.status()["slots"][0] == original_auto
    slots.copy_automatic(1, "启动时另存", slots.status()["revision"])
    assert slots.status()["slots"][1]["saved_at"] == original_auto["saved_at"]
    with tempfile.TemporaryDirectory() as temporary:
        copied = slots._unpack(
            isolated / "saves" / slots._catalog(isolated / "saves")["slots"][1]["file"],
            Path(temporary),
        )
        assert safety.snapshot_manifest(copied)["info"]["ids_digest"] == original["ids_digest"]
        with connect(copied / "payload/data/runtime.sqlite3") as connection:
            assert connection.execute("SELECT name FROM worlds").fetchone() == ("current",)
    with zipfile.ZipFile(
        isolated / "saves" / slots._catalog(isolated / "saves")["slots"][2]["file"]
    ) as archive:
        assert not any(name.startswith("payload/config/") for name in archive.namelist())


def test_failed_manual_replacement_keeps_original_and_export_is_exact(isolated, monkeypatch):
    app = configured(isolated)
    write_slot(app, 1, "原存档")
    before = slots.status()
    source = slots._checked_archive(isolated / "saves", before["slots"][1])
    original_digest = safety.digest(source)
    unknown = isolated / "saves/unknown.dreamsave"
    unknown.write_bytes(b"not owned by the application")
    atomic = safety.atomic_json

    def fail_catalog(path, value):
        if path == isolated / "saves" / slots.CATALOG:
            raise OSError("synthetic failed catalog write")
        atomic(path, value)

    with monkeypatch.context() as fault:
        fault.setattr(safety, "atomic_json", fail_catalog)
        with pytest.raises(OSError, match="synthetic failed catalog write"):
            write_slot(app, 1, "失败的替换")
    assert slots.status() == before
    assert safety.digest(source) == original_digest
    renamed = slots.rename(1, "已改名", before["revision"])
    assert renamed["slots"][1]["saved_at"] == before["slots"][1]["saved_at"]
    output = isolated / "export.dreamsave"
    slots.export_file(1, renamed["revision"], output)
    assert safety.digest(output) == original_digest
    with pytest.raises(safety.SaveSafetyError, match="save_export_target_invalid"):
        slots.export_file(1, renamed["revision"], output)
    assert unknown.read_bytes() == b"not owned by the application"


def test_load_replaces_whole_store_and_auto_preserves_machine_config_and_costs(
    isolated, canonical_draft
):
    app = configured(isolated)
    write_slot(app, 0)
    other = isolated / "other"
    seed(other, "other", canonical_draft)
    expected = contents(other)
    source, _ = slots._capture(other, "0.1.81", isolated / "capture")
    slots.import_file(source, 1, "分享存档", slots.status()["revision"])
    with connect(app / "data/runtime.sqlite3") as connection:
        budgets = connection.execute("SELECT * FROM llm_budgets").fetchall()
    config = safety.inventory(app / "config")
    manual = slots.status()["slots"][1]
    assert slots.load(app, "0.1.81", 1, slots.status()["revision"]) == {"loaded": True}
    assert contents(app) == expected
    assert safety.inventory(app / "config") == config
    with connect(app / "data/runtime.sqlite3") as connection:
        assert connection.execute("SELECT * FROM llm_budgets").fetchall() == budgets
        assert connection.execute("SELECT state FROM chat_reply_executions").fetchall() == [
            ("unknown",)
        ]
    assert slots.status()["slots"][1] == manual
    assert not safety.guard(app)["recovery_required"]
    for folder in ("avatars", "world-covers", "chat-media", "speech", "content-assets"):
        assert (app / "data" / folder / "fixture.bin").read_bytes() == (
            other / "data" / folder / "fixture.bin"
        ).read_bytes()
    auto = slots._catalog(isolated / "saves")["slots"][0]
    with tempfile.TemporaryDirectory() as temporary:
        restored = slots._unpack(isolated / "saves" / auto["file"], Path(temporary))
        assert contents(restored / "payload") == expected
    assert not (app / slots.JOURNAL).exists()
    assert not list(app.glob("restore-preserved-*"))


class PowerLoss(BaseException):
    """Skip exception rollback to exercise the next startup's durable recovery."""


@pytest.mark.parametrize("phase", ["before_install", "data_moved", "data_installed", "committed"])
def test_interrupted_load_recovers_atomically(isolated, monkeypatch, phase):
    app = configured(isolated)
    write_slot(app, 0)
    before = contents(app)
    original_auto = slots.status()["slots"][0]
    other = isolated / "other"
    seed(other, "imported")
    source, _ = slots._capture(other, "0.1.81", isolated / "capture")
    slots.import_file(source, 1, "待加载", slots.status()["revision"])
    expected = contents(other)
    rename, atomic = os.rename, safety.atomic_json

    def interrupted_rename(source, target):
        rename(source, target)
        if phase == "data_moved" and Path(source) == app / "data":
            raise PowerLoss()
        if phase == "data_installed" and Path(target) == app / "data":
            raise PowerLoss()

    def interrupted_json(path, value):
        atomic(path, value)
        if phase == "before_install" and path == app / slots.JOURNAL:
            raise PowerLoss()
        if (
            phase == "committed"
            and path == isolated / "saves" / slots.CATALOG
            and value["slots"][0].get("load_transaction")
        ):
            raise PowerLoss()

    with monkeypatch.context() as fault:
        fault.setattr(os, "rename", interrupted_rename)
        fault.setattr(safety, "atomic_json", interrupted_json)
        with pytest.raises(PowerLoss):
            slots.load(app, "0.1.81", 1, slots.status()["revision"])
    assert (app / slots.JOURNAL).exists()
    slots.recover(app)
    assert contents(app) == (expected if phase == "committed" else before)
    if phase != "committed":
        assert slots.status()["slots"][0] == original_auto
    assert not safety.guard(app)["recovery_required"]
    slots.recover(app)  # Recovery is repeatable and does not change a completed store.


def test_auto_capture_failure_rolls_back_current_data_and_preserves_both_slots(
    isolated, monkeypatch
):
    app = configured(isolated)
    write_slot(app, 0)
    write_slot(app, 1)
    with connect(app / "data/runtime.sqlite3") as connection:
        connection.execute("UPDATE worlds SET name='after manual',revision=1")
    before, catalog = contents(app), slots.status()
    original = slots._capture

    def fail_automatic(current, version, work):
        if work.name == "automatic":
            raise OSError("synthetic full disk")
        return original(current, version, work)

    monkeypatch.setattr(slots, "_capture", fail_automatic)
    with pytest.raises(OSError, match="synthetic full disk"):
        slots.load(app, "0.1.81", 1, catalog["revision"])
    assert contents(app) == before
    assert slots.status() == catalog
    assert not safety.guard(app)["recovery_required"]


def test_corrupt_archive_never_changes_current_data(isolated):
    app = configured(isolated)
    write_slot(app, 1)
    entry = slots._catalog(isolated / "saves")["slots"][1]
    archive = isolated / "saves" / entry["file"]
    before = safety.inventory(app)
    archive.write_bytes(archive.read_bytes() + b"corrupted")
    with pytest.raises(safety.SaveSafetyError, match="save_snapshot_damaged"):
        slots.load(app, "0.1.81", 1, slots.status()["revision"])
    assert safety.inventory(app) == before | {
        "save-slot-operation.lock": safety.inventory(app)["save-slot-operation.lock"]
    }


def test_previous_schema_migrates_only_working_copy(isolated):
    app = configured(isolated)
    database_at(app / "data/runtime.sqlite3", "0052_sticker_entry_description")
    write_slot(app, 1)
    sealed = slots._checked_archive(
        isolated / "saves", slots._catalog(isolated / "saves")["slots"][1]
    )
    digest = safety.digest(sealed)
    slots.load(app, "0.1.81", 1, slots.status()["revision"])
    assert safety.metadata(app / "data")["revisions"] == [HEAD_REVISION]
    assert safety.digest(sealed) == digest


def test_future_save_can_be_registered_but_not_loaded(isolated):
    app = configured(isolated)
    write_slot(app, 0)
    other = isolated / "future"
    seed(other, "future")
    with connect(other / "data/runtime.sqlite3") as connection:
        connection.execute("UPDATE alembic_version SET version_num='9999_future'")
    source, _ = slots._capture(other, "99.0.0", isolated / "capture")
    slots.import_file(source, 1, "新版存档", slots.status()["revision"])
    before, catalog = contents(app), slots.status()
    with pytest.raises(safety.SaveSafetyError, match="save_newer_application_required"):
        slots.load(app, "0.1.81", 1, catalog["revision"])
    assert contents(app) == before
    assert slots.status() == catalog


def test_catalog_commit_with_lost_reply_keeps_committed_data(isolated, monkeypatch):
    app = configured(isolated)
    write_slot(app, 0)
    other = isolated / "other"
    seed(other, "committed")
    source, _ = slots._capture(other, "0.1.81", isolated / "capture")
    slots.import_file(source, 1, "提交边界", slots.status()["revision"])
    expected = contents(other)
    atomic = safety.atomic_json

    def lost_reply(path, value):
        atomic(path, value)
        if path == isolated / "saves" / slots.CATALOG and value["slots"][0].get("load_transaction"):
            raise OSError("synthetic lost commit reply")

    monkeypatch.setattr(safety, "atomic_json", lost_reply)
    assert slots.load(app, "0.1.81", 1, slots.status()["revision"]) == {"loaded": True}
    assert contents(app) == expected
    assert not (app / slots.JOURNAL).exists()


def test_explicit_empty_save_is_usable_despite_old_world_recovery_snapshot(isolated):
    app = configured(isolated)
    safety.create_snapshot(app, "pre_update", "0.1.81")
    empty = isolated / "empty"

    async def initialize():
        database = Database(empty / "data")
        try:
            await database.initialize()
        finally:
            await database.close()

    asyncio.run(initialize())
    source, _ = slots._capture(empty, "0.1.81", isolated / "capture")
    slots.import_file(source, 1, "空白存档", slots.status()["revision"])
    slots.load(app, "0.1.81", 1, slots.status()["revision"])
    assert safety.metadata(app / "data")["counts"]["worlds"] == 0
    assert not safety.guard(app)["recovery_required"]


def test_missing_current_store_does_not_inherit_someone_elses_accounting(isolated):
    import shutil

    app = configured(isolated)
    write_slot(app, 1)
    original_config = safety.inventory(app / "config")
    # Only this fixture's verified external data directory is removed.
    assert (app / "data").resolve().is_relative_to(isolated.resolve())
    shutil.rmtree(app / "data")
    slots.load(app, "0.1.81", 1, slots.status()["revision"])
    with connect(app / "data/runtime.sqlite3") as connection:
        assert connection.execute("SELECT COUNT(*) FROM llm_budgets").fetchone() == (0,)
    assert safety.inventory(app / "config") == original_config
    assert not safety.guard(app)["recovery_required"]


@pytest.mark.parametrize("path", ["../outside", "payload/data/../../outside", "payload/config/x:y"])
def test_import_rejects_unsafe_archive_paths(isolated, path):
    app = configured(isolated)
    before, catalog = contents(app), slots.status()
    source = isolated / "unsafe.dreamsave"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr(path, "synthetic invalid path")
    with pytest.raises(safety.SaveSafetyError):
        slots.import_file(source, 1, "不安全文件", catalog["revision"])
    assert contents(app) == before
    assert slots.status() == catalog


def test_overlapping_offline_helper_is_rejected(isolated):
    app = configured(isolated)
    with slots._offline_lock(app):
        with pytest.raises(safety.SaveSafetyError, match="save_busy"):
            slots.recover(app)


def test_private_storage_helper_returns_json_without_starting_application(isolated):
    app = configured(isolated)
    request = isolated / "request.json"
    safety.atomic_json(
        request,
        {
            "app_data": str(app),
            "action": "slots_save",
            "slot": 1,
            "revision": slots.status()["revision"],
            "name": "独立工具存档",
            "version": "0.1.81",
            "expected_file_identity": safety.metadata(app / "data")["file_identity"],
        },
    )
    result = subprocess.run(
        [sys.executable, "-m", "livingworld.bootstrap", "--storage-request", str(request)],
        capture_output=True,
        check=True,
        timeout=30,
        env={**os.environ, "PYTHONIOENCODING": "ascii"},
    )
    reply = json.loads(result.stdout)
    assert reply["ok"] is True
    assert reply["result"]["slots"][1]["name"] == "独立工具存档"
    assert not (app / "runtime").exists()
