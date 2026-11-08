"""Mobile host state must not leak into desktop archive regression fixtures."""

import pytest
from livingworld.infrastructure import save_safety


@pytest.fixture(autouse=True)
def isolated_mobile_storage_adapter(monkeypatch):
    monkeypatch.setattr(save_safety, "_mobile_root", None)
