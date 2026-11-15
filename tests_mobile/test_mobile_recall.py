"""Synthetic vectors only: no fixed model inference, provider or real storage."""

import json

import numpy as np
import pytest
from livingworld.infrastructure import semantic_chat_retrieval as recall
from livingworld.infrastructure.mobile_recall import MobileEmbeddingModel, install


class Host:
    def __init__(self):
        self.calls = []

    def recallEmbed(self, payload):
        texts = json.loads(payload)
        self.calls.append(texts)
        return json.dumps([[3.0, 4.0] + [0.0] * 510 for _ in texts])


@pytest.fixture(autouse=True)
def restore_backend(monkeypatch):
    monkeypatch.setattr(recall, "_mobile_model_factory", None)
    monkeypatch.setattr(recall, "_native_ready", None)


def test_registered_before_native_prepare_does_not_require_fastembed(monkeypatch):
    import builtins

    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name == "fastembed":
            raise AssertionError("Android must not import unavailable desktop backend")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    host = Host()
    install(host)
    assert recall.prepare_native_recall()
    model = recall.HybridChatRecallRanker()._load_model()
    assert isinstance(model, MobileEmbeddingModel)
    vectors = list(model.embed(["synthetic"]))
    np.testing.assert_array_equal(vectors[0][:2], np.array([0.6, 0.8], dtype=np.float32))


def test_batch_bound_and_float32_normalization_match_fastembed():
    host = Host()
    actual = np.asarray(list(MobileEmbeddingModel(host).embed(["x"] * 19, batch_size=16)))
    source = np.array([[3, 4] + [0] * 510] * 19, dtype=np.float32)
    expected = source / np.maximum(np.linalg.norm(source, ord=2, axis=1, keepdims=True), 1e-12)
    np.testing.assert_array_equal(actual, expected)
    assert actual.dtype == np.float32
    assert [len(call) for call in host.calls] == [4, 4, 4, 4, 3]


@pytest.mark.parametrize("payload", ["[]", "[[1,2]]", "[[NaN]]", "{}", "null"])
def test_invalid_native_vectors_fail_closed(payload):
    host = Host()
    host.recallEmbed = lambda _: payload
    with pytest.raises((ValueError, TypeError)):
        list(MobileEmbeddingModel(host).embed(["synthetic"]))


@pytest.mark.parametrize("size", [0, 17, True])
def test_rejects_invalid_batch_before_native_call(size):
    host = Host()
    with pytest.raises(ValueError):
        list(MobileEmbeddingModel(host).embed(["synthetic"], batch_size=size))
    assert host.calls == []


def test_shared_cache_payload_and_ranking_use_normalized_mobile_vectors():
    host = Host()
    install(host)
    ranker = recall.HybridChatRecallRanker()
    vector = list(ranker._load_model().embed(["synthetic"]))[0]
    digest = bytes(32)
    payload = digest + vector.astype("<f4").tobytes()
    decoded = ranker._decode(payload)
    assert decoded is not None
    np.testing.assert_array_equal(decoded, vector)
    assert recall.VECTOR_MODEL_VERSION == recall.MODEL_SHA + ":2000:512"
    assert ranker._decode(digest + np.zeros(512, dtype="<f4").tobytes()) is None


def test_missing_native_bridge_keeps_desktop_or_keyword_path():
    install(object())
    assert recall._mobile_model_factory is None


def test_synonym_recall_uses_mobile_vectors_and_reuses_authorized_cache(tmp_path):
    import asyncio

    from livingworld.infrastructure.persistence.long_chat_memory import RecallCandidate

    class SemanticHost(Host):
        def recallEmbed(self, payload):
            texts = json.loads(payload)
            self.calls.append(texts)
            return json.dumps(
                [
                    ([1.0, 0.0] if text.startswith(recall.PREFIX) or "沙滩" in text else [0.0, 1.0])
                    + [0.0] * 510
                    for text in texts
                ]
            )

    host = SemanticHost()
    install(host)
    ranker = recall.HybridChatRecallRanker(tmp_path / "synthetic-vectors")
    beach = RecallCandidate("下周末去沙滩听浪", object(), "allowed", b"beach")
    other = RecallCandidate("停车场今天修好了", object(), "allowed", b"other")

    async def check():
        selected, mode, payloads = await ranker.rank_with_index(
            ("那个约定",), (beach, other), limit=1
        )
        assert selected == (beach,)
        assert mode == "hybrid"
        assert {key for key, _ in payloads} == {b"beach", b"other"}
        calls = len(host.calls)
        selected, mode, _ = await ranker.rank_with_index(("那个约定",), (other,), limit=1)
        assert not selected
        assert mode == "hybrid"
        assert len(host.calls) == calls

    asyncio.run(check())


def test_core_startup_registers_native_backend_before_prepare(tmp_path):
    import importlib

    from livingworld.bootstrap import mobile_host

    class SecureNativeHost(Host):
        def dataDirectory(self):
            return str(tmp_path / "synthetic-mobile")

        def isForeground(self):
            return True

        def secureRead(self):
            return "{}"

        def secureWrite(self, _value):
            raise AssertionError("This test must not configure an API")

    host = SecureNativeHost()
    runtime = importlib.reload(mobile_host)
    try:
        connection = json.loads(runtime.dispatch("connection", "{}", host))
        assert connection["result"]["endpoint"].startswith("http://127.0.0.1:")
        assert recall._native_ready is True
        assert isinstance(recall.HybridChatRecallRanker()._load_model(), MobileEmbeddingModel)
        assert host.calls == []  # Startup imports runtimes without model inference.
    finally:
        if runtime._thread and runtime._thread.is_alive():
            runtime._stop_if_idle()
            runtime._thread.join(timeout=5)
