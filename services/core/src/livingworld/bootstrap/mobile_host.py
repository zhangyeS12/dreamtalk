"""Android-only in-process host. Secrets enter through Keystore and never leave this boundary."""

from __future__ import annotations

import asyncio
import json
import re
import secrets
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from livingworld.bootstrap.reader import derive_session

_lock = threading.RLock()
_thread = None
_loop = None
_root = None
_host = None
_settings = {}
_bootstrap_secret = ""
_nonce = ""
_maintenance = None
_shutdown = None
_start_error = None
_start_diagnostic = {}
_start_phase = "not_started"
_credentials = None
_session = None
_startup_backup_done = False
_startup_backup_error = None
_allowed_origins = ("http://tauri.localhost", "https://tauri.localhost", "tauri://localhost")


_START_CODES = frozenset(
    {
        "mobile_data_path_invalid",
        "mobile_secure_store",
        "mobile_core_start_failed",
        "mobile_core_timeout",
        "mobile_core_exited",
        "save_link_rejected",
        "save_path_invalid",
        "save_recovery_required",
        "save_record_invalid",
        "save_restore_interrupted",
        "save_slot_catalog_invalid",
        "save_backup_location_invalid",
        "save_snapshot_damaged",
        "save_database_missing",
    }
)


def _record_start_failure(error, phase=None):
    """Keep fixed failure facts only; never exception text, paths, settings or locals."""
    global _start_error, _start_diagnostic
    if _start_diagnostic.get("error_type"):
        return
    import traceback

    error_type = type(error).__name__.rsplit(".", 1)[-1]
    if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]{0,127}", error_type):
        error_type = "UnknownError"
    _start_error = error_type
    args = error.args
    code = (
        args[0]
        if len(args) == 1 and type(args[0]) is str and args[0] in _START_CODES
        else "mobile_startup_failed"
    )
    frames = []
    for frame in traceback.extract_tb(error.__traceback__):
        path = Path(frame.filename)
        if "livingworld" not in path.parts:
            continue
        parts = path.parts[path.parts.index("livingworld") :]
        module = ".".join((*parts[:-1], path.stem))
        frames.append(
            {
                "module": module,
                "file": path.name,
                "line": frame.lineno,
                "function": frame.name,
            }
        )
    _start_diagnostic = {
        "phase": phase or _start_phase,
        "code": code,
        "error_type": error_type,
        "frames": frames[-8:],
    }
    if isinstance(error, ModuleNotFoundError) and isinstance(error.name, str):
        if re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*", error.name):
            _start_diagnostic["missing_module"] = error.name[:160]


def _data_root(host):
    # This parent is provided by Android Context, never a user-selected path.
    # Resolve only that trusted prefix: keep a linked managed root/child rejectable.
    path = Path(str(host.dataDirectory()))
    if not path.is_absolute() or not path.name:
        raise ValueError("mobile_data_path_invalid")
    return path.parent.resolve() / path.name


def _diagnostics():
    return {
        "app": "dreamtalk",
        "android_preview": "0.1.4",
        "core_running": bool(_thread and _thread.is_alive()),
        "startup": _start_diagnostic or {"phase": _start_phase},
    }


def _sync_visibility():
    if _loop and _maintenance:
        visible = bool(_host.isForeground()) if hasattr(_host, "isForeground") else True
        background = (
            bool(_host.isBackgroundRunning()) if hasattr(_host, "isBackgroundRunning") else False
        )
        admitted = visible or background

        def apply():
            was_suspended = _maintenance.suspended
            _maintenance.suspended = not admitted
            if was_suspended and admitted:
                _maintenance.on_resume()

        _loop.call_soon_threadsafe(apply)


