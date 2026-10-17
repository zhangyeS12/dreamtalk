"""Five user save positions, separate from immutable update recovery snapshots.

Only the private desktop storage tool calls mutations, behind maintenance admission.
The catalog commits last; archives are immutable until no position references them.
"""

import asyncio
import os
import shutil
import tempfile
import zipfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

from livingworld.infrastructure import save_safety as safety

CATALOG = "dreamtalk-saves.json"
LOCATION = "save-slots-location.json"
JOURNAL = "save-slot-load.json"
COUNT = 5


@contextmanager
def _offline_lock(app_data):
    """An orphaned storage helper must finish before a new Core can open SQLite."""
    app_data.mkdir(parents=True, exist_ok=True)
    path = safety.plain(app_data / "save-slot-operation.lock")
    with path.open("a+b") as stream:
        if stream.tell() == 0:
            stream.write(b"\0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise safety.SaveSafetyError("save_busy") from None
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _name(value):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 80:
        raise safety.SaveSafetyError("save_slot_name_invalid")
    if any(ord(character) < 32 for character in value):
        raise safety.SaveSafetyError("save_slot_name_invalid")
    return value.strip()


def _slot(value, *, manual=False):
    if type(value) is not int or not (1 if manual else 0) <= value < COUNT:
        raise safety.SaveSafetyError("save_slot_invalid")
    return value


def _empty():
    return {"identity": safety.IDENTITY, "format": 1, "revision": 0, "slots": [None] * COUNT}


def _archive(root, entry):
    name = entry["file"]
    if not isinstance(name, str) or name != f"{UUID(Path(name).stem)}.dreamsave":
        raise safety.SaveSafetyError("save_slot_catalog_invalid")
    return safety.plain(root / name)


def _catalog(root):
    value = safety.read_json(root / CATALOG, 256 * 1024)
    if (
        value.get("identity") != safety.IDENTITY
        or value.get("format") != 1
        or type(value.get("revision")) is not int
        or not isinstance(value.get("slots"), list)
    ):
        raise safety.SaveSafetyError("save_slot_catalog_invalid")
    # Do not inspect archives or metadata belonging to a sixth position.
    value["slots"] = (value["slots"][:COUNT] + [None] * COUNT)[:COUNT]
    for entry in value["slots"]:
        if entry is None:
            continue
        if not isinstance(entry, dict):
            raise safety.SaveSafetyError("save_slot_catalog_invalid")
        _archive(root, entry)
        _name(entry["name"])
        if datetime.fromisoformat(entry["saved_at"]).utcoffset() is None:
            raise safety.SaveSafetyError("save_slot_catalog_invalid")
        if not isinstance(entry.get("sha256"), str) or len(entry["sha256"]) != 64:
            raise safety.SaveSafetyError("save_slot_catalog_invalid")
        counts = entry.get("counts")
        if not isinstance(counts, dict) or any(
            type(counts.get(key)) is not int or counts[key] < 0
            for key in ("worlds", "chat_messages")
        ):
            raise safety.SaveSafetyError("save_slot_catalog_invalid")
    return value


def directory():
    path = safety.default_root() / LOCATION
    if not path.exists():
        return None
    value = safety.read_json(path, 16_384)
    if value.get("identity") != safety.IDENTITY:
        raise safety.SaveSafetyError("save_slot_catalog_invalid")
    return safety.plain(Path(value["directory"]))


def status():
    root = directory()
    if root is None:
        return {"directory": None, "revision": 0, "slots": [None] * COUNT}
    value = _catalog(root)
    slots = []
    for entry in value["slots"]:
        slots.append({**entry, "available": _archive(root, entry).is_file()} if entry else None)
    return {"directory": str(root), "revision": value["revision"], "slots": slots}


def configure(folder, app_data, program_root):
    root, live, program = map(safety.plain, (folder, app_data, program_root))
    if (
        root == live
        or root.is_relative_to(live)
        or live.is_relative_to(root)
        or root.is_relative_to(program)
    ):
        raise safety.SaveSafetyError("save_backup_location_invalid")
    root.mkdir(parents=True, exist_ok=True)
    if (root / CATALOG).exists():
        _catalog(root)
    else:
        safety.atomic_json(root / CATALOG, _empty())
    safety.atomic_json(
        safety.default_root() / LOCATION,
        {"identity": safety.IDENTITY, "directory": str(root)},
    )
    return status()


def _selected(slot, revision):
    _slot(slot)
    root = directory()
    if root is None:
        raise safety.SaveSafetyError("save_slot_folder_required")
    value = _catalog(root)
    if type(revision) is not int or value["revision"] != revision:
        raise safety.SaveSafetyError("save_slot_changed")
    return root, value


def _checked_archive(root, entry):
    if entry is None:
        raise safety.SaveSafetyError("save_slot_empty")
    path = _archive(root, entry)
    if not path.is_file() or safety.digest(path) != entry["sha256"]:
        raise safety.SaveSafetyError("save_snapshot_damaged")
    return path


def _discard_archive(root, entry, current):
    if (
        entry
        and entry.get("managed") is True
        and all(item is None or item["file"] != entry["file"] for item in current["slots"])
    ):
        try:
            path = _archive(root, entry)
            if path.is_file() and safety.digest(path) == entry["sha256"]:
                path.unlink()
        except OSError:
            pass  # A completed save is never rolled back by optional old-file cleanup.


def _commit(root, previous, slot, name, source, info, *, transaction=None):
    if _catalog(root) != previous:
        raise safety.SaveSafetyError("save_slot_changed")
    target = root / f"{uuid4()}.dreamsave"
    working = target.with_suffix(".working")
    try:
        with source.open("rb") as input_stream, working.open("xb") as output_stream:
            shutil.copyfileobj(input_stream, output_stream)
            output_stream.flush()
            os.fsync(output_stream.fileno())
        digest = safety.digest(working)
        if digest != safety.digest(source):
            raise safety.SaveSafetyError("save_snapshot_damaged")
        os.rename(working, target)
        entry = {
            "name": _name(name),
            "file": target.name,
            "saved_at": info["created_at"],
            "counts": info["info"]["counts"],
            "sha256": digest,
            "managed": True,
        }
        if transaction:
            entry["load_transaction"] = transaction
        slots = list(previous["slots"])
        slots[slot] = entry
        current = {**previous, "slots": slots, "revision": previous["revision"] + 1}
        if _catalog(root) != previous:
            raise safety.SaveSafetyError("save_slot_changed")
        safety.atomic_json(root / CATALOG, current)
        if not transaction:
            _discard_archive(root, previous["slots"][slot], current)
        return current
    finally:
        try:
            working.unlink(missing_ok=True)
        except OSError:
            pass
        # On an uncertain catalog write, keep the sealed file. Deleting it could
        # invalidate a catalog whose atomic replace had already reached disk.


def _capture(app_data, version, work):
    snapshot = safety.create_snapshot(app_data, "manual", version, workspace_root=work / "capture")
    folder = work / "capture/snapshots" / snapshot["id"]
    archive = work / f"{uuid4()}.dreamsave"
    safety.export_snapshot(snapshot["id"], archive, source_folder=folder)
    return archive, safety.snapshot_manifest(folder)


def save(app_data, version, slot, name, revision):
    root, previous = _selected(slot, revision)
    if (app_data / JOURNAL).exists() or safety.guard(app_data, include_snapshots=False)[
        "recovery_required"
    ]:
        raise safety.SaveSafetyError("save_recovery_required")
    with tempfile.TemporaryDirectory(prefix="dreamtalk-save-slot-") as temporary:
        archive, info = _capture(app_data, version, Path(temporary))
        _commit(root, previous, slot, name, archive, info)
    return status()


def _unpack(source, work):
    extracted = work / "archive"
    extracted.mkdir()
    total = 0
    with zipfile.ZipFile(safety.plain(source)) as archive:
        entries = archive.infolist()
        if len(entries) > safety.MAX_FILES + 1 or len({item.filename for item in entries}) != len(
            entries
        ):
            raise safety.SaveSafetyError("save_import_invalid")
        for item in entries:
            if item.filename == "snapshot.json":
                relative = Path("snapshot.json")
            elif item.filename.startswith("payload/"):
                relative = Path("payload") / safety.valid_relative(item.filename[8:])
            else:
                raise safety.SaveSafetyError("save_import_invalid")
            total += item.file_size
            if total > safety.MAX_BYTES or ((item.external_attr >> 16) & 0o170000) == 0o120000:
                raise safety.SaveSafetyError("save_import_invalid")
            target = extracted / relative
            if not target.resolve().is_relative_to(extracted.resolve()):
                raise safety.SaveSafetyError("save_import_invalid")
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(item) as input_stream, target.open("xb") as output_stream:
                shutil.copyfileobj(input_stream, output_stream)
    value = safety.read_json(extracted / "snapshot.json", 32 * 1024**2)
    folder = work / str(UUID(value["id"]))
    os.rename(extracted, folder)
    safety.verify_snapshot(folder)
    return folder


def import_file(source, slot, name, revision):
    _slot(slot, manual=True)
    root, previous = _selected(slot, revision)
    with tempfile.TemporaryDirectory(prefix="dreamtalk-import-slot-") as temporary:
        work = Path(temporary)
        folder = _unpack(source, work)
        value = safety.snapshot_manifest(folder)
        # Shared saves never carry another computer's API references or executable paths.
        value["files"] = {
            key: item for key, item in value["files"].items() if not key.startswith("config/")
        }
        safety.atomic_json(folder / "snapshot.json", value)
        if (folder / "payload/config").exists():
            shutil.rmtree(folder / "payload/config")
        sanitized = work / "imported.dreamsave"
        safety.export_snapshot(value["id"], sanitized, source_folder=folder)
        _commit(root, previous, slot, name, sanitized, value)
    return status()


def copy_automatic(slot, name, revision):
    _slot(slot, manual=True)
    root, previous = _selected(slot, revision)
    source = _checked_archive(root, previous["slots"][0])
    with tempfile.TemporaryDirectory(prefix="dreamtalk-copy-slot-") as temporary:
        folder = _unpack(source, Path(temporary))
        _commit(root, previous, slot, name, source, safety.snapshot_manifest(folder))
    return status()


def rename(slot, name, revision):
    root, previous = _selected(slot, revision)
    if previous["slots"][slot] is None:
        raise safety.SaveSafetyError("save_slot_empty")
    previous["slots"][slot]["name"] = _name(name)
    previous["revision"] += 1
    safety.atomic_json(root / CATALOG, previous)
    return status()


def export_file(slot, revision, output):
    root, previous = _selected(slot, revision)
    source = _checked_archive(root, previous["slots"][slot])
    output = safety.plain(output)
    if output.exists() or output.suffix != ".dreamsave":
        raise safety.SaveSafetyError("save_export_target_invalid")
    with source.open("rb") as input_stream, output.open("xb") as output_stream:
        shutil.copyfileobj(input_stream, output_stream)
        output_stream.flush()
        os.fsync(output_stream.fileno())
    return {"exported": True}


def recover(app_data):
    with _offline_lock(app_data):
        _recover(app_data)


def _recover(app_data):
    """Offline only, before Core opens SQLite. A committed catalog selects the new store."""
    path = app_data / JOURNAL
    if not path.exists():
        return
    record = safety.read_json(path, 256 * 1024)
    if record.get("identity") != safety.IDENTITY:
        raise safety.SaveSafetyError("save_restore_interrupted")
    operation = str(UUID(record["operation"]))
    root = safety.plain(Path(record["directory"]))
    current = _catalog(root)
    automatic = current["slots"][0]
    committed = automatic and automatic.get("load_transaction") == operation
    preserved = safety.plain(app_data / f"restore-preserved-{operation}")
    if committed:
        safety.metadata(app_data / "data", integrity=True)
        _discard_archive(root, record.get("old_automatic"), current)
    else:
        # Renames can precede a journal flush; inspect owned preserved paths, not a counter.
        failed = app_data / f"save-slot-failed-{uuid4()}"
        for name in ("data", safety.MARKER):
            target, original = app_data / name, preserved / name
            safety.plain(target)
            if original.exists():
                if target.exists():
                    failed.mkdir(exist_ok=True)
                    os.rename(target, failed / name)
                os.rename(original, target)
            elif name not in record["originals"] and target.exists():
                failed.mkdir(exist_ok=True)
                os.rename(target, failed / name)
        safety.metadata(app_data / "data", integrity=True)
    (app_data / "restore-in-progress.json").unlink(missing_ok=True)
    (app_data / "restore-hold.json").unlink(missing_ok=True)
    path.unlink()
    # Only this journal's exact UUID work directories; never an arbitrary caller path.
    for prefix in ("restore-preserved", "restore-incoming"):
        owned = safety.plain(app_data / f"{prefix}-{operation}")
        try:
            if owned.is_dir():
                safety.inventory(owned)
                shutil.rmtree(owned)
        except (OSError, ValueError):
            pass
    return bool(committed)


def load(app_data, version, slot, revision):
    with _offline_lock(app_data):
        return _load(app_data, version, slot, revision)


def _load(app_data, version, slot, revision):
    _slot(slot)
    root, previous = _selected(slot, revision)
    if (app_data / JOURNAL).exists() or (app_data / "restore-in-progress.json").exists():
        raise safety.SaveSafetyError("save_restore_interrupted")
    source = _checked_archive(root, previous["slots"][slot])
    with tempfile.TemporaryDirectory(prefix="dreamtalk-load-slot-") as temporary:
        work = Path(temporary)
        folder = _unpack(source, work)
        from livingworld.infrastructure.persistence.migration import HEAD_REVISION

        revisions = safety.snapshot_manifest(folder)["info"]["revisions"]
        if any(int(item[:4]) > int(HEAD_REVISION[:4]) for item in revisions):
            raise safety.SaveSafetyError("save_newer_application_required")

        async def upgrade():
            from livingworld.infrastructure.persistence import Database

            database = Database(folder / "payload/data")
            try:
                await database.initialize()
            finally:
                await database.close()

        # Migrate only a disposable copy; a failed old/future schema never touches live data.
        asyncio.run(upgrade())
        # Explicitly choosing an empty save is valid even when older recovery
        # snapshots contain worlds. Normalize only this disposable marker.
        safety.observe_world_change(folder / "payload")
        normalized, _ = _capture(folder / "payload", version, work / "normalized")
        prepared_work = work / "prepared"
        prepared_work.mkdir()
        prepared = _unpack(normalized, prepared_work)
        operation = str(uuid4())
        safety.atomic_json(
            app_data / JOURNAL,
            {
                "identity": safety.IDENTITY,
                "operation": operation,
                "directory": str(root),
                "old_automatic": previous["slots"][0],
                "originals": [
                    name for name in ("data", safety.MARKER) if (app_data / name).exists()
                ],
            },
        )

        def installed():
            archive, info = _capture(app_data, version, work / "automatic")
            automatic_name = (previous["slots"][0] or {}).get("name", "自动存档")
            _commit(root, previous, 0, automatic_name, archive, info, transaction=operation)

        try:
            safety.restore(
                app_data,
                prepared.name,
                version,
                source_folder=prepared,
                preserve_config=True,
                replace_accounting=True,
                retain_before=False,
                transaction_id=operation,
                after_install=installed,
            )
        except Exception:
            if _recover(app_data):
                return {"loaded": True}
            raise
        _recover(app_data)
    return {"loaded": True}


def run_request(request):
    action = request["action"]
    app_data, version = safety.plain(Path(request["app_data"])), request.get("version", "")
    slot, revision = request.get("slot"), request.get("revision")
    if action == "slots_status":
        return status()
    if action == "slots_configure":
        return configure(Path(request["directory"]), app_data, Path(request["program_root"]))
    if action == "slots_save":
        if safety.metadata(app_data / "data")["file_identity"] != request["expected_file_identity"]:
            raise safety.SaveSafetyError("save_storage_context_mismatch")
        return save(app_data, version, slot, request["name"], revision)
    if action == "slots_import":
        return import_file(Path(request["source"]), slot, request["name"], revision)
    if action == "slots_copy_auto":
        return copy_automatic(slot, request["name"], revision)
    if action == "slots_rename":
        return rename(slot, request["name"], revision)
    if action == "slots_export":
        return export_file(slot, revision, Path(request["output"]))
    if action == "slots_load":
        return load(app_data, version, slot, revision)
    raise safety.SaveSafetyError("save_action_invalid")
