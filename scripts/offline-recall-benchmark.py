"""Explicitly authorized fixed-BGE benchmark on synthetic text only."""

from __future__ import annotations

import asyncio
import json
import os
import socket
import tempfile
import time
from pathlib import Path

TEXTS = (
    "我们约好周六傍晚在海边见面。",
    "昨天在书店借给你一本蓝色封面的诗集。",
    "今天的早餐是豆浆和包子。",
)
QUERY = "我们约好周六傍晚在海边见面？"


def run(host=None, model_path=None, cache_root=None):
    def blocked(*args, **kwargs):
        raise AssertionError("fixed_recall_check_network_forbidden")

    import ipaddress

    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_getaddrinfo = socket.getaddrinfo

    def local(host):
        if host in ("localhost", b"localhost"):
            return True
        try:
            return ipaddress.ip_address(
                host.decode() if isinstance(host, bytes) else host
            ).is_loopback
        except ValueError:
            return False

    def connect(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6) and not local(address[0]):
            return blocked()
        return original_connect(sock, address)

    def connect_ex(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6) and not local(address[0]):
            return blocked()
        return original_connect_ex(sock, address)

    def getaddrinfo(host, *args, **kwargs):
        if host is not None and not local(host):
            return blocked()
        return original_getaddrinfo(host, *args, **kwargs)

    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex
    socket.getaddrinfo = getaddrinfo
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    from livingworld.infrastructure import semantic_chat_retrieval as recall
    from livingworld.infrastructure.mobile_recall import MobileEmbeddingModel, install
    from livingworld.infrastructure.persistence.long_chat_memory import RecallCandidate

    if host is None:
        recall.configure_mobile_recall(None)
    else:
        install(host)
    assert recall.prepare_native_recall(), "fixed_recall_native_unavailable"
    import numpy as np

    started = time.perf_counter()
    if host is None:
        from fastembed import TextEmbedding

        model = TextEmbedding(
            recall.MODEL,
            specific_model_path=str(model_path),
            local_files_only=True,
            providers=["CPUExecutionProvider"],
            threads=2,
        )
    else:
        model = MobileEmbeddingModel(host)
    inputs = [recall.PREFIX + QUERY, *TEXTS]
    vectors = np.asarray(list(model.embed(inputs, batch_size=16)), dtype=np.float32)
    cold_ms = (time.perf_counter() - started) * 1000
    warm_ms = []
    for _ in range(3):
        started = time.perf_counter()
        warm = np.asarray(list(model.embed(inputs, batch_size=16)), dtype=np.float32)
        warm_ms.append((time.perf_counter() - started) * 1000)
        np.testing.assert_allclose(warm, vectors, atol=1e-6, rtol=1e-6)

    with tempfile.TemporaryDirectory(prefix="fixed-recall-check-", dir=cache_root) as directory:
        ranker = recall.HybridChatRecallRanker(Path(directory))
        ranker._model = model
        candidates = tuple(
            RecallCandidate(text, i, "synthetic", ("synthetic-" + str(i)).encode())
            for i, text in enumerate(TEXTS)
        )

        async def check():
            start = time.perf_counter()
            selected, mode, _ = await ranker.rank_with_index((QUERY,), candidates, limit=3)
            first_ms = (time.perf_counter() - start) * 1000
            first = {
                "selected": [item.row for item in selected],
                "mode": mode,
                "ms": round(first_ms, 2),
            }
            job = ranker._semantic_job
            if job is not None:
                await asyncio.wait_for(asyncio.shield(job), timeout=30)
            start = time.perf_counter()
            selected, mode, _ = await ranker.rank_with_index((QUERY,), candidates, limit=3)
            return first, {
                "selected": [item.row for item in selected],
                "mode": mode,
                "ms": round((time.perf_counter() - start) * 1000, 2),
            }

        first, cached = asyncio.run(check())
    return json.dumps(
        {
            "model_sha256": recall.MODEL_SHA,
            "numpy_version": np.__version__,
            "synthetic_documents": len(TEXTS),
            "queries": 1,
            "network_allowed": False,
            "mobile_native_batch_limit": 4 if host is not None else None,
            "cold_embedding_ms": round(cold_ms, 2),
            "warm_embedding_ms": [round(v, 2) for v in warm_ms],
            "first_recall": first,
            "cached_recall": cached,
            "similarities": (vectors[1:] @ vectors[0]).tolist(),
            "semantic_eligible_indices": np.flatnonzero(vectors[1:] @ vectors[0] >= 0.8).tolist(),
            "vectors": vectors.tolist(),
        },
        ensure_ascii=False,
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-fixed-model-inference", action="store_true")
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.allow_fixed_model_inference:
        parser.error("This check requires current explicit fixed-model authorization.")
    args.output.write_text(run(model_path=args.model_path), encoding="utf-8")
