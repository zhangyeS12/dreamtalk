"""Local whole-save snapshots. No models, business replay, or schema migrations.

SQLite's backup API copies committed WAL pages. Assets/config are copied only
behind the existing desktop maintenance barrier (or with Core stopped).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
import time
import zipfile
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

IDENTITY = "app.livingworld.desktop"
FORMAT = 1
MAX_FILES = 100_000
MAX_BYTES = 32 * 1024**3
COUNTS = (
    "worlds",
    "characters",
    "chat_messages",
    "content_character_definitions",
    "chat_sticker_entries",
    "voice_cards",
)
MARKER = ".dreamtalk-storage.json"
ACCOUNTING = (
    "llm_attempts",
    "llm_budgets",
    "llm_budget_reservations",
    "speech_call_receipts",
    "chat_media_caption_calls",
)
CONTENT_TABLES = {
    "chat_messages",
    "content_character_definitions",
    "content_worlds",
    "content_lore_entries",
    "content_lore_collections",
    "content_raw_imports",
    "voice_cards",
    "chat_media_assets",
    "world_covers",
}


class SaveSafetyError(ValueError):
    pass


def plain(path: Path) -> Path:
    if not path.is_absolute():
        raise SaveSafetyError("save_path_invalid")
    for part in (path, *path.parents):
        if part.is_symlink() or part.is_junction():
            raise SaveSafetyError("save_link_rejected")
    return path.resolve()


def atomic_json(path: Path, value) -> None:
    plain(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def read_json(path: Path, limit=4 * 1024**2):
    plain(path)
    if path.stat().st_size > limit:
        raise SaveSafetyError("save_record_invalid")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def default_root() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        raise SaveSafetyError("save_backup_location_unavailable")
    return plain(Path(base) / "dreamtalk-backups")


def backup_root() -> Path:
    base = default_root()
    settings = base / "location.json"
    if settings.exists():
        value = read_json(settings, 16_384)
        if value.get("identity") != IDENTITY:
            raise SaveSafetyError("save_backup_location_invalid")
        return plain(Path(value["directory"]))
    return base


def configure_location(folder: Path, app_data: Path, program_root: Path | None = None) -> dict:
    selected = plain(folder) / "dreamtalk-backups"
    live = plain(app_data)
    if selected == live or selected.is_relative_to(live) or live.is_relative_to(selected):
        raise SaveSafetyError("save_backup_location_invalid")
    if program_root and selected.is_relative_to(plain(program_root)):
        raise SaveSafetyError("save_backup_location_invalid")
    selected.mkdir(parents=True, exist_ok=True)
    atomic_json(selected / ".dreamtalk-backup-root.json", {"identity": IDENTITY})
    atomic_json(default_root() / ".dreamtalk-backup-root.json", {"identity": IDENTITY})
    atomic_json(
        default_root() / "location.json", {"identity": IDENTITY, "directory": str(selected)}
    )
    # Previous root remains discoverable, so changing location cannot hide backups.
    previous = default_root() / "roots.json"
    roots = read_json(previous) if previous.exists() else []
    roots = list(dict.fromkeys([*roots, str(selected)]))[-32:]
    atomic_json(previous, roots)
    return {"directory": str(selected)}


def roots() -> list[Path]:
    base = default_root()
    known = base / "roots.json"
    values = read_json(known) if known.exists() else []
    return list(dict.fromkeys([base, backup_root(), *(plain(Path(item)) for item in values)]))


def metadata(data: Path, *, integrity=False, frozen=False) -> dict:
    database = plain(data) / "runtime.sqlite3"
    if not database.is_file():
        raise SaveSafetyError("save_database_missing")
    uri = database.as_uri() + ("?mode=ro&immutable=1" if frozen else "?mode=ro")
    connection = sqlite3.connect(uri, uri=True, timeout=5)
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        if integrity and connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise SaveSafetyError("save_database_corrupt")
        revision = [row[0] for row in connection.execute("SELECT version_num FROM alembic_version")]
        counts, ids = {}, hashlib.sha256()
        for table in COUNTS:
            present = connection.execute(
                "SELECT 1 FROM sqlite_schema WHERE type='table' AND name=?", (table,)
            ).fetchone()
            counts[table] = (
                connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                if present
                else 0
            )
        # IDs/counts are evidence of continuity, never private text or names.
        for table, key in (("worlds", "world_id"), ("chat_messages", "message_id")):
            if not connection.execute(
                "SELECT 1 FROM sqlite_schema WHERE type='table' AND name=?", (table,)
            ).fetchone():
                continue
            for (value,) in connection.execute(f'SELECT "{key}" FROM "{table}" ORDER BY "{key}"'):
                ids.update(f"{table}:{value}\n".encode())
        stat = database.stat()
        return {
            "counts": counts,
            "ids_digest": ids.hexdigest(),
            "revisions": revision,
            "file_identity": f"{stat.st_dev}:{stat.st_ino}",
            "data_directory": str(data),
        }
    finally:
        connection.close()


def storage_id(app_data: Path) -> str:
    path = app_data / MARKER
    if path.exists():
        value = read_json(path, 16_384)
        if value.get("identity") != IDENTITY:
            raise SaveSafetyError("save_storage_identity_invalid")
        return str(UUID(value["storage_id"]))
    value = str(uuid4())
    atomic_json(path, {"identity": IDENTITY, "storage_id": value})
    return value


def inventory(folder: Path) -> dict[str, dict]:
    files, size = {}, 0
    plain(folder)
    for path in sorted(folder.rglob("*")):
        plain(path)
        if path.is_file():
            size += path.stat().st_size
            if len(files) >= MAX_FILES or size > MAX_BYTES:
                raise SaveSafetyError("save_backup_too_large")
            files[path.relative_to(folder).as_posix()] = {
                "bytes": path.stat().st_size,
                "sha256": digest(path),
            }
    return files


def valid_relative(value: str) -> Path:
    path = Path(value)
    if (
        not value
        or "\\" in value
        or ":" in value
        or path.is_absolute()
        or any(part in (".", "..") for part in path.parts)
    ):
        raise SaveSafetyError("save_snapshot_path_invalid")
    if not (value.startswith("data/") or value.startswith("config/") or value == MARKER):
        raise SaveSafetyError("save_snapshot_path_invalid")
    return path


def snapshot_manifest(folder: Path) -> dict:
    value = read_json(folder / "snapshot.json", 32 * 1024**2)
    if (
        value.get("identity") != IDENTITY
        or value.get("format") != FORMAT
        or not value.get("complete")
    ):
        raise SaveSafetyError("save_snapshot_invalid")
    if str(UUID(value["id"])) != folder.name or len(value["files"]) > MAX_FILES:
        raise SaveSafetyError("save_snapshot_invalid")
    if not {"data/runtime.sqlite3", MARKER} <= value["files"].keys():
        raise SaveSafetyError("save_snapshot_invalid")
    str(UUID(value["storage_id"]))
    if datetime.fromisoformat(value["created_at"]).utcoffset() is None:
        raise SaveSafetyError("save_snapshot_invalid")
    for name in value["files"]:
        valid_relative(name)
    return value


def verify_payload(payload: Path, expected: dict) -> None:
    actual = inventory(payload)
    # SHM is a rebuildable WAL index, never committed user data. Old read-only
    # inspection could also create an unrecorded empty WAL beside a sealed DB.
    # A recorded WAL or any nonempty WAL remains protected byte for byte.
    actual.pop("data/runtime.sqlite3-shm", None)
    expected = {name: info for name, info in expected.items() if name != "data/runtime.sqlite3-shm"}
    wal = "data/runtime.sqlite3-wal"
    if wal not in expected and actual.get(wal, {}).get("bytes") == 0:
        actual.pop(wal)
    if actual != expected:
        raise SaveSafetyError("save_snapshot_damaged")


def verify_snapshot(folder: Path) -> dict:
    value = snapshot_manifest(folder)
    verify_payload(folder / "payload", value["files"])
    marker = read_json(folder / "payload" / MARKER, 16_384)
    if marker.get("identity") != IDENTITY or marker.get("storage_id") != value["storage_id"]:
        raise SaveSafetyError("save_snapshot_damaged")
    info = snapshot_metadata(folder, integrity=True)
    if value.get("info") and (
        info["counts"] != value["info"]["counts"]
        or info["ids_digest"] != value["info"]["ids_digest"]
    ):
        raise SaveSafetyError("save_snapshot_damaged")
    value["info"] = info
    return value


@contextmanager
def snapshot_database(folder: Path):
    data = folder / "payload/data"
    if not (data / "runtime.sqlite3-wal").exists():
        # Only sealed, quiescent snapshot files use immutable; never the live DB.
        yield data, True
        return
    # SQLite may rebuild SHM even for mode=ro. Use a disposable working copy
    # whenever a captured WAL must be read, leaving the original snapshot sealed.
    with tempfile.TemporaryDirectory(prefix="dreamtalk-snapshot-") as temporary_name:
        temporary = Path(temporary_name)
        for name in ("runtime.sqlite3", "runtime.sqlite3-wal"):
            if (data / name).exists():
                shutil.copy2(data / name, temporary / name)
        yield temporary, False


def snapshot_metadata(folder: Path, *, integrity=False) -> dict:
    with snapshot_database(folder) as (data, frozen):
        return metadata(data, integrity=integrity, frozen=frozen)


def list_snapshots() -> list[dict]:
    result = []
    for root in roots():
        directory = plain(root) / "snapshots"
        if not directory.is_dir():
            continue
        for path in directory.iterdir():
            try:
                plain(path)
                value = snapshot_manifest(path)
                # Listing history is metadata-only. A legacy opaque installer
                # backup is verified when selected, not opened on every startup.
                info = value.get("info")
                result.append(
                    {
                        "id": value["id"],
                        "created_at": value["created_at"],
                        "reason": value["reason"],
                        "version": value.get("version", ""),
                        "counts": info["counts"] if info else None,
                        "bytes": sum(item["bytes"] for item in value["files"].values()),
                    }
                )
            except (OSError, ValueError, KeyError, sqlite3.Error):
                continue  # Partial/damaged records never become restoration candidates.
    return sorted(result, key=lambda item: item["created_at"], reverse=True)


def locate(snapshot_id: str) -> Path:
    name = str(UUID(snapshot_id))
    for root in roots():
        path = plain(root) / "snapshots" / name
        if path.is_dir():
            return plain(path)
    raise SaveSafetyError("save_snapshot_missing")


def guard(
    app_data: Path, *, retry_update_verification: bool = False, include_snapshots=True
) -> dict:
    app_data = plain(app_data)
    current, problem = None, None
    database_present = (app_data / "data/runtime.sqlite3").exists()
    try:
        current = metadata(app_data / "data")
    except (OSError, ValueError, sqlite3.Error):
        if database_present:
            problem = "save_database_unavailable"
    snapshots, backup_problem, backup_directory = [], None, ""
    try:
        backup_directory = str(backup_root())
        if include_snapshots or current is None or current["counts"]["worlds"] == 0:
            snapshots = list_snapshots()
    except (OSError, ValueError, KeyError, sqlite3.Error):
        backup_problem = "save_backup_catalog_unavailable"
    if current is None and (snapshots or backup_problem):
        problem = "save_database_unavailable"
    marker = read_json(app_data / MARKER, 16_384) if (app_data / MARKER).exists() else {}
    if (
        current
        and not current["counts"]["worlds"]
        and backup_problem
        and not marker.get("allow_empty")
    ):
        problem = "save_previous_worlds_found"
    if current is None and marker and not marker.get("allow_empty"):
        problem = "save_database_unavailable"
    if (
        current
        and current["counts"]["worlds"] == 0
        and not marker.get("allow_empty")
        and any(item["counts"] is None or item["counts"]["worlds"] for item in snapshots)
    ):
        problem = "save_previous_worlds_found"
    if (app_data / "restore-in-progress.json").exists():
        problem = "save_restore_interrupted"
    elif (app_data / "restore-hold.json").exists():
        problem = "save_restored_review_required"
    elif (
        (app_data / "update-failure.json").exists()
        and (app_data / "updates/handoff.json").exists()
        and not retry_update_verification
    ):
        problem = "save_update_review_required"
    return {
        "recovery_required": bool(problem),
        "problem": problem,
        "current": current,
        "snapshots": snapshots[:100],
        "backup_directory": backup_directory,
        "backup_problem": backup_problem,
        "automatic_minutes": 30,
    }


def observe_world_change(app_data: Path) -> None:
    """Only called after an explicit, successful world creation/deletion."""
    identity = storage_id(app_data)
    atomic_json(
        app_data / MARKER,
        {
            "identity": IDENTITY,
            "storage_id": identity,
            "allow_empty": metadata(app_data / "data")["counts"]["worlds"] == 0,
        },
    )


def fingerprint(app_data: Path) -> str:
    values = []
    for path in (
        app_data / "data/runtime.sqlite3",
        app_data / "data/runtime.sqlite3-wal",
        *(app_data / "config").glob("*.json"),
    ):
        if path.is_file():
            stat = path.stat()
            values.append((path.name, stat.st_mtime_ns, stat.st_size))
    return hashlib.sha256(json.dumps(sorted(values)).encode()).hexdigest()


def create_snapshot(app_data: Path, reason: str, version: str, *, automatic=False) -> dict:
    app_data = plain(app_data)
    root = backup_root()
    if root == app_data or root.is_relative_to(app_data) or app_data.is_relative_to(root):
        raise SaveSafetyError("save_backup_location_invalid")
    atomic_json(root / ".dreamtalk-backup-root.json", {"identity": IDENTITY})
    info = metadata(app_data / "data")
    if automatic and guard(app_data)["recovery_required"]:
        raise SaveSafetyError("save_recovery_required")
    identity = storage_id(app_data)
    stamp = fingerprint(app_data)
    history = root / f"last-{identity}.json"
    if automatic and history.exists() and read_json(history).get("fingerprint") == stamp:
        return {"skipped": True}
    name = str(uuid4())
    folder = plain(root / "incomplete" / name)
    payload = folder / "payload"
    payload.mkdir(parents=True, exist_ok=False)
    deadline = time.monotonic() + 180
    database = app_data / "data/runtime.sqlite3"
    try:
        (payload / "data").mkdir()
        source = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=5)
        destination = sqlite3.connect(payload / "data/runtime.sqlite3")

        def progress(_status, _left, _total):
            if time.monotonic() > deadline:
                raise SaveSafetyError("save_backup_timeout")

        try:
            source.backup(destination, pages=512, progress=progress, sleep=0.05)
            destination.execute("PRAGMA journal_mode=DELETE")
        finally:
            destination.close()
            source.close()
        for path in (app_data / "data").iterdir():
            plain(path)
            if path.name in (
                "runtime.sqlite3",
                "runtime.sqlite3-wal",
                "runtime.sqlite3-shm",
                "cache",
            ):
                continue
            target = payload / "data" / path.name
            if path.is_dir():
                for child in path.rglob("*"):
                    plain(child)
                shutil.copytree(path, target)
            else:
                shutil.copy2(path, target)
            if time.monotonic() > deadline:
                raise SaveSafetyError("save_backup_timeout")
        config = app_data / "config"
        if config.is_dir():
            inventory(config)  # reject links before traversing user-owned config
            shutil.copytree(config, payload / "config")
        shutil.copy2(app_data / MARKER, payload / MARKER)
        copied = metadata(payload / "data", integrity=True, frozen=True)
        if copied["counts"] != info["counts"] or copied["ids_digest"] != info["ids_digest"]:
            raise SaveSafetyError("save_changed_during_backup")
        value = {
            "identity": IDENTITY,
            "format": FORMAT,
            "id": name,
            "storage_id": identity,
            "created_at": datetime.now(UTC).isoformat(),
            "version": version,
            "reason": reason,
            "info": copied,
            "files": inventory(payload),
            "complete": True,
        }
        atomic_json(folder / "snapshot.json", value)
        verify_snapshot(folder)
        published = plain(root / "snapshots" / name)
        published.parent.mkdir(parents=True, exist_ok=True)
        os.rename(folder, published)
        result = {"id": name, "counts": copied["counts"], "created_at": value["created_at"]}
        try:
            atomic_json(history, {"fingerprint": stamp, "created_at": value["created_at"]})
            protected = set()
            handoff_path = app_data / "updates/handoff.json"
            if handoff_path.exists():
                handoff = read_json(handoff_path)
                if handoff.get("identity") != IDENTITY:
                    raise SaveSafetyError("save_legacy_update_invalid")
                protected.update(handoff.get("prior_snapshot_ids", []))
                protected.add(handoff.get("save_snapshot_id"))
            for known_root in roots():
                if (known_root / "snapshots").is_dir():
                    prune(known_root, protected=protected)
        except (OSError, ValueError, KeyError, sqlite3.Error):
            # Retention is optional housekeeping. A verified published snapshot
            # must not become a failed backup because an older root is offline.
            result["retention_warning"] = "save_retention_incomplete"
        return result
    except Exception:
        # Keep incomplete material; it is not listed and never replaces a good backup.
        raise


def prune(root: Path, *, protected=()) -> None:
    directory = plain(root / "snapshots")
    candidates = []
    for path in directory.iterdir():
        try:
            value = verify_snapshot(path)
            candidates.append((path, value))
        except (OSError, ValueError, KeyError, sqlite3.Error):
            continue
    candidates.sort(key=lambda pair: pair[1]["created_at"], reverse=True)
    keep, days, upgrades, automatic = set(), set(), 0, 0
    cutoff = datetime.now(UTC) - timedelta(days=7)
    for path, value in candidates:
        if path.name in protected:
            keep.add(path)
            continue
        created = datetime.fromisoformat(value["created_at"])
        reason = value["reason"]
        if reason not in ("automatic", "pre_update", "pre_install", "pre_migration"):
            keep.add(path)  # manual, imported and pre-restore backups are never silently pruned
        elif reason in ("pre_update", "pre_install", "pre_migration") and upgrades < 3:
            keep.add(path)
            upgrades += 1
        elif reason == "automatic":
            day = created.date()
            if automatic < 2 or (created >= cutoff and day not in days):
                keep.add(path)
            days.add(day)
            automatic += 1
    for path, _value in candidates:
        if path not in keep and path.resolve().parent == directory.resolve():
            inventory(path)  # reject any junction introduced after enumeration
            shutil.rmtree(path)  # checked exact UUID child, never active data or backup root


def restore(app_data: Path, snapshot_id: str, version: str) -> dict:
    app_data = plain(app_data)
    value = verify_snapshot(locate(snapshot_id))
    # Future/unknown schema must never be opened by an older application.
    from livingworld.infrastructure.persistence.migration import HEAD_REVISION

    if any(int(item[:4]) > int(HEAD_REVISION[:4]) for item in value["info"]["revisions"]):
        raise SaveSafetyError("save_newer_application_required")
    before = None
    if (app_data / "data/runtime.sqlite3").is_file():
        try:
            before = create_snapshot(app_data, "pre_restore", version)
        except (sqlite3.Error, SaveSafetyError) as error:
            if isinstance(error, SaveSafetyError) and str(error) != "save_database_corrupt":
                raise
            # A corrupt live DB cannot be logically backed up: preserve opaque files instead.
            before = None
            opaque = backup_root() / "damaged-preserved" / str(uuid4())
            inventory(app_data / "data")
            shutil.copytree(app_data / "data", opaque)
    incoming = app_data / f"restore-incoming-{uuid4()}"
    preserved = app_data / f"restore-preserved-{uuid4()}"
    payload = locate(snapshot_id) / "payload"
    shutil.copytree(payload, incoming)
    verify_payload(incoming, value["files"])
    # Installer snapshots may have a WAL; normalize only the working copy.
    (incoming / "data/runtime.sqlite3-shm").unlink(missing_ok=True)
    if (incoming / "data/runtime.sqlite3-wal").exists():
        source = sqlite3.connect(
            (incoming / "data/runtime.sqlite3").as_uri() + "?mode=ro", uri=True
        )
        destination = sqlite3.connect(incoming / "data/normalized.sqlite3")
        try:
            source.backup(destination)
            destination.execute("PRAGMA journal_mode=DELETE")
        finally:
            destination.close()
            source.close()
        for name in ("runtime.sqlite3-wal", "runtime.sqlite3-shm"):
            (incoming / "data" / name).unlink(missing_ok=True)
        os.replace(incoming / "data/normalized.sqlite3", incoming / "data/runtime.sqlite3")
    preserve_accounting(app_data / "data/runtime.sqlite3", incoming / "data/runtime.sqlite3")
    quarantine_restored_tasks(incoming / "data/runtime.sqlite3")
    (incoming / "config").mkdir(exist_ok=True)
    installed_files = inventory(incoming)
    preserved.mkdir()
    journal = app_data / "restore-in-progress.json"
    atomic_json(journal, {"snapshot_id": snapshot_id, "preserved": str(preserved)})
    installed, moved = [], []
    try:
        for name in ("data", "config", MARKER):
            source, target = incoming / name, app_data / name
            if not source.exists():
                continue
            plain(target)
            if target.exists():
                os.rename(target, preserved / name)
                moved.append(name)
            os.rename(source, target)
            installed.append(name)
        actual = metadata(app_data / "data", integrity=True)
        if (
            actual["counts"] != value["info"]["counts"]
            or actual["ids_digest"] != value["info"]["ids_digest"]
        ):
            raise SaveSafetyError("save_restore_verification_failed")
        for name, expected in installed_files.items():
            if digest(app_data / valid_relative(name)) != expected["sha256"]:
                raise SaveSafetyError("save_restore_verification_failed")
        atomic_json(
            app_data / "restore-hold.json",
            {"snapshot_id": snapshot_id, "created_at": value["created_at"]},
        )
        (app_data / "update-failure.json").unlink(missing_ok=True)
        journal.unlink()
    except Exception:
        failed = app_data / f"restore-failed-{uuid4()}"
        failed.mkdir()
        for name in installed:
            os.rename(app_data / name, failed / name)
        for name in moved:
            os.rename(preserved / name, app_data / name)
        journal.unlink(missing_ok=True)
        raise
    return {
        "restored": True,
        "counts": actual["counts"],
        "created_at": value["created_at"],
        "before": before,
    }


def preserve_accounting(current: Path, restored: Path) -> None:
    """Story restoration must not roll back known costs, hard budgets or daily receipts."""
    if not current.is_file():
        return
    try:
        source = sqlite3.connect(current.as_uri() + "?mode=ro", uri=True)
        destination = sqlite3.connect(restored)
        try:
            for table in ACCOUNTING:
                old_columns = source.execute(f'PRAGMA table_info("{table}")').fetchall()
                new_columns = destination.execute(f'PRAGMA table_info("{table}")').fetchall()
                if not old_columns:
                    continue
                if not new_columns or [item[1] for item in old_columns] != [
                    item[1] for item in new_columns
                ]:
                    raise SaveSafetyError("save_financial_schema_incompatible")
                names = [item[1] for item in old_columns]
                keys = [item[1] for item in old_columns if item[5]]
                fields = ",".join(f'"{name}"' for name in names)
                conflict = ",".join(f'"{name}"' for name in keys)
                assignments = ",".join(
                    f'"{name}"=excluded."{name}"' for name in names if name not in keys
                )
                placeholders = ",".join("?" for _ in names)
                statement = (
                    f'INSERT INTO "{table}" ({fields}) VALUES ({placeholders}) '
                    f"ON CONFLICT ({conflict}) DO UPDATE SET {assignments}"
                )
                destination.executemany(
                    statement, source.execute(f'SELECT {fields} FROM "{table}"')
                )
            destination.commit()
        finally:
            source.close()
            destination.close()
    except sqlite3.DatabaseError:
        # Do not silently discard newer known spending or hard-budget reservations.
        raise SaveSafetyError("save_financial_metadata_unavailable") from None


def quarantine_restored_tasks(database: Path) -> None:
    """Only operational state changes; canonical history and message bodies stay intact."""
    connection = sqlite3.connect(database)
    try:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_schema WHERE type='table'")
        }
        if {"chat_turn_dispatches", "chat_reply_executions", "chat_turns"} <= tables:
            stamp = datetime.now(UTC).isoformat(timespec="microseconds")
            connection.execute(
                "INSERT OR IGNORE INTO chat_turn_dispatches(world_id,turn_id,claimed_at_utc) "
                "SELECT world_id,turn_id,? FROM chat_turns",
                (stamp,),
            )
            connection.execute(
                "INSERT OR IGNORE INTO chat_reply_executions(world_id,turn_id,state) "
                "SELECT world_id,turn_id,'unknown' FROM chat_turns"
            )
            connection.execute(
                "UPDATE chat_reply_executions SET state='unknown' WHERE state='running'"
            )
        for table in (
            "director_settings",
            "world_news_settings",
            "offline_contact_settings",
            "proactive_contact_settings",
        ):
            if table in tables:
                connection.execute(
                    f"UPDATE \"{table}\" SET enabled=0,state='off',revision=revision+1"
                )
        for table, states in (
            ("director_plans", ("planning",)),
            ("world_news_batches", ("queued", "dispatched")),
            ("offline_contact_episodes", ("queued", "planning", "writing")),
            ("proactive_contact_episodes", ("writing",)),
        ):
            if table in tables:
                placeholders = ",".join("?" for _ in states)
                connection.execute(
                    f"UPDATE \"{table}\" SET state='interrupted',error='save_restored' "
                    f"WHERE state IN ({placeholders})",
                    states,
                )
        if "speech_jobs" in tables:
            connection.execute(
                "UPDATE speech_jobs SET state='interrupted',error='save_restored' "
                "WHERE state IN ('pending','queued','submitted','running','generating')"
            )
        if "chat_media_assets" in tables:
            connection.execute(
                "UPDATE chat_media_assets SET caption_state='failed' WHERE caption_state='running'"
            )
        if "chat_media_caption_calls" in tables:
            connection.execute(
                "UPDATE chat_media_caption_calls SET state='unknown' WHERE state='running'"
            )
        if "llm_budget_reservations" in tables:
            connection.execute(
                "UPDATE llm_budget_reservations SET status='held_uncertain' WHERE status='held'"
            )
        connection.commit()
    finally:
        connection.close()


def clear_saved_data(app_data: Path, confirmation: str, include_backups: bool) -> dict:
    if confirmation != "删除全部数据" or app_data.name != IDENTITY:
        raise SaveSafetyError("save_confirmation_required")
    app_data = plain(app_data)
    erase_roots = roots() if include_backups else []
    for root in erase_roots:
        owner = root / ".dreamtalk-backup-root.json"
        if not owner.exists() or read_json(owner).get("identity") != IDENTITY:
            raise SaveSafetyError("save_backup_ownership_unconfirmed")
        for name in ("snapshots", "damaged-preserved"):
            folder = root / name
            if folder.exists():
                inventory(folder)
    temporary = backup_root() / f"clear-working-{uuid4()}"
    temporary.mkdir(parents=True)
    clean = temporary / "runtime.sqlite3"
    source = sqlite3.connect((app_data / "data/runtime.sqlite3").as_uri() + "?mode=ro", uri=True)
    destination = sqlite3.connect(clean)
    try:
        source.backup(destination)
        destination.execute("PRAGMA defer_foreign_keys=ON")
        # Only this disposable replacement is emptied. Preserve the exact
        # immutable-event/FTS triggers, which otherwise correctly reject erasure.
        triggers = list(
            destination.execute("SELECT name,sql FROM sqlite_schema WHERE type='trigger'")
        )
        for name, _sql in triggers:
            if not re.fullmatch(r"[A-Za-z0-9_]+", name):
                raise SaveSafetyError("save_schema_invalid")
            destination.execute(f'DROP TRIGGER "{name}"')
        # Delete business/content tables; keep non-content billing guards intact.
        entries = list(destination.execute("PRAGMA table_list"))
        for kind in ("table", "virtual"):
            for schema, name, table_type, *_rest in entries:
                if (
                    schema != "main"
                    or table_type != kind
                    or name.startswith("sqlite_")
                    or name in (*ACCOUNTING, "alembic_version")
                ):
                    continue
                if not re.fullmatch(r"[A-Za-z0-9_]+", name):
                    raise SaveSafetyError("save_schema_invalid")
                destination.execute(f'DELETE FROM "{name}"')
        for _name, sql in triggers:
            destination.execute(sql)
        destination.commit()
        destination.execute("PRAGMA journal_mode=DELETE")
        destination.execute("VACUUM")  # remove private text from freed pages in the replacement
    finally:
        source.close()
        destination.close()
    if metadata(temporary, integrity=True)["counts"]["worlds"] != 0:
        raise SaveSafetyError("save_clear_failed")
    cleanup = app_data / "config/credential-cleanup.json"
    if cleanup.exists():
        pending = read_json(cleanup, 32 * 1024**2)
        if not isinstance(pending, list) or any(not isinstance(item, str) for item in pending):
            raise SaveSafetyError("save_credential_registry_unavailable")
        atomic_json(temporary / "credential-cleanup.json", pending)
    if app_data.resolve().name != IDENTITY or app_data.resolve().parent != plain(app_data.parent):
        raise SaveSafetyError("save_path_invalid")
    # The user explicitly selected erasure. No new private-data backup is created.
    shutil.rmtree(app_data)
    (app_data / "data").mkdir(parents=True)
    os.rename(clean, app_data / "data/runtime.sqlite3")
    if (temporary / "credential-cleanup.json").exists():
        (app_data / "config").mkdir()
        os.rename(
            temporary / "credential-cleanup.json", app_data / "config/credential-cleanup.json"
        )
    atomic_json(
        app_data / MARKER, {"identity": IDENTITY, "storage_id": str(uuid4()), "allow_empty": True}
    )
    if include_backups:
        for root in erase_roots:
            for name in ("snapshots", "damaged-preserved"):
                folder = plain(root / name)
                if folder.exists() and folder.parent == plain(root):
                    inventory(folder)
                    shutil.rmtree(folder)
    if plain(temporary).parent == plain(backup_root()):
        shutil.rmtree(temporary)
    return {"cleared": True, "billing_receipts_preserved": True, "backups_deleted": include_backups}


def verify_continuity(app_data: Path, snapshot_id: str) -> dict:
    folder = locate(snapshot_id)
    value = verify_snapshot(folder)
    actual = metadata(app_data / "data", integrity=True)
    with snapshot_database(folder) as (saved_data, frozen):
        _verify_database_continuity(app_data, saved_data, frozen=frozen)
    # Program startup cannot certify success with missing pictures/config.
    for name, expected in value["files"].items():
        if name in (
            "data/runtime.sqlite3",
            "data/runtime.sqlite3-wal",
            "data/runtime.sqlite3-shm",
        ):
            continue
        path = app_data / valid_relative(name)
        if not path.is_file() or digest(path) != expected["sha256"]:
            raise SaveSafetyError("save_update_assets_changed")
    return {"verified": True, "current": actual}


def _verify_database_continuity(app_data: Path, saved_data: Path, *, frozen: bool) -> None:
    suffix = "?mode=ro&immutable=1" if frozen else "?mode=ro"
    source = sqlite3.connect((saved_data / "runtime.sqlite3").as_uri() + suffix, uri=True)
    current = sqlite3.connect((app_data / "data/runtime.sqlite3").as_uri() + "?mode=ro", uri=True)
    try:
        for schema, table, kind, *_ in source.execute("PRAGMA table_list"):
            if (
                schema != "main"
                or kind != "table"
                or table.startswith("sqlite_")
                or table == "alembic_version"
            ):
                continue
            if not re.fullmatch(r"[A-Za-z0-9_]+", table):
                raise SaveSafetyError("save_schema_invalid")
            primary = [
                item[1]
                for item in sorted(
                    source.execute(f'PRAGMA table_info("{table}")'), key=lambda item: item[5]
                )
                if item[5]
            ]
            if any(not re.fullmatch(r"[A-Za-z0-9_]+", field) for field in primary):
                raise SaveSafetyError("save_schema_invalid")
            if not primary:
                continue
            fields = ",".join(f'"{field}"' for field in primary)
            rows = source.execute(f'SELECT {fields} FROM "{table}"')
            while batch := rows.fetchmany(256):
                placeholders = ",".join("(" + ",".join("?" for _ in primary) + ")" for _ in batch)
                found = set(
                    current.execute(
                        f'SELECT {fields} FROM "{table}" WHERE ({fields}) IN ({placeholders})',
                        [part for row in batch for part in row],
                    )
                )
                if not set(batch) <= found:
                    raise SaveSafetyError("save_update_continuity_failed")
            if table in CONTENT_TABLES:
                # Stream one immutable-content row at a time, including BLOBs.
                # Nothing is logged or sent to a model; only equality is reported.
                columns = [
                    item[1]
                    for item in source.execute(f'PRAGMA table_info("{table}")')
                    if not (table == "chat_media_assets" and item[1] == "caption_state")
                ]
                if any(not re.fullmatch(r"[A-Za-z0-9_]+", field) for field in columns):
                    raise SaveSafetyError("save_schema_invalid")
                names = ",".join(f'"{field}"' for field in columns)
                key_indices = [columns.index(field) for field in primary]
                predicate = " AND ".join(f'"{field}"=?' for field in primary)
                for old in source.execute(f'SELECT {names} FROM "{table}"'):
                    new = current.execute(
                        f'SELECT {names} FROM "{table}" WHERE {predicate}',
                        [old[index] for index in key_indices],
                    ).fetchone()
                    if old != new:
                        raise SaveSafetyError("save_update_content_changed")
    finally:
        source.close()
        current.close()


def adopt_legacy_update(app_data: Path, recovery: Path) -> dict:
    recovery = plain(recovery)
    if (
        recovery.parent != plain(app_data / "updates/recovery")
        or str(UUID(recovery.name)) != recovery.name
    ):
        raise SaveSafetyError("save_legacy_update_invalid")
    record = read_json(recovery / ".dreamtalk-snapshot.json", 32 * 1024**2)
    if record.get("identity") != IDENTITY or len(record["files"]) > MAX_FILES:
        raise SaveSafetyError("save_legacy_update_invalid")
    for name, expected in record["files"].items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or ":" in name:
            raise SaveSafetyError("save_legacy_update_invalid")
        path = plain(recovery / relative)
        if not path.is_relative_to(recovery) or digest(path) != expected:
            raise SaveSafetyError("save_snapshot_damaged")
    name = str(uuid4())
    root = backup_root()
    folder = plain(root / "incomplete" / name)
    payload = folder / "payload"
    payload.mkdir(parents=True)
    for part in ("data", "config"):
        source = recovery / part
        if source.is_dir():
            if part == "data":
                (payload / part).mkdir()
                for child in source.iterdir():
                    if child.name == "cache":
                        continue
                    plain(child)
                    if child.is_dir():
                        inventory(child)
                        shutil.copytree(child, payload / part / child.name)
                    else:
                        shutil.copy2(child, payload / part / child.name)
            else:
                inventory(source)
                shutil.copytree(source, payload / part)
    identity = storage_id(app_data)
    atomic_json(payload / MARKER, {"identity": IDENTITY, "storage_id": identity})
    value = {
        "identity": IDENTITY,
        "format": FORMAT,
        "id": name,
        "storage_id": identity,
        "created_at": datetime.now(UTC).isoformat(),
        "version": record["version"],
        "reason": "pre_update",
        "complete": True,
        "files": inventory(payload),
        "info": None,
    }
    atomic_json(folder / "snapshot.json", value)
    verified = verify_snapshot(folder)
    value["info"] = verified["info"]
    atomic_json(folder / "snapshot.json", value)
    target = plain(root / "snapshots" / name)
    target.parent.mkdir(parents=True, exist_ok=True)
    os.rename(folder, target)
    return {"id": name}


def export_snapshot(snapshot_id: str, output: Path) -> dict:
    folder = locate(snapshot_id)
    value = verify_snapshot(folder)
    plain(output)
    if output.exists() or output.suffix != ".dreamsave":
        raise SaveSafetyError("save_export_target_invalid")
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=3) as archive:
        # Export canonical keys and omit the rebuildable WAL index. Do not alter
        # an older source snapshot just to make it portable.
        value["files"] = {
            name: info
            for name, info in value["files"].items()
            if name != "data/runtime.sqlite3-shm"
        }
        archive.writestr("snapshot.json", json.dumps(value, ensure_ascii=False))
        for name in value["files"]:
            archive.write(folder / "payload" / valid_relative(name), f"payload/{name}")
    return {"exported": True}


def import_snapshot(source: Path) -> dict:
    plain(source)
    temporary = backup_root() / f"import-{uuid4()}"
    temporary.mkdir(parents=True)
    total = 0
    with zipfile.ZipFile(source) as archive:
        entries = archive.infolist()
        if len(entries) > MAX_FILES + 1 or len({item.filename for item in entries}) != len(entries):
            raise SaveSafetyError("save_import_invalid")
        for item in entries:
            name = item.filename
            if name == "snapshot.json":
                relative = Path(name)
            elif name.startswith("payload/"):
                relative = Path("payload") / valid_relative(name[8:])
            else:
                raise SaveSafetyError("save_import_invalid")
            total += item.file_size
            if total > MAX_BYTES or ((item.external_attr >> 16) & 0o170000) == 0o120000:
                raise SaveSafetyError("save_import_invalid")
            target = temporary / relative
            if not target.resolve().is_relative_to(temporary.resolve()):
                raise SaveSafetyError("save_import_invalid")
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(item) as input_stream, target.open("xb") as output_stream:
                shutil.copyfileobj(input_stream, output_stream)
    value = read_json(temporary / "snapshot.json", 32 * 1024**2)
    name = str(UUID(value["id"]))
    target = backup_root() / "snapshots" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        existing = verify_snapshot(target)
        existing["original_reason"] = existing.get("original_reason", existing["reason"])
        existing["reason"] = "imported"
        atomic_json(target / "snapshot.json", existing)
        return {"id": name, "already_present": True}
    staged = temporary.parent / name
    if staged.exists():
        raise SaveSafetyError("save_import_invalid")
    os.rename(temporary, staged)
    value = verify_snapshot(staged)
    value["original_reason"] = value["reason"]
    value["reason"] = "imported"
    atomic_json(staged / "snapshot.json", value)
    os.rename(staged, target)
    return {"id": name}


def run_request(request_path: Path) -> None:
    """Private host tool. JSON-only output, no credentials or private content."""
    try:
        request = read_json(request_path, 32_768)
        app_data = plain(Path(request["app_data"]))
        version = request.get("version", "")
        action = request["action"]
        if action in ("status", "guard"):
            result = guard(app_data, include_snapshots=action == "status")
        elif action == "backup":
            if (
                request.get("expected_file_identity")
                and metadata(app_data / "data")["file_identity"]
                != request["expected_file_identity"]
            ):
                raise SaveSafetyError("save_storage_context_mismatch")
            result = create_snapshot(
                app_data,
                request.get("reason", "manual"),
                version,
                automatic=request.get("automatic", False),
            )
        elif action == "restore":
            result = restore(app_data, request["snapshot_id"], version)
        elif action == "resume":
            metadata(app_data / "data", integrity=True)
            (app_data / "restore-hold.json").unlink(missing_ok=True)
            result = {"resumed": True}
        elif action == "configure":
            result = configure_location(
                Path(request["directory"]),
                app_data,
                Path(request["program_root"]) if request.get("program_root") else None,
            )
        elif action == "clear":
            result = clear_saved_data(
                app_data, request.get("confirmation", ""), request.get("include_backups", False)
            )
        elif action == "export":
            result = export_snapshot(request["snapshot_id"], Path(request["output"]))
        elif action == "import":
            result = import_snapshot(Path(request["source"]))
        elif action == "verify_update":
            if (
                request.get("expected_file_identity")
                and metadata(app_data / "data")["file_identity"]
                != request["expected_file_identity"]
            ):
                raise SaveSafetyError("save_storage_context_mismatch")
            result = verify_continuity(app_data, request["snapshot_id"])
        elif action == "adopt_legacy_update":
            if metadata(app_data / "data")["file_identity"] != request["expected_file_identity"]:
                raise SaveSafetyError("save_storage_context_mismatch")
            result = adopt_legacy_update(app_data, Path(request["recovery"]))
        else:
            raise SaveSafetyError("save_action_invalid")
        print(json.dumps({"ok": True, "result": result}, ensure_ascii=False))
    except Exception as error:
        code = str(error) if isinstance(error, SaveSafetyError) else "save_operation_failed"
        print(json.dumps({"ok": False, "error": code}))
        raise SystemExit(1) from None
