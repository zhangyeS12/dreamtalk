"""Provider independence, offline async behavior and credential isolation invariants."""

import asyncio
import json
import socket
import urllib.request
from dataclasses import FrozenInstanceError, asdict, replace
from io import StringIO
from uuid import uuid4

import pytest
from livingworld.application.llm import (
    FinishReason,
    InvocationId,
    LLMContractError,
    LLMError,
    LLMErrorCode,
    LLMFailure,
    LLMMessage,
    LLMPurpose,
    LLMRequest,
    LLMUsage,
    MessageRole,
    ModelCapabilities,
    ModelCatalog,
    ModelGateway,
    ModelRef,
    ProviderDiagnostics,
    ProviderId,
    StreamCompleted,
    StreamFailed,
    StreamStarted,
    StructuredOutputRequest,
    TextContent,
    TextDelta,
    UsageUpdate,
    ValidatedStructuredResult,
)
from livingworld.application.llm_config import (
    CredentialProvider,
    EndpointConfig,
    ProviderConfig,
    SecretRef,
    SecretValue,
)
from livingworld.application.llm_serialization import request_from_data, request_to_data
from livingworld.domain.content.serialization import serialize_content
from livingworld.domain.identifiers import CorrelationId
from livingworld.infrastructure.llm.fake import FakeModelGateway, StaticModelCatalog
from livingworld.infrastructure.logging import StructuredLogger
from livingworld.infrastructure.persistence import Database
from package_fixtures import NOW, accept, native_package, service, zip_members

CANARY = "LW_SYNTHETIC_C005A_CREDENTIAL_CANARY_NEVER_A_REAL_API_KEY"
SCHEMA = {
    "type": "object",
    "properties": {"label": {"type": "string"}},
    "required": ["label"],
    "additionalProperties": False,
}


def request(**changes):
    values = dict(
        invocation_id=InvocationId(uuid4()),
        model=ModelRef(ProviderId("synthetic"), "opaque/model:1"),
        purpose=LLMPurpose("contract_test"),
        messages=(
            LLMMessage(MessageRole.SYSTEM, (TextContent("Synthetic context"),)),
            LLMMessage(MessageRole.DEVELOPER, (TextContent("Synthetic instruction"),)),
            LLMMessage(MessageRole.USER, (TextContent("Synthetic question"),)),
            LLMMessage(MessageRole.ASSISTANT, (TextContent("Synthetic history"),)),
        ),
        max_output_tokens=64,
        stop_sequences=("<END>",),
        correlation_id=CorrelationId(uuid4()),
        metadata={"test": {"labels": ["controlled"]}},
    )
    values.update(changes)
    return LLMRequest(**values)


def test_provider_model_purpose_and_invocation_have_separate_identities():
    first = ModelRef(ProviderId("provider-a"), "same-opaque-model")
    second = ModelRef(ProviderId("provider-b"), "same-opaque-model")
    assert first != second
    assert ProviderId("purpose") != LLMPurpose("purpose")
    with pytest.raises(LLMContractError):
        request(purpose=ProviderId("purpose"))
    with pytest.raises(LLMContractError):
        InvocationId("provider-request-id")
    assert InvocationId(uuid4()) != CorrelationId(uuid4())
    assert (
        ModelRef(ProviderId("local"), "contains-gpt-but-opaque").model_id
        == "contains-gpt-but-opaque"
    )


def test_request_round_trip_defensive_copy_and_text_privacy():
    metadata = {"tags": ["synthetic"]}
    source_schema = json.loads(json.dumps(SCHEMA))
    original = request(
        metadata=metadata, structured_output=StructuredOutputRequest("controlled", source_schema)
    )
    metadata["tags"].append("changed")
    source_schema["properties"]["label"]["type"] = "number"
    assert original.metadata["tags"] == ("synthetic",)
    assert original.structured_output.schema["properties"]["label"]["type"] == "string"
    data = request_to_data(original)
    assert request_from_data(json.loads(json.dumps(data))) == original
    data["messages"][0]["content"][0]["text"] = "changed"
    assert original.messages[0].content[0].text == "Synthetic context"
    assert "Synthetic context" not in repr(original)
    with pytest.raises(FrozenInstanceError):
        original.max_output_tokens = 1
    with pytest.raises(TypeError):
        original.metadata["secret"] = "bad"


