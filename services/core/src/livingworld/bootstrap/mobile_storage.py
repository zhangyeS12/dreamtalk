"""Mobile wrapper over the existing verified five-slot archive implementation."""

from pathlib import Path
from uuid import uuid4

from livingworld.infrastructure import save_safety as safety
from livingworld.infrastructure import save_slots as slots

VERSION = "0.1.3"


def prepare_storage(root):
    safety._mobile_root = root.parent / "dreamtalk-backups"
    slots.recover(root)
    if slots.directory() is None:
        slots.configure(root.parent / "dreamtalk-saves", root, root / "program")


def _source(root, value):
    path = Path(value).resolve()
    transfer = (root.parent / "dreamtalk-transfers").resolve()
    if path.parent != transfer or not path.is_file() or path.is_symlink():
        raise ValueError("mobile_invalid")
    return path


def dispatch_storage(operation, value, host):
    if operation not in {
        "save_slots_status",
        "choose_save_slots_folder",
        "operate_save_slot",
        "mobile_export_path",
    }:
        return False, None
    prepare_storage(host._root)
    if operation in {"save_slots_status", "choose_save_slots_folder"}:
        if not host._startup_backup_done and host._thread and host._thread.is_alive():
            host._stop_if_idle()
            try:
                state = slots.status()
                slots.save(
                    host._root,
                    VERSION,
                    0,
                    (state["slots"][0] or {}).get("name", "自动存档"),
                    state["revision"],
                )
                host._startup_backup_done = True
            finally:
                host._connection()
        return True, {**slots.status(), "startup_error": host._startup_backup_error}
    if operation == "mobile_export_path":
        request = value["request"]
        target = host._root.parent / "dreamtalk-transfers" / (str(uuid4()) + ".dreamsave")
        target.parent.mkdir(exist_ok=True)
        slots.export_file(request["slot"], request["revision"], target)
        return True, str(target)
    request = value["request"]
    action, slot, revision = request["action"], request["slot"], request["revision"]
    if request.get("confirmed") is not True:
        raise ValueError("mobile_invalid")
    if action in {"save", "load", "retry_auto"}:
        host._stop_if_idle()
        try:
            if action == "load":
                result = slots.load(host._root, VERSION, slot, revision)
                # Restoring a different database must never notify historical messages.
                (host._root / "notification-cursor.json").unlink(missing_ok=True)
            else:
                result = slots.save(
                    host._root,
                    VERSION,
                    0 if action == "retry_auto" else slot,
                    (slots.status()["slots"][0] or {}).get("name", "自动存档")
                    if action == "retry_auto"
                    else request["name"],
                    revision,
                )
                if action == "retry_auto":
                    host._startup_backup_error = None
        finally:
            host._connection()
        return True, result
    if action == "import":
        source = _source(host._root, request["source"])
        try:
            return True, slots.import_file(source, slot, request["name"], revision)
        finally:
            source.unlink(missing_ok=True)
    if action == "copy_auto":
        return True, slots.copy_automatic(slot, request["name"], revision)
    if action == "rename":
        return True, slots.rename(slot, request["name"], revision)
    raise ValueError("mobile_invalid")
