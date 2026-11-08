"""Synthetic app-directory aliases and redacted pre-thread failure diagnostics."""

import importlib
import json
import os
from types import SimpleNamespace

import pytest
from livingworld.bootstrap import mobile_host
from livingworld.infrastructure.save_safety import SaveSafetyError

CANARY = "SYNTHETIC_PRIVATE_TEXT_AND_SECRET_NOT_FOR_DIAGNOSTICS"


class Host:
    def __init__(self, root):
        self.root = root
        self.value = "{}"
        self.diagnostic = None

    def dataDirectory(self):
        return str(self.root)

    def secureRead(self):
        return self.value

    def secureWrite(self, value):
        self.value = value

    def isForeground(self):
        return True

    def copyDiagnostic(self, value):
        self.diagnostic = json.loads(value)


def make_alias(alias, target):
    assert target.is_dir()
    assert alias.parent.resolve().is_relative_to(target.parent.resolve())
    if os.name == "nt":
        import _winapi

        _winapi.CreateJunction(str(target), str(alias))
    else:
        alias.symlink_to(target, target_is_directory=True)
    assert alias.resolve() == target.resolve()


def diagnostics(module, host):
    assert json.loads(module.dispatch("copy_diagnostics", "{}", host)) == {"result": True}
    encoded = json.dumps(host.diagnostic)
    assert CANARY not in encoded
    assert str(host.root) not in encoded
    return host.diagnostic


@pytest.fixture
def runtime(tmp_path):
    module = importlib.reload(mobile_host)
    host = Host(tmp_path / "files/dreamtalk")
    yield module, host
    if module._thread and module._thread.is_alive() and module._loop:
        module._stop_if_idle()


def test_system_private_parent_alias_starts_core_and_keeps_same_data(tmp_path, runtime):
    module, host = runtime
    real = tmp_path / "actual-files"
    real.mkdir()
    alias = tmp_path / "android-private-alias"
    make_alias(alias, real)
    host.root = alias / "dreamtalk"
    connection = json.loads(module.dispatch("connection", "{}", host))["result"]
    assert connection["endpoint"].startswith("http://127.0.0.1:")
    assert module._root == real / "dreamtalk"
    assert (real / "dreamtalk/data/runtime.sqlite3").is_file()
    assert (host.root / "data/runtime.sqlite3").is_file()
    result = diagnostics(module, host)
    assert result["core_running"] is True and result["startup"] == {"phase": "ready"}


@pytest.mark.parametrize("linked", ["managed_root", "backup_root"])
def test_link_inside_managed_storage_still_rejected_and_recorded(tmp_path, runtime, linked):
    module, host = runtime
    files = tmp_path / "files"
    files.mkdir()
    target = tmp_path / "untrusted-target"
    target.mkdir()
    alias = files / ("dreamtalk" if linked == "managed_root" else "dreamtalk-backups")
    # Both alias and target are confined to the same synthetic test directory.
    if os.name == "nt":
        import _winapi

        _winapi.CreateJunction(str(target), str(alias))
    else:
        alias.symlink_to(target, target_is_directory=True)
    with pytest.raises(SaveSafetyError, match="save_link_rejected"):
        module.dispatch("connection", "{}", host)
    assert module._thread is None
    result = diagnostics(module, host)
    assert result["startup"]["phase"] == "storage_prepare"
    assert result["startup"]["code"] == "save_link_rejected"
    assert result["startup"]["error_type"] == "SaveSafetyError"
    assert result["startup"]["frames"]
    assert (target / "data/runtime.sqlite3").exists() is False


def test_diagnostics_survive_secure_store_failure_without_reading_store_again(runtime):
    module, host = runtime

    def fail():
        raise RuntimeError(CANARY)

    host.secureRead = fail
    with pytest.raises(ValueError, match="mobile_secure_store"):
        module.dispatch("connection", "{}", host)
    result = diagnostics(module, host)
    assert result["core_running"] is False
    assert result["startup"]["phase"] == "secure_store"
    assert result["startup"]["error_type"] == "RuntimeError"
    assert result["startup"]["code"] == "mobile_startup_failed"


def test_configuration_preflight_records_project_frames_but_not_values(runtime, monkeypatch):
    module, host = runtime

    def fail(_):
        raise RuntimeError(CANARY)

    monkeypatch.setattr(module, "production_document", fail)
    with pytest.raises(RuntimeError):
        module.dispatch("connection", "{}", host)
    result = diagnostics(module, host)
    assert result["startup"]["phase"] == "model_configuration"
    assert module._thread is None
    assert any(
        frame["module"] == "livingworld.bootstrap.mobile_host" and frame["function"] == "_start"
        for frame in result["startup"]["frames"]
    )


def test_new_successful_attempt_clears_previous_preflight_error(runtime):
    module, host = runtime
    original = host.secureRead

    def fail():
        raise RuntimeError(CANARY)

    host.secureRead = fail
    with pytest.raises(ValueError, match="mobile_secure_store"):
        module.dispatch("connection", "{}", host)
    assert diagnostics(module, host)["startup"]["error_type"] == "RuntimeError"
    host.secureRead = original
    module.dispatch("connection", "{}", host)
    assert diagnostics(module, host)["startup"] == {"phase": "ready"}


def test_unstarted_diagnostics_do_not_access_directory_or_keystore(runtime):
    module, host = runtime

    def fail():
        raise AssertionError("Diagnostic copy must not initialize storage")

    host.dataDirectory = host.secureRead = fail
    result = diagnostics(module, host)
    assert result["core_running"] is False
    assert result["startup"] == {"phase": "not_started"}


def test_readiness_timeout_is_distinct_from_empty_diagnostic(runtime, monkeypatch):
    module, host = runtime
    monkeypatch.setattr(module, "_thread", SimpleNamespace(is_alive=lambda: True))
    monkeypatch.setattr(module, "_start", lambda: None)
    times = iter([0, 100])
    monkeypatch.setattr(module.time, "monotonic", lambda: next(times))
    with pytest.raises(ValueError, match="mobile_core_timeout"):
        module.dispatch("connection", "{}", host)
    result = diagnostics(module, host)
    assert result["startup"]["phase"] == "readiness"
    assert result["startup"]["code"] == "mobile_core_timeout"