@pytest.mark.parametrize(
    "changes",
    [
        {"messages": ()},
        {"messages": ({"role": "user", "content": "text"},)},
        {"max_output_tokens": True},
        {"max_output_tokens": 0},
        {"streaming": 1},
        {"structured_output": SCHEMA},
        {"stop_sequences": ("",)},
        {"metadata": {"sdk": object()}},
    ],
)
def test_request_rejects_untyped_or_ambiguous_inputs(changes):
    with pytest.raises(LLMContractError):
        request(**changes)


@pytest.mark.parametrize(
    "role,content",
    [
        ("user", (TextContent("text"),)),
        (MessageRole.USER, ("untyped",)),
        (MessageRole.USER, ()),
        (MessageRole.USER, ({"kind": "image"},)),
    ],
)
def test_message_has_livingworld_role_and_typed_text_blocks(role, content):
    with pytest.raises(LLMContractError):
        LLMMessage(role, content)


def test_round_trip_codec_is_closed_and_does_not_coerce_future_content():
    data = request_to_data(request())
    data["messages"][0]["content"][0] = {"kind": "image", "text": "not text"}
    with pytest.raises(LLMContractError):
        request_from_data(data)
    data = request_to_data(request())
    data["provider_config"] = {"credential": CANARY}
    with pytest.raises(LLMContractError) as error:
        request_from_data(data)
    assert CANARY not in repr(error.value)


def test_raw_json_looking_response_is_not_a_validated_structured_result():
    async def run():
        original = request(structured_output=StructuredOutputRequest("controlled", SCHEMA))
        gateway: ModelGateway = FakeModelGateway(chunks=('{"label":"synthetic"}',))
        response = await gateway.generate(original)
        assert response.text == '{"label":"synthetic"}'
        assert response.structured_result is None
        validated = ValidatedStructuredResult("controlled", {"label": "synthetic"})
        result = replace(response, structured_result=validated)
        assert result.text == response.text
        assert result.structured_result.value["label"] == "synthetic"
        with pytest.raises(LLMContractError):
            replace(response, structured_result=json.loads(response.text))
        # A manual trusted-claim fixture tests representation, not schema validation.
        with pytest.raises(LLMContractError):
            replace(result, finish_reason=FinishReason.REFUSAL)

    asyncio.run(run())


def test_usage_preserves_reported_facts_and_unknown_categories():
    usage = LLMUsage(10, 3, 13, details={"provider_cache": {"tokens": 4}})
    assert (usage.input_tokens, usage.output_tokens, usage.total_tokens) == (10, 3, 13)
    assert LLMUsage().total_tokens is None
    assert LLMUsage(input_tokens=10, output_tokens=3).total_tokens is None
    with pytest.raises(LLMContractError):
        LLMUsage(input_tokens=-1)
    with pytest.raises(LLMContractError):
        LLMUsage(total_tokens=True)
    assert not {"cost", "price", "currency"} & set(LLMUsage.__dataclass_fields__)


@pytest.mark.parametrize("code", list(LLMErrorCode))
def test_fake_normalizes_failures_without_provider_types(code):
    async def run():
        original = request()
        with pytest.raises(LLMError) as error:
            await FakeModelGateway(error=code).generate(original)
        assert error.value.failure.code is code
        assert error.value.failure.invocation_id == original.invocation_id
        assert error.value.args == (code.value,)

    asyncio.run(run())


