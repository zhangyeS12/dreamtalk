"""Offline safety regressions for the isolated Android acceptance entry."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def entry(tmp_path, monkeypatch):
    source = Path(__file__).resolve().parents[1] / "scripts/android-local.py"
    spec = importlib.util.spec_from_file_location("android_local_entry_test", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = tmp_path / "source"
    root.mkdir()
    monkeypatch.setattr(module, "ROOT", root)
    monkeypatch.setattr(module, "OUT", root / "artifacts/android-local")
    module.OUT.mkdir(parents=True)
    return module


def runtime(entry):
    path = entry.ROOT / "apps/web/src/runtime.ts"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("export const current = 1;", encoding="utf-8")
    return path


def make_receipt(entry):
    runtime(entry)
    apk = entry.OUT / "dreamtalk-android-local.apk"
    apk.write_bytes(b"synthetic local APK")
    value = {
        "apk": apk.relative_to(entry.ROOT).as_posix(),
        "sha256": entry.digest(apk),
        "local_only": True,
        "source": entry.source_fingerprint(),
    }
    entry.write_json(entry.OUT / "build-receipt.json", value)
    return value, apk


def test_fingerprint_tracks_runtime_but_ignores_docs_tests_and_outputs(entry):
    source = runtime(entry)
    original = entry.source_fingerprint()
    for name in ["docs/local.md", "apps/web/src/runtime.test.tsx", "artifacts/output.bin"]:
        path = entry.ROOT / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic", encoding="utf-8")
    assert entry.source_fingerprint() == original
    source.write_text("export const current = 2;", encoding="utf-8")
    assert entry.source_fingerprint() != original


def test_receipt_rejects_replaced_apk(entry):
    _, apk = make_receipt(entry)
    apk.write_bytes(b"another build")
    with pytest.raises(entry.LocalError, match="receipt_mismatch"):
        entry.current_build()


def test_receipt_cannot_select_an_apk_outside_local_output(entry):
    entry.write_json(
        entry.OUT / "build-receipt.json", {"apk": "../outside.apk", "local_only": True}
    )
    with pytest.raises(entry.LocalError, match="receipt_mismatch"):
        entry.current_build()


def test_source_edit_marks_existing_build_stale_without_modifying_it(entry):
    _, apk = make_receipt(entry)
    runtime(entry).write_text("export const current = 3;", encoding="utf-8")
    assert entry.current_build()["source_current"] is False
    assert apk.read_bytes() == b"synthetic local APK"


@pytest.mark.parametrize(
    "qemu,name",
    [
        ("0", "DreamtalkLocalAcceptance001"),
        ("1", "AnotherDevice"),
        ("1", "DreamtalkLocalAcceptance001-other"),
    ],
)
def test_device_identity_rejects_physical_or_other_avd(entry, monkeypatch, qemu, name):
    monkeypatch.setattr(
        entry,
        "adb",
        lambda _sdk, _env, *args: SimpleNamespace(
            stdout=qemu if args[0] == "shell" else name + "\nOK\n"
        ),
    )
    with pytest.raises(entry.LocalError, match="identity_mismatch"):
        entry.verify_device(Path("synthetic-sdk"), {})


def test_source_change_during_build_does_not_replace_receipt(entry):
    source = runtime(entry)
    entry.write_json(entry.OUT / "source-before.json", entry.source_fingerprint())
    candidate = entry.OUT / "candidate.apk"
    candidate.write_bytes(b"candidate")
    source.write_text("export const current = 4;", encoding="utf-8")
    with pytest.raises(entry.LocalError, match="source_changed_during_build"):
        entry.record_build(candidate)
    assert not (entry.OUT / "pending-build.json").exists()


def test_finalize_requires_exact_candidate_bytes(entry):
    entry.write_json(
        entry.OUT / "pending-build.json",
        {
            "apk": "artifacts/android-local/dreamtalk-android-local.apk",
            "sha256": "synthetic-wrong-digest",
            "local_only": True,
        },
    )
    (entry.OUT / "dreamtalk-android-local.apk").write_bytes(b"candidate")
    with pytest.raises(entry.LocalError, match="receipt_mismatch"):
        entry.finalize_build()
    assert not (entry.OUT / "build-receipt.json").exists()


def test_open_never_installs_when_device_identity_check_fails(entry, monkeypatch):
    value, _ = make_receipt(entry)
    monkeypatch.setattr(entry, "ensure_build", lambda _force: value)
    monkeypatch.setattr(entry, "start_device", lambda: (Path("synthetic-sdk"), {}))

    def reject(*_args):
        raise entry.LocalError("local_device_identity_mismatch")

    monkeypatch.setattr(entry, "verify_device", reject)
    monkeypatch.setattr(
        entry, "adb", lambda *_args, **_kwargs: pytest.fail("must not install or launch")
    )
    with pytest.raises(entry.LocalError, match="identity_mismatch"):
        entry.open_app()


def test_emulator_uses_explicit_compatible_graphics_without_wiping_data(entry):
    command = entry.emulator_command(Path("synthetic-sdk"))
    assert command[command.index("-gpu") + 1] == "host"
    assert command[command.index("-avd") + 1] == entry.NAME
    assert command[command.index("-port") + 1] == entry.SERIAL.removeprefix("emulator-")
    assert "-Vulkan" in command
    assert "-no-snapshot" in command
    assert not {"-wipe-data", "-read-only", "-no-window"}.intersection(command)


def test_host_emulator_exit_stops_boot_wait_and_records_only_exit_metadata(entry, monkeypatch):
    home = entry.ROOT / "synthetic-home"
    (home / "avd").mkdir(parents=True)
    monkeypatch.setattr(entry, "context", lambda: (entry.ROOT / "sdk", home, {}))
    monkeypatch.setattr(
        entry.subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(returncode=0)
    )
    monkeypatch.setattr(
        entry, "adb", lambda *_args, **_kwargs: SimpleNamespace(stdout="", returncode=1)
    )
    process = SimpleNamespace(pid=123, returncode=0xC0000005, poll=lambda: 0xC0000005)
    monkeypatch.setattr(entry.subprocess, "Popen", lambda *_args, **_kwargs: process)
    monkeypatch.setattr(
        entry.time, "sleep", lambda *_args: pytest.fail("must stop after host exit")
    )
    with pytest.raises(entry.LocalError, match="emulator_process_exited"):
        entry.start_device()
    import json

    metadata = json.loads((entry.OUT / "emulator-exit.json").read_text())
    assert metadata == {
        "stage": "boot",
        "returncode": 0xC0000005,
        "returncode_hex": "c0000005",
        "graphics_mode": "host",
    }
