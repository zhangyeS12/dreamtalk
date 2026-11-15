"""Android CPU embedding adapter; retrieval policies remain in the shared ranker."""

from __future__ import annotations

import json
import os

MAX_NATIVE_BATCH = 4


class MobileEmbeddingModel:
    def __init__(self, host):
        self._host = host

    def embed(self, documents, batch_size=16):
        import numpy as np

        if type(batch_size) is not int or not 1 <= batch_size <= 16:
            raise ValueError("mobile_recall_batch_invalid")
        values = list(documents)
        if any(not isinstance(text, str) or len(text) > 4096 for text in values):
            raise ValueError("mobile_recall_input_invalid")
        native_batch = min(batch_size, MAX_NATIVE_BATCH)
        for offset in range(0, len(values), native_batch):
            batch = values[offset : offset + native_batch]
            raw = str(self._host.recallEmbed(json.dumps(batch, ensure_ascii=False)))
            vectors = np.asarray(json.loads(raw), dtype=np.float32)
            if vectors.shape != (len(batch), 512) or not np.all(np.isfinite(vectors)):
                raise ValueError("mobile_recall_output_invalid")
            # Exactly FastEmbed's CLS L2 normalization, including its epsilon.
            norm = np.linalg.norm(vectors, ord=2, axis=1, keepdims=True)
            vectors = vectors / np.maximum(norm, 1e-12)
            yield from vectors


def install(host):
    from livingworld.infrastructure.semantic_chat_retrieval import configure_mobile_recall

    if host is not None and hasattr(host, "recallEmbed"):
        # Scoring and normalization must not recruit every phone CPU core.
        os.environ["OPENBLAS_NUM_THREADS"] = "1"
        os.environ["OMP_NUM_THREADS"] = "1"
        configure_mobile_recall(lambda: MobileEmbeddingModel(host))