def test_refusal_is_a_successful_round_trip_and_failed_stream_is_distinct():
    async def run():
        original = request()
        refused = await FakeModelGateway(finish_reason=FinishReason.REFUSAL).generate(original)
        assert refused.finish_reason is FinishReason.REFUSAL
        assert refused.invocation_id == original.invocation_id
        streamed = replace(original, streaming=True)
        refusal = [
            event
            async for event in FakeModelGateway(finish_reason=FinishReason.REFUSAL).stream(streamed)
        ]
        assert isinstance(refusal[-1], StreamCompleted)
        assert refusal[-1].response.finish_reason is FinishReason.REFUSAL
        failed = [
            event async for event in FakeModelGateway(error=LLMErrorCode.TIMEOUT).stream(streamed)
        ]
        assert [type(event) for event in failed] == [StreamStarted, StreamFailed]
        assert failed[-1].failure.code is LLMErrorCode.TIMEOUT

    asyncio.run(run())


def test_catalog_uses_explicit_full_model_identity_and_owns_its_snapshot():
    unusual = ModelRef(ProviderId("synthetic"), "unknown-no-vendor-prefix")
    misleading = ModelRef(ProviderId("synthetic"), "gpt-vision-tools-reasoning")
    entries = {unusual: ModelCapabilities(text_generation=True, streaming=True)}
    catalog: ModelCatalog = StaticModelCatalog(entries)
    entries[unusual] = ModelCapabilities(vision=True)
    assert catalog.capabilities(unusual).streaming
    assert not catalog.capabilities(unusual).vision
    assert catalog.capabilities(misleading) is None
    assert catalog.capabilities(ModelRef(ProviderId("other"), unusual.model_id)) is None
    with pytest.raises(LLMContractError):
        ModelCapabilities(vision=1)


def test_fake_generate_and_stream_are_deterministic_and_never_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("LLM contract fake attempted network access")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)

    async def run():
        original = request()
        gateway: ModelGateway = FakeModelGateway(
            chunks=("first", " second"), usage=LLMUsage(2, 2, 4)
        )
        response = await gateway.generate(original)
        assert await gateway.generate(original) == response
        assert response.invocation_id == original.invocation_id
        assert response.model_used == original.model and response.text == "first second"
        streamed = replace(original, streaming=True)
        events = [event async for event in gateway.stream(streamed)]
        assert [event async for event in gateway.stream(streamed)] == events
        assert [type(event) for event in events] == [
            StreamStarted,
            TextDelta,
            TextDelta,
            UsageUpdate,
            StreamCompleted,
        ]
        assert all(event.invocation_id == original.invocation_id for event in events[:-1])
        assert events[-1].response == response
        assert (
            "".join(event.text for event in events if isinstance(event, TextDelta)) == response.text
        )
        with pytest.raises(LLMError, match="invalid_request"):
            await gateway.generate(streamed)
        with pytest.raises(LLMError, match="invalid_request"):
            await anext(gateway.stream(original))

    asyncio.run(run())


def test_async_cancellation_and_stream_close_use_standard_asyncio():
    async def run():
        gateway = FakeModelGateway(chunks=("one", "two"))
        original = request()
        task = asyncio.create_task(gateway.generate(original))
        await asyncio.sleep(0)  # Fake is now suspended at its cooperative cancellation point.
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        iterator = gateway.stream(replace(original, streaming=True))
        assert isinstance(await anext(iterator), StreamStarted)
        task = asyncio.create_task(anext(iterator))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await iterator.aclose()
        with pytest.raises(StopAsyncIteration):
            await anext(iterator)

    asyncio.run(run())


@pytest.mark.parametrize(
    "url",
    [
        "https://user:password@example.invalid/v1",
        "https://example.invalid/v1?key=" + CANARY,
        "https://example.invalid/#" + CANARY,
        "https://example.invalid:wrong/",
        "https://example.invalid\\private",
        "https://example.invalid/\n",
        "file:///private/key",
    ],
)
def test_endpoint_rejects_embedded_authentication_and_malformed_transport(url):
    with pytest.raises(LLMContractError) as error:
        EndpointConfig(url)
    assert CANARY not in str(error.value) and CANARY not in repr(error.value)


