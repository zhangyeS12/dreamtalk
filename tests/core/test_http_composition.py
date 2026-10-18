"""Composition regression checks; no database, desktop or external provider."""

import io

import pytest
from fastapi.testclient import TestClient
from livingworld.adapters.http.app import create_app, create_product_app
from livingworld.adapters.http.services import HttpServices
from livingworld.application.runtime import RuntimeStatus, ShutdownRequests
from livingworld.infrastructure.logging import StructuredLogger


def test_product_rejects_missing_wiring_before_initialization():
    initialized = []
    with pytest.raises(ValueError, match="Missing product HTTP services") as error:
        create_product_app(
            RuntimeStatus("synthetic", "generation"),
            ShutdownRequests(),
            "synthetic-session",
            lambda: initialized.append(True),
            StructuredLogger(io.StringIO()),
            services=HttpServices(),
        )
    assert "world_settings" in str(error.value)
    assert "chat_reply" not in str(error.value)
    assert "maintenance" in str(error.value)
    assert "developer_inspector" not in str(error.value)
    assert "storage_metadata" not in str(error.value)
    assert initialized == []


def test_explicit_partial_embedding_retains_lifespan_and_session_boundary():
    initialized = []
    status = RuntimeStatus("synthetic", "generation")
    app = create_app(
        status,
        ShutdownRequests(),
        "synthetic-session",
        lambda: initialized.append(True),
        StructuredLogger(io.StringIO()),
        services=HttpServices(),
    )
    assert status.ready is False
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert status.ready is True
        assert initialized == [True]
        assert client.get("/system/health").status_code == 401
        health = client.get("/system/health", headers={"Authorization": "Bearer synthetic-session"})
        assert health.status_code == 200
        assert health.json()["ready"] is True
    assert status.ready is False


def test_missing_model_configuration_is_a_valid_product_state():
    from dataclasses import fields
    from unittest.mock import Mock

    values = {field.name: Mock() for field in fields(HttpServices)}
    values.update(
        chat_reply=None,
        group_chat_reply=None,
        developer_inspector=None,
        storage_metadata=None,
        storage_observer=None,
    )
    HttpServices(**values).require_product()