def attach(session, maintenance, shutdown):
    global _loop, _maintenance, _shutdown, _credentials, _session
    _loop = asyncio.get_running_loop()
    _maintenance, _shutdown, _credentials, _session = (
        maintenance,
        shutdown,
        session.credentials,
        session,
    )
    from livingworld.application.llm_config import SecretRef
    from livingworld.bootstrap.mobile_settings import credentials_for

    for world, reference, secret in credentials_for(_settings):
        if world:
            _credentials.upsert_media(UUID(world), SecretRef(UUID(reference)), secret)
        else:
            _credentials.upsert(SecretRef(UUID(reference)), secret)
    _credentials.complete_sync(secure_store_available=True)
    _sync_visibility()
    if hasattr(_host, "tokenUpperBound"):
        from livingworld.infrastructure.llm.request_bounds import configure_mobile_counter

        configure_mobile_counter(lambda payload: int(_host.tokenUpperBound(payload)))


def validate_model(value, previous):
    allowed = {
        "provider_kind",
        "model_id",
        "base_url",
        "max_billable_input_tokens",
        "max_output_tokens",
        "streaming",
        "timeout_ms",
        "native_json",
        "secret",
    }
    if type(value) is not dict or set(value) - allowed:
        raise ValueError("mobile_invalid")
    kinds = {"openai-compatible", "openai-responses", "anthropic-messages", "gemini-interactions"}
    if value.get("provider_kind") not in kinds:
        raise ValueError("mobile_invalid")
    name = value.get("model_id", "")
    if not isinstance(name, str) or not name.strip() or len(name.encode()) > 128:
        raise ValueError("mobile_invalid")
    for key in ("max_billable_input_tokens", "max_output_tokens", "timeout_ms"):
        count = value.get(key)
        if type(count) is not int or not 1 <= count <= (
            600000 if key == "timeout_ms" else 2147483647
        ):
            raise ValueError("mobile_invalid")
    if type(value.get("streaming")) is not bool:
        raise ValueError("mobile_invalid")
    base = value.get("base_url")
    if value["provider_kind"] == "openai-compatible":
        if not isinstance(base, str) or any(c.isspace() for c in base) or "\\" in base:
            raise ValueError("mobile_invalid")
        parsed = urlsplit(base)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("mobile_invalid")
    else:
        base = None
    secret = value.get("secret") or previous.get("secret")
    if not isinstance(secret, str) or not secret or len(secret.encode()) > 4096:
        raise ValueError("mobile_invalid")
    setup = {key: value[key] for key in allowed - {"secret", "base_url", "native_json"}}
    if "native_json" in value:
        if type(value["native_json"]) is not bool:
            raise ValueError("mobile_invalid")
        setup["native_json"] = value["native_json"]
    setup["model_id"], setup["base_url"] = name.strip(), base
    return {
        "setup": setup,
        "secret": secret,
        "secret_ref": previous.get("secret_ref") or str(uuid4()),
    }


def single_document(settings):
    if not settings.get("setup"):
        return {"version": 1}
    setup = settings["setup"]
    provider = {
        "provider_id": "mobile-chat",
        "adapter_kind": setup["provider_kind"],
        "secret_ref": settings["secret_ref"],
        "timeout_ms": setup["timeout_ms"],
    }
    if setup["base_url"]:
        provider["base_url"] = setup["base_url"]
    capabilities = {"text_generation": True, "streaming": setup["streaming"]}
    profile = {"supports_streaming": True} if setup["streaming"] else {}
    if setup["provider_kind"] == "openai-compatible" and setup["streaming"]:
        profile["supports_stream_usage"] = True
    if setup.get("native_json"):
        capabilities.update(
            structured_output=True, structured_output_mode="json_object_local_validate"
        )
        profile["structured_output_mode"] = "json_object_local_validate"
    return {
        "version": 1,
        "providers": [provider],
        "models": [
            {
                "provider_id": "mobile-chat",
                "model_id": setup["model_id"],
                "enabled": True,
                "capabilities": capabilities,
                "limits": {
                    "max_billable_input_tokens": setup["max_billable_input_tokens"],
                    "max_output_tokens": setup["max_output_tokens"],
                },
                "adapter_profile": profile,
            }
        ],
        "routes": [],
        "execution_policy": {},
        "pricing_catalog": {
            "catalog_id": "empty",
            "source_label": "configured-empty",
            "schedules": [],
            "aliases": [],
        },
    }


