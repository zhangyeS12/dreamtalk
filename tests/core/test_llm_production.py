"""Production composition, non-secret config, credentials and host-control invariants."""

import asyncio
import importlib.util
import json
import struct
from io import BytesIO, StringIO
from pathlib import Path
from uuid import UUID

import pytest
from livingworld.application.llm import (
    LLMMessage,
    LLMPurpose,
    LLMRequest,
    MessageRole,
    TextContent,
)
from livingworld.application.llm_config import LLMRuntimeHealth, SecretRef
from livingworld.application.llm_routing import (
    RouteIssue,
    RoutingError,
    RoutingProfile,
)
from livingworld.bootstrap import llm_runtime as composition
from livingworld.bootstrap.llm_control import (
    HOST_CONTROL_CONTRACT,
    MAX_FRAME_BYTES,
    PROTOCOL_VERSION,
    ControlProtocolError,
    HostControlListener,
    apply_message,
    decode_frame,
)
from livingworld.infrastructure.llm.credentials import SessionCredentialProvider
from livingworld.infrastructure.llm.fake import FakeModelGateway
from livingworld.infrastructure.llm.production_config import (
    CONFIG_VERSION,
    LLMProductionConfigurationError,
    load_configuration,
)
from livingworld.infrastructure.logging import StructuredLogger
from livingworld.infrastructure.persistence import Database
from sqlalchemy import text

SECRET_REFS = tuple(UUID(f"00000000-0000-0000-0000-00000000000{index}") for index in range(1, 5))
KINDS = ("openai-compatible", "anthropic", "gemini", "openai-responses")


def document():
    providers, models = [], []
    profiles = (
        {"supports_streaming": True, "structured_output_mode": "native_json_schema"},
        {"supports_streaming": True, "supports_native_structured_output": True},
        {"supports_streaming": True, "supports_native_structured_output": True},
        {"supports_streaming": True, "supports_native_structured_output": True},
    )
    for index, (kind, reference, profile) in enumerate(
        zip(KINDS, SECRET_REFS, profiles, strict=True)
    ):
        provider_id = f"provider-{index}"
        providers.append(
            {
                "provider_id": provider_id,
                "adapter_kind": kind,
                "base_url": f"https://provider-{index}.invalid",
                "secret_ref": str(reference),
            }
        )
        models.append(
            {
                "provider_id": provider_id,
                "model_id": f"opaque-{index}",
                "enabled": True,
                "capabilities": {
                    "text_generation": True,
                    "streaming": True,
                    "structured_output": True,
                    "structured_output_mode": "native_json_schema",
                },
                "limits": {
                    "max_billable_input_tokens": 2048,
                    "max_output_tokens": 128,
                },
                "adapter_profile": profile,
            }
        )
    identities = [
        {"provider_id": model["provider_id"], "model_id": model["model_id"]} for model in models
    ]
    return {
        "version": CONFIG_VERSION,
        "providers": providers,
        "models": models,
        "routes": [
            {
                "policy_id": f"default-{profile}",
                "profile": profile,
                "candidates": identities,
                "allowed_fallback": ["candidate_unavailable"],
            }
            for profile in ("fast", "balanced", "best")
        ],
        "execution_policy": {
            "max_attempts": 2,
            "initial_backoff_seconds": 0.1,
            "max_backoff_seconds": 1.0,
            "max_elapsed_seconds": 3.0,
            "jitter": "none",
        },
        "pricing_catalog": {
            "catalog_id": "controlled-offline",
            "source_label": "fixture-2026-09-19",
            "schedules": [],
            "aliases": [],
        },
    }


def write_config(tmp_path, value=None):
    path = tmp_path / "llm.json"
    path.write_text(json.dumps(value if value is not None else document()), encoding="utf-8")
    return path


def frame(value):
    body = json.dumps(value, separators=(",", ":")).encode()
    return struct.pack(">I", len(body)) + body


def request(model, *, streaming=False):
    return LLMRequest(
        invocation_id=composition.InvocationFactory().create(),
        model=model,
        purpose=LLMPurpose("stage4-acceptance"),
        messages=(LLMMessage(MessageRole.USER, (TextContent("controlled prompt"),)),),
        max_output_tokens=16,
        streaming=streaming,
    )


def test_versioned_config_wires_all_adapter_families_and_profiles(tmp_path):
    config = load_configuration(write_config(tmp_path))
    assert config.version == 1
    assert {provider.adapter_kind.value for provider in config.providers.values()} == set(KINDS)
    assert len(config.registry.models) == 4
    for profile in RoutingProfile:
        policy = config.routing.policy(LLMPurpose("anything"), profile)
        assert tuple(model.model_id for model in policy.candidates) == tuple(
            f"opaque-{index}" for index in range(4)
        )
    assert config.retry_policy.max_attempts == 2
    assert config.pricing_catalog_id == "controlled-offline"
    serialized = json.dumps(document(), sort_keys=True)
    assert "api_key" not in serialized and "SECRET-CANARY" not in serialized


