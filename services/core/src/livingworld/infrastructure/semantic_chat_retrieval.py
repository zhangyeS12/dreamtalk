"""FastEmbed retrieval on freshly authorized candidates and local cached vectors."""

from __future__ import annotations

import asyncio
import hashlib
import sys
from collections import OrderedDict
from pathlib import Path

from livingworld.infrastructure.chat_retrieval import Fts5ChatRecallRanker
from livingworld.infrastructure.local_vector_cache import LocalVectorCache

MODEL = "BAAI/bge-small-zh-v1.5"
MODEL_SHA = "1294ea4b6331115a353d81f96b85e8c8d7fdcc284453d5b2fab5b016230aad38"
MAX_INDEX_REFERENCES = 8192
PREFIX = "为这个句子生成表示以用于检索相关文章："


def reference_key(scope, kind, identity, version=""):
    # Source IDs are immutable; a changed memory revision gets a new vector key.
    return hashlib.sha256(
        f"bge-zh-v2:{MODEL_SHA}:2000:512\0{scope}\0{kind}\0{identity}\0{version}".encode()
    ).digest()


def model_directory():
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "semantic-model"
    return Path(__file__).resolve().parents[5] / "artifacts/semantic-model"


class HybridChatRecallRanker(Fts5ChatRecallRanker):
    def __init__(self, cache_directory=None):
        super().__init__()
        self._semantic_job = None
        self._model = None
        self._unavailable = False
        self._vectors = OrderedDict()
        self._query_vectors = OrderedDict()
        self._cache = LocalVectorCache(cache_directory)

    async def _worker(self, method, *args):
        # A slow cold model/cache cannot queue every conversation behind it.
        # Keep one worker until it really finishes; cancelled/expired callers
        # never use its late result or start another concurrent model load.
        if self._semantic_job is not None and not self._semantic_job.done():
            return None
        job = asyncio.create_task(asyncio.to_thread(method, *args))
        self._semantic_job = job

        def completed(task):
            if self._semantic_job is task:
                self._semantic_job = None
            if not task.cancelled():
                task.exception()  # Consume failures even after the caller timed out.

        job.add_done_callback(completed)
        try:
            return await asyncio.wait_for(asyncio.shield(job), timeout=3.0)
        except TimeoutError:
            return None

    async def historical(self, queries, references, *, limit=24):
        """References contain IDs only, after the caller's SQL permission filtering."""
        if not references:
            return (), (), False
        result = await self._worker(self._historical, queries, references, limit)
        return result if result is not None else ((), (), True)

    async def rank_with_mode(self, queries, candidates, *, limit):
        lexical = await super().rank_queries(queries, candidates, limit=max(32, limit * 4))
        if not candidates:
            return (), "keyword"
        semantic = await self._worker(self._semantic, queries, candidates)
        if semantic is None:
            return lexical[:limit], "keyword_fallback"
        scores, items = {}, {}
        semantic, partial = semantic
        for result in (lexical, semantic):
            for rank, item in enumerate(result, 1):
                identity = id(item)
                scores[identity] = scores.get(identity, 0.0) + 1 / (60 + rank)
                items[identity] = item
        ordered = sorted(scores, key=lambda key: -scores[key])[:limit]
        mode = (
            "hybrid_memory_only"
            if self._cache.failed
            else "hybrid_partial"
            if partial
            else "hybrid"
        )
        return tuple(items[key] for key in ordered), mode

    async def rank_queries(self, queries, candidates, *, limit):
        result, _mode = await self.rank_with_mode(queries, candidates, limit=limit)
        return result

    def _load_model(self):
        if self._unavailable:
            raise ValueError("semantic_model_unavailable")
        if self._model is None:
            from fastembed import TextEmbedding

            directory = model_directory()
            if not (directory / "model_optimized.onnx").is_file():
                raise ValueError("semantic_model_missing")
            self._model = TextEmbedding(
                MODEL,
                specific_model_path=str(directory),
                local_files_only=True,
                providers=["CPUExecutionProvider"],
                threads=2,
            )
        return self._model

    def _payload(self, key):
        value = self._vectors.get(key)
        if value is None:
            value = self._cache.get(key)
        if value is not None:
            self._vectors[key] = value
            self._vectors.move_to_end(key)
            while len(self._vectors) > 4096:
                self._vectors.popitem(last=False)
        return value

    def _decode(self, payload):
        import numpy as np

        if payload is None or len(payload) != 2080:
            return None
        vector = np.frombuffer(payload[32:], dtype="<f4")
        if not np.isfinite(vector).all() or not 0.95 <= np.linalg.norm(vector) <= 1.05:
            return None
        return vector

    def _scores(self, queries, vectors):
        import numpy as np

        if not vectors:
            return {}
        matrix = np.stack(vectors)
        scores = {}
        prepared = [PREFIX + query[:2000] for query in queries[:3]]
        keys = [hashlib.sha256(query.encode()).digest() for query in prepared]
        missing = {
            key: query
            for key, query in zip(keys, prepared, strict=True)
            if key not in self._query_vectors
        }
        if missing:
            embedded = self._load_model().embed(list(missing.values()), batch_size=3)
            for key, vector in zip(missing, embedded, strict=True):
                self._query_vectors[key] = vector
        # Query vectors depend only on the supplied question, never corpus contents.
        # Keep them in memory so history lookup and final fusion reuse one encoding.
        for key in keys:
            self._query_vectors.move_to_end(key)
        while len(self._query_vectors) > 128:
            self._query_vectors.popitem(last=False)
        for query_index, key in enumerate(keys):
            vector = self._query_vectors[key]
            similarities = matrix @ vector
            for rank, index in enumerate(np.argsort(-similarities, kind="stable")[:16], 1):
                if similarities[index] < 0.8:
                    continue
                identity = int(index)
                scores[identity] = scores.get(identity, 0.0) + (2 if query_index == 0 else 1) / (
                    60 + rank
                )
        return scores

    def _historical(self, queries, references, limit):
        self._cache.open()
        try:
            identities, vectors, missing = [], [], []
            for identity, key in references[:MAX_INDEX_REFERENCES]:
                vector = self._decode(self._payload(key))
                if vector is None:
                    if len(missing) < 64:
                        missing.append(identity)
                else:
                    identities.append(identity)
                    vectors.append(vector)
            scores = self._scores(queries, vectors)
            selected = tuple(
                identities[index] for index in sorted(scores, key=lambda key: -scores[key])[:limit]
            )
            return selected, tuple(missing), len(vectors) < len(references)
        except Exception:
            # Only the explicit body-reading caller can authorize a backfill page.
            return (), tuple(identity for identity, _key in references[:64]), True
        finally:
            self._cache.close()

    def _semantic(self, queries, candidates):
        if self._unavailable:
            return None
        self._cache.open()
        try:
            import numpy as np

            keys = [
                item.index_key
                or reference_key(
                    item.scope_key, "text", hashlib.sha256(item.text[:2000].encode()).hexdigest()
                )
                for item in candidates
            ]
            payloads, missing = {}, OrderedDict()
            for key, item in zip(keys, candidates, strict=True):
                digest = hashlib.sha256(item.text[:2000].encode()).digest()
                payload = self._payload(key)
                if (
                    payload is not None
                    and payload[:32] == digest
                    and self._decode(payload) is not None
                ):
                    payloads[key] = payload
                else:
                    missing.setdefault(key, item)
            # An older-history page gets up to half the existing encoding allowance.
            priority = [key for key, item in missing.items() if item.index_priority][:64]
            chosen = dict.fromkeys([*priority, *missing])
            chosen = list(chosen)[:128]
            if chosen:
                embedded = self._load_model().embed(
                    [missing[key].text[:2000] for key in chosen], batch_size=16
                )
                for key, vector in zip(chosen, embedded, strict=True):
                    digest = hashlib.sha256(missing[key].text[:2000].encode()).digest()
                    vector = np.asarray(vector, dtype="<f4")
                    payload = digest + vector.tobytes()
                    if self._decode(payload) is None:
                        raise ValueError("semantic_vector_invalid")
                    payloads[key] = payload
                    self._vectors[key] = payload
                    self._cache.set(key, payload)
            available = [index for index, key in enumerate(keys) if key in payloads]
            vectors = [self._decode(payloads[keys[index]]) for index in available]
            while len(self._vectors) > 4096:
                self._vectors.popitem(last=False)
            scores = self._scores(queries, vectors)
            return tuple(
                candidates[available[index]]
                for index in sorted(scores, key=lambda key: -scores[key])
            ), len(available) < len(keys)
        except Exception:
            self._unavailable = True
            self._model = None
            self._vectors.clear()
            self._query_vectors.clear()
            return None
        finally:
            self._cache.close()
