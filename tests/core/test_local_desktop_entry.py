"""Local delivery must survive unrelated Cargo builds and preserve unknown files."""

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/build-local-desktop.py"
spec = importlib.util.spec_from_file_location("local_desktop_build", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_delivered_entry_is_independent_of_later_cargo_output(tmp_path):
    source = tmp_path / "cargo.exe"
    source.write_bytes(b"synthetic embedded application")
    delivered = tmp_path / "local"
    module.publish_entry(source, delivered, "0.1.81")
    source.write_bytes(b"synthetic development server application")
    assert (delivered / "dreamtalk-desktop.exe").read_bytes() == b"synthetic embedded application"
    module.publish_entry(source, delivered, "0.1.82")
    receipt = json.loads((delivered / "entry.json").read_text("utf-8"))
    assert receipt["version"] == "0.1.82"
    assert receipt["sha256"] == module.digest(delivered / "dreamtalk-desktop.exe")


def test_unknown_or_modified_entry_is_preserved(tmp_path):
    source = tmp_path / "cargo.exe"
    source.write_bytes(b"owned build")
    delivered = tmp_path / "local"
    module.publish_entry(source, delivered, "0.1.81")
    entry = delivered / "dreamtalk-desktop.exe"
    entry.write_bytes(b"unknown replacement")
    with pytest.raises(ValueError, match="local_entry_modified"):
        module.publish_entry(source, delivered, "0.1.81")
    assert entry.read_bytes() == b"unknown replacement"