@pytest.mark.parametrize(
    "mutate,code",
    [
        (lambda value: value["providers"].append(value["providers"][0]), "duplicate_provider_id"),
        (
            lambda value: value["providers"][0].update(adapter_kind="unknown"),
            "llm_configuration_invalid",
        ),
        (
            lambda value: value["models"][0].update(provider_id="missing"),
            "model_provider_missing",
        ),
        (lambda value: value["models"].append(value["models"][0]), "duplicate_model_ref"),
        (
            lambda value: value["models"][0]["capabilities"].update(streaming=False),
            "model_capability_mismatch",
        ),
        (
            lambda value: value["providers"][0].update(secret_ref="not-a-uuid"),
            "llm_configuration_invalid",
        ),
        (
            lambda value: value["execution_policy"].update(max_attempts=0),
            "llm_configuration_invalid",
        ),
        (
            lambda value: value["models"][0]["limits"].update(max_output_tokens=0),
            "llm_configuration_invalid",
        ),
        (
            lambda value: value["pricing_catalog"]["aliases"].append(
                {
                    "alias": value["routes"][0]["candidates"][0],
                    "target": {"provider_id": "missing", "model_id": "missing"},
                }
            ),
            "llm_configuration_invalid",
        ),
        (
            lambda value: value["providers"][0].update(api_key="SECRET-CANARY"),
            "llm_config_contains_secret_field",
        ),
    ],
)
def test_invalid_configuration_fails_safely_before_execution(tmp_path, mutate, code):
    value = document()
    mutate(value)
    with pytest.raises(LLMProductionConfigurationError) as failure:
        load_configuration(write_config(tmp_path, value))
    assert failure.value.code == code
    assert "SECRET-CANARY" not in repr(failure.value)


def test_disabled_route_candidate_is_rejected_at_load(tmp_path):
    value = document()
    value["models"][0]["enabled"] = False
    with pytest.raises(LLMProductionConfigurationError, match="route_model_unavailable"):
        load_configuration(write_config(tmp_path, value))


def test_session_credentials_are_typed_memory_only_and_restart_requires_reprovision():
    reference = SecretRef(SECRET_REFS[0])
    first = SessionCredentialProvider((reference,))
    assert first.health is LLMRuntimeHealth.UNCONFIGURED
    with pytest.raises(RuntimeError, match="credential_unavailable"):
        asyncio.run(first.resolve(reference))
    first.upsert(reference, "SECRET-CANARY")
    first.complete_sync(secure_store_available=True)
    assert first.health is LLMRuntimeHealth.READY
    assert "SECRET-CANARY" not in repr(asyncio.run(first.resolve(reference)))

    restarted = SessionCredentialProvider((reference,))
    assert restarted.health is LLMRuntimeHealth.UNCONFIGURED
    restarted.upsert(reference, "SECRET-CANARY")
    restarted.complete_sync(secure_store_available=True)
    assert restarted.health is LLMRuntimeHealth.READY
    restarted.remove(reference)
    assert restarted.health is LLMRuntimeHealth.UNCONFIGURED

    partial = SessionCredentialProvider(tuple(SecretRef(value) for value in SECRET_REFS[:2]))
    partial.upsert(SecretRef(SECRET_REFS[0]), "SECRET-CANARY")
    partial.complete_sync(secure_store_available=True)
    assert partial.health is LLMRuntimeHealth.PARTIALLY_CONFIGURED


def test_degraded_session_provider_discards_existing_and_new_secret_values():
    reference = SecretRef(SECRET_REFS[0])
    credentials = SessionCredentialProvider((reference,))
    credentials.upsert(reference, "SECRET-CANARY-ONE")
    credentials.mark_degraded()
    credentials.upsert(reference, "SECRET-CANARY-TWO")
    credentials.complete_sync(secure_store_available=True)
    assert credentials.health is LLMRuntimeHealth.DEGRADED
    with pytest.raises(RuntimeError, match="credential_unavailable"):
        asyncio.run(credentials.resolve(reference))