def production_document(settings):
    from livingworld.bootstrap.mobile_settings import document

    return document(settings, single_document)


def _start():
    global \
        _thread, \
        _bootstrap_secret, \
        _nonce, \
        _start_error, \
        _loop, \
        _maintenance, \
        _shutdown, \
        _startup_backup_done, \
        _startup_backup_error, \
        _start_diagnostic, \
        _start_phase
    if _thread and _thread.is_alive():
        return
    _start_error, _loop, _maintenance, _shutdown = None, None, None, None
    _start_diagnostic = {}
    _start_phase = "storage_prepare"
    _root.mkdir(parents=True, exist_ok=True)
    from livingworld.bootstrap.mobile_storage import prepare_storage

    prepare_storage(_root)
    from livingworld.infrastructure import save_slots

    if not (_root / "data/runtime.sqlite3").exists() and any(save_slots.status()["slots"]):
        raise ValueError("save_recovery_required")
    from livingworld.infrastructure.save_safety import guard

    _start_phase = "storage_guard"
    if (_root / "data/runtime.sqlite3").exists() and guard(_root, include_snapshots=False)[
        "recovery_required"
    ]:
        raise ValueError("save_recovery_required")
    if not _startup_backup_done and (_root / "data/runtime.sqlite3").is_file():
        from livingworld.infrastructure import save_slots

        try:
            state = save_slots.status()
            save_slots.save(
                _root,
                "0.1.4",
                0,
                (state["slots"][0] or {}).get("name", "自动存档"),
                state["revision"],
            )
            _startup_backup_done, _startup_backup_error = True, None
        except Exception:
            # Keep the current database usable; show an explicit manual retry.
            _startup_backup_done, _startup_backup_error = True, "save_startup_backup_failed"
    _start_phase = "model_configuration"
    runtime = _root / "runtime"
    runtime.mkdir(exist_ok=True)
    _bootstrap_secret, _nonce = secrets.token_hex(32), str(uuid4())
    config_path = _root / "llm.json"
    temporary = config_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(production_document(_settings)), encoding="utf-8")
    from livingworld.infrastructure.llm.production_config import load_configuration

    load_configuration(temporary)
    temporary.replace(config_path)
    _start_phase = "bootstrap_write"
    bootstrap = runtime / "bootstrap.json"
    bootstrap.write_text(
        json.dumps(
            {
                "bootstrap_secret": _bootstrap_secret,
                "instance_nonce": _nonce,
                "protocol_min": 1,
                "protocol_max": 1,
                "data_dir": str(_root / "data"),
                "log_dir": str(_root / "logs"),
                "llm_config_path": str(config_path),
                "allowed_origins": list(_allowed_origins),
            }
        ),
        encoding="utf-8",
    )
    # Clear only this host's stale readiness marker before scheduling the Core.
    (runtime / "ready.json").unlink(missing_ok=True)

    def run():
        phase = "core_import"
        try:
            from livingworld.bootstrap.cli import run as run_core

            phase = "core_run"
            asyncio.run(run_core(bootstrap, native_host=__import__(__name__, fromlist=["attach"])))
            if not _shutdown or not _shutdown.event.is_set():
                _record_start_failure(RuntimeError("mobile_core_exited"), phase)
        except BaseException as error:
            _record_start_failure(error, phase)

    _thread = threading.Thread(target=run, name="dreamtalk-core", daemon=True)
    _thread.start()