def test_secret_boundary_rejects_credential_objects_and_redacts_errors_and_logs():
    reference = SecretRef(uuid4())
    secret = SecretValue(CANARY)
    config = ProviderConfig(
        provider_id=ProviderId("synthetic"),
        secret_ref=reference,
        endpoint=EndpointConfig("https://example.invalid/v1"),
    )
    assert CANARY not in repr(secret) and CANARY not in str(secret)
    assert CANARY not in repr(config) and CANARY not in repr(asdict(config))
    assert secret.reveal_for_adapter() == CANARY
    with pytest.raises(LLMContractError):
        TextContent(secret)
    with pytest.raises(LLMContractError):
        LLMUsage(details={"credential": secret})
    with pytest.raises(LLMContractError):
        StructuredOutputRequest("controlled", {"credential": secret})
    assert CANARY not in repr(TextContent(CANARY))
    assert CANARY not in repr(TextDelta(InvocationId(uuid4()), CANARY))
    with pytest.raises(TypeError):
        json.dumps(secret)
    with pytest.raises(TypeError):
        asdict(secret)
    for credential in (secret, reference, config, {"nested": [secret]}):
        with pytest.raises(LLMContractError) as error:
            request(metadata={"credential": credential})
        assert CANARY not in repr(error.value)
    with pytest.raises(LLMContractError):
        ProviderConfig(provider_id=ProviderId("synthetic"), secret_ref=secret)
    with pytest.raises(LLMContractError):
        SecretRef(CANARY)
    diagnostics = ProviderDiagnostics(provider_request_id=CANARY, diagnostic_code=CANARY)
    failure = LLMFailure(LLMErrorCode.AUTHENTICATION, InvocationId(uuid4()), diagnostics)
    assert CANARY not in repr(failure) and CANARY not in repr(LLMError(failure))
    logs = StringIO()
    StructuredLogger(stream=logs).emit(
        "llm", "synthetic_failure", level="ERROR", trace_id=str(failure.invocation_id.value)
    )
    assert CANARY not in logs.getvalue()
    assert "secret_ref" not in request_to_data(request())


def test_config_and_credential_provider_are_separate_from_requests():
    async def run():
        reference = SecretRef(uuid4())

        class Credentials:
            async def resolve(self, supplied: SecretRef) -> SecretValue:
                assert supplied == reference
                return SecretValue(CANARY)

        credentials: CredentialProvider = Credentials()
        assert CANARY not in repr(await credentials.resolve(reference))
        config = ProviderConfig(
            provider_id=ProviderId("local"),
            endpoint=EndpointConfig("http://127.0.0.1:9000"),
            default_model=ModelRef(ProviderId("local"), "opaque"),
        )
        assert config.secret_ref is None
        with pytest.raises(LLMContractError):
            replace(config, default_model=ModelRef(ProviderId("other"), "opaque"))
        with pytest.raises(LLMContractError):
            replace(config, timeout_ms=0)
        with pytest.raises(LLMContractError):
            replace(config, verify_tls=False)

    asyncio.run(run())


def test_provider_config_does_not_enter_canonical_content_or_native_package(tmp_path):
    async def run():
        database = Database(tmp_path)
        package = native_package()
        original_hash = package.semantic_hash
        config = ProviderConfig(provider_id=ProviderId("synthetic"), secret_ref=SecretRef(uuid4()))
        secret = SecretValue(CANARY)
        try:
            await database.initialize()
            await accept(database, package)
            result = await service(database).export(
                package.root_ids, package_id=package.package_id, created_at_utc=NOW
            )
            for payload in (result.package_bytes, *zip_members(result.package_bytes).values()):
                assert CANARY.encode() not in payload
                assert config.secret_ref.value.hex.encode() not in payload
            for root in result.package.content.contents:
                assert "provider_config" not in serialize_content(root)
            assert result.semantic_hash == original_hash
            assert secret.reveal_for_adapter() == CANARY  # Present locally throughout export.
        finally:
            await database.close()

    asyncio.run(run())
