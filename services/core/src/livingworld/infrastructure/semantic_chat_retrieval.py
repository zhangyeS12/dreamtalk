"""FastEmbed CPU retrieval, after SQL authorization; no network at runtime."""

from __future__ import annotations

import asyncio
import hashlib
import sys
from collections import OrderedDict
from pathlib import Path

from anyio import CancelScope

from livingworld.infrastructure.chat_retrieval import Fts5ChatRecallRanker

MODEL = "BAAI/bge-small-zh-v1.5"


def model_directory():
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "semantic-model"
    return Path(__file__).resolve().parents[5] / "artifacts/semantic-model"


class HybridChatRecallRanker(Fts5ChatRecallRanker):
    def __init__(self):
        super().__init__()
        self._semantic_slot = asyncio.Semaphore(1)
        self._model = None
        self._unavailable = False
        # No text in this cache; candidates/membership are freshly authorized.
        self._vectors = OrderedDict()

    async def rank_with_mode(self, queries, candidates, *, limit):
        lexical = await super().rank_queries(queries, candidates, limit=max(32, limit * 4))
        if not candidates:
            return (), "keyword"
        async with self._semantic_slot:
            job = asyncio.create_task(asyncio.to_thread(self._semantic, queries, candidates))
            try:
                semantic = await asyncio.shield(job)
            except asyncio.CancelledError:
                # AnyIO HTTP cancellation is level-triggered: retain the slot
                # until the CPU worker stops touching the shared vector cache.
                with CancelScope(shield=True):
                    await job
                raise
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
        return tuple(items[key] for key in ordered), "hybrid_partial" if partial else "hybrid"

    async def rank_queries(self, queries, candidates, *, limit):
        result, _mode = await self.rank_with_mode(queries, candidates, limit=limit)
        return result

    def _semantic(self, queries, candidates):
        if self._unavailable:
            return None
        try:
            import numpy as np
            from fastembed import TextEmbedding

            directory = model_directory()
            if self._model is None:
                if not (directory / "model_optimized.onnx").is_file():
                    self._unavailable = True
                    return None
                self._model = TextEmbedding(
                    MODEL,
                    specific_model_path=str(directory),
                    local_files_only=True,
                    providers=["CPUExecutionProvider"],
                    threads=2,
                )
            keys = [
                hashlib.sha256((item.scope_key + "\0" + item.text[:2000]).encode()).digest()
                for item in candidates
            ]
            missing = {
                key: item.text[:2000]
                for key, item in zip(keys, candidates, strict=True)
                if key not in self._vectors
            }
            # Bound cold-start CPU work. Subsequent explicit chat/search requests
            # progressively encode remaining authorized candidates, without a worker/export.
            missing = dict(list(missing.items())[:128])
            if missing:
                for key, vector in zip(
                    missing, self._model.embed(list(missing.values()), batch_size=16), strict=True
                ):
                    self._vectors[key] = vector
            available = [index for index, key in enumerate(keys) if key in self._vectors]
            matrix = np.stack([self._vectors[keys[index]] for index in available])
            for index in available:
                self._vectors.move_to_end(keys[index])
            while len(self._vectors) > 4096:
                self._vectors.popitem(last=False)
            scores = {}
            prefix = "为这个句子生成表示以用于检索相关文章："
            vectors = self._model.embed(
                [prefix + query[:2000] for query in queries[:3]], batch_size=3
            )
            for query_index, vector in enumerate(vectors):
                similarities = matrix @ vector
                for rank, index in enumerate(np.argsort(-similarities, kind="stable")[:16], 1):
                    # Heuristic relevance floor, never a truth/confidence guarantee.
                    if similarities[index] < 0.8:
                        continue
                    identity = available[int(index)]
                    scores[identity] = scores.get(identity, 0.0) + (
                        2 if query_index == 0 else 1
                    ) / (60 + rank)
            return tuple(
                candidates[index] for index in sorted(scores, key=lambda key: -scores[key])
            ), len(available) < len(keys)
        except Exception:
            # A damaged/unsupported local model cannot disable normal chat.
            self._unavailable = True
            self._model = None
            self._vectors.clear()
            return None