def _connection():
    global _start_phase, _start_error, _start_diagnostic
    _start()
    _start_phase = "readiness"
    ready = _root / "runtime/ready.json"
    deadline = time.monotonic() + 75
    while time.monotonic() < deadline:
        if _start_error or not _thread.is_alive():
            raise ValueError("mobile_core_start_failed")
        try:
            result = json.loads(ready.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            # The producer removes its previous marker and publishes the next one.
            # This is a local readiness race, not a provider request or retry.
            pass
        else:
            if result.get("instance_nonce") == _nonce:
                if _start_error or not _thread.is_alive():
                    raise ValueError("mobile_core_start_failed")
                _start_error, _start_diagnostic, _start_phase = None, {}, "ready"
                return {
                    "endpoint": result["endpoint"],
                    "generation": result["generation"],
                    "token": derive_session(_bootstrap_secret, _nonce, result["generation"]),
                }
        time.sleep(0.05)
    raise ValueError("mobile_core_timeout")


def _stop_if_idle():
    if not _thread or not _thread.is_alive() or not _loop or not _shutdown or not _maintenance:
        return

    async def stop():
        _maintenance.prepare()
        try:
            async with asyncio.timeout(10):
                await _maintenance.wait_idle()
        except TimeoutError:
            _maintenance.cancel()
            raise ValueError("mobile_busy") from None
        from livingworld.domain.contracts import RequestId

        _shutdown.request(RequestId(uuid4()))

    asyncio.run_coroutine_threadsafe(stop(), _loop).result(timeout=15)
    _thread.join(timeout=15)
    if _thread.is_alive():
        raise ValueError("mobile_busy")


def dispatch(operation, payload, host):
    global _start_diagnostic, _start_error, _start_phase
    with _lock:
        # Diagnostics must remain usable even if directory or Keystore setup failed.
        if operation == "copy_diagnostics":
            host.copyDiagnostic(json.dumps(_diagnostics(), ensure_ascii=False))
            return json.dumps({"result": True})
        starting = operation == "connection" and not (_thread and _thread.is_alive())
        if starting:
            _start_diagnostic, _start_error, _start_phase = {}, None, "data_directory"
        try:
            return _dispatch(operation, payload, host)
        except BaseException as error:
            if operation == "connection":
                _record_start_failure(error)
            raise


def _dispatch(operation, payload, host):
    global _root, _host, _settings, _start_phase
    with _lock:
        _host = host
        _root = _data_root(host)
        if not _settings:
            if operation == "connection":
                _start_phase = "secure_store"
            try:
                _settings = json.loads(str(host.secureRead()))
            except Exception as error:
                if operation == "connection":
                    _record_start_failure(error, "secure_store")
                raise ValueError("mobile_secure_store") from None
        value = json.loads(payload)
        if operation == "visibility":
            _sync_visibility()
            result = True
        elif operation == "connection":
            result = _connection()
        elif operation == "model_status":
            result = _settings.get("setup")
        elif operation == "configure_model":
            updated = {**_settings, **validate_model(value, _settings)}
            from livingworld.infrastructure.llm.production_config import load_configuration

            check_path = _root / ("model-check-" + str(uuid4()) + ".json")
            _root.mkdir(parents=True, exist_ok=True)
            try:
                check_path.write_text(json.dumps(production_document(updated)), encoding="utf-8")
                load_configuration(check_path)
            finally:
                check_path.unlink(missing_ok=True)
            _stop_if_idle()
            previous = _settings
            try:
                host.secureWrite(json.dumps(updated))
            except Exception:
                _settings = previous
                _start()
                raise ValueError("mobile_secure_store") from None
            _settings = updated
            result = _connection()
        elif operation == "stop":
            _stop_if_idle()
            result = True
        else:
            from livingworld.bootstrap.mobile_notifications import dispatch_notifications
            from livingworld.bootstrap.mobile_settings import dispatch_settings
            from livingworld.bootstrap.mobile_storage import dispatch_storage

            handled, result = dispatch_settings(
                operation, value, __import__(__name__, fromlist=["dispatch"])
            )
            if not handled:
                handled, result = dispatch_storage(
                    operation, value, __import__(__name__, fromlist=["dispatch"])
                )
            if not handled:
                handled, result = dispatch_notifications(
                    operation, value, __import__(__name__, fromlist=["dispatch"])
                )
            if not handled:
                raise ValueError("mobile_invalid_operation")
        return json.dumps({"result": result})
