"""Ensure the development wheel carries the shared protocol and all runtime layers."""

import json
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
wheel = next((root / "artifacts/core").glob("*.whl"))
with zipfile.ZipFile(wheel) as package:
    names = package.namelist()
    for layer in ["domain", "application", "infrastructure", "adapters/http", "bootstrap"]:
        assert f"livingworld/{layer}/__init__.py" in names
    source = root / "services/core/src/livingworld/domain/api_contract.json"
    assert json.loads(package.read("livingworld/domain/api_contract.json")) == json.loads(
        source.read_text()
    )
print("Core development wheel contract and layers: PASS")