def test_bounded_control_protocol_and_secret_canary(tmp_path):
    reference = SecretRef(SECRET_REFS[0])
    credentials = SessionCredentialProvider((reference,))
    stream = BytesIO(
        frame(
            {
                "version": PROTOCOL_VERSION,
                "type": "credential_upsert",
                "secret_ref": str(reference.value),
                "secret": "SECRET-CANARY",
            }
        )
        + frame(
            {
                "version": PROTOCOL_VERSION,
                "type": "credential_sync_complete",
                "secure_store_available": True,
            }
        )
    )
    first = decode_frame(stream)
    assert first.secret == "SECRET-CANARY"
    apply_message(first, credentials)
    apply_message(decode_frame(stream), credentials)
    assert decode_frame(stream) is None and credentials.health is LLMRuntimeHealth.READY
    assert "SECRET-CANARY" not in repr(first)

    output = StringIO()
    listener = HostControlListener(
        BytesIO(struct.pack(">I", MAX_FRAME_BYTES + 1)), credentials, StructuredLogger(output)
    )
    listener.start()
    assert listener.join(2)
    assert credentials.health is LLMRuntimeHealth.DEGRADED
    assert "SECRET-CANARY" not in output.getvalue()
    assert set(HOST_CONTROL_CONTRACT["message_types"]) == {
        "credential_upsert",
        "credential_remove",
        "credential_sync_complete",
    }


def test_control_listener_stops_after_host_pipe_eof():
    credentials = SessionCredentialProvider()
    listener = HostControlListener(BytesIO(), credentials, StructuredLogger(StringIO()))
    listener.start()
    assert listener.join(2)


def test_control_protocol_rejects_unknown_and_oversized_without_echo():
    with pytest.raises(ControlProtocolError, match="host_control_protocol_rejected"):
        decode_frame(BytesIO(frame({"version": 1, "type": "shell", "secret": "CANARY"})))
    with pytest.raises(ControlProtocolError, match="host_control_frame_size_invalid"):
        decode_frame(BytesIO(struct.pack(">I", MAX_FRAME_BYTES + 1)))


def test_production_runtime_governs_calls_and_missing_credential_has_no_attempt_row(
    tmp_path, monkeypatch
):
    class OwnedFake(FakeModelGateway):
        def __init__(self):
            super().__init__(chunks=("ok",))
            self.closed = False

        async def aclose(self):
            self.closed = True

    owned = []

    def fake_factory(*_args):
        gateway = OwnedFake()
        owned.append(gateway)
        return gateway

    async def run():
        database = Database(tmp_path / "data")
        await database.initialize()
        config = load_configuration(write_config(tmp_path))
        credentials = SessionCredentialProvider(tuple(SecretRef(value) for value in SECRET_REFS))
        monkeypatch.setattr(composition, "_factory", fake_factory)
        runtime = await composition.build_production_llm_runtime(
            config, database, StructuredLogger(StringIO()), credentials=credentials
        )
        model = config.registry.models[0].model
        try:
            with pytest.raises(RoutingError) as failure:
                await runtime.gateway.generate(request(model))
            assert failure.value.issue is RouteIssue.CREDENTIAL_UNAVAILABLE
            async with database.engine.connect() as connection:
                assert (
                    await connection.execute(text("SELECT count(*) FROM llm_attempts"))
                ).scalar_one() == 0
            credentials.upsert(config.providers[model.provider_id].config.secret_ref, "test-key")
            result = await runtime.gateway.generate(request(model))
            assert result.text == "ok"
            credentials.remove(config.providers[model.provider_id].config.secret_ref)
            with pytest.raises(RoutingError) as deleted:
                await runtime.gateway.generate(request(model))
            assert deleted.value.issue is RouteIssue.CREDENTIAL_UNAVAILABLE
            async with database.engine.connect() as connection:
                assert (
                    await connection.execute(text("SELECT count(*) FROM llm_attempts"))
                ).scalar_one() == 1
        finally:
            await runtime.aclose()
            await database.close()
        assert len(owned) == 4 and all(gateway.closed for gateway in owned)

    asyncio.run(run())


def test_control_contract_contains_no_runtime_secret():
    assert "SECRET-CANARY" not in json.dumps(HOST_CONTROL_CONTRACT)
    assert not hasattr(composition.InvocationFactory, "secret")


def test_live_smoke_is_disabled_without_explicit_flag_even_when_env_has_secret(
    tmp_path, monkeypatch, capsys
):
    script = Path(__file__).parents[2] / "scripts" / "live-llm-smoke.py"
    spec = importlib.util.spec_from_file_location("livingworld_live_llm_smoke", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("LIVINGWORLD_LIVE_SECRET", "LIVE-SMOKE-SECRET-CANARY")
    result = module.main(
        [
            "--config",
            str(tmp_path / "missing.json"),
            "--data-dir",
            str(tmp_path / "data"),
            "--provider",
            "provider",
            "--model",
            "model",
            "--credential-env",
            "LIVINGWORLD_LIVE_SECRET",
        ]
    )
    captured = capsys.readouterr()
    assert result == 2
    assert "disabled" in captured.out
    assert "LIVE-SMOKE-SECRET-CANARY" not in captured.out + captured.err
