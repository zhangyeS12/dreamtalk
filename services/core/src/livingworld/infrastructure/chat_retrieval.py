"""Reuse jieba search segmentation and SQLite FTS5 BM25 on authorized candidates."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from contextlib import closing
from pathlib import Path

import jieba

from livingworld.application.chat_messages import ChatMessage

_MAX_QUERY_TERMS = 24
_STOP_TERMS = frozenset(
    "我 你 他 她 它 我们 你们 他们 她们 是 的 了 呢 吗 啊 和 与 或 在 这 那 什么 怎么 "
    "还 也 都 就 又 很 有 没 不 想 说 问 能 会 好 的话 记得 记住 之前 以前 现在 "
    "a an the i you he she it we they is are was were do does did of to and or".split()
)


class Fts5ChatRecallRanker:
    def __init__(self) -> None:
        jieba.setLogLevel(logging.WARNING)
        self._tokenizer = jieba.Tokenizer(
            dictionary=str(Path(jieba.__file__).with_name("dict.txt"))
        )
        self._slots = asyncio.Semaphore(2)

    def _tokens(self, text: str) -> list[str]:
        return [
            token.casefold()
            for token in self._tokenizer.cut_for_search(text, HMM=True)
            if token.isalnum() and token.casefold() not in _STOP_TERMS
        ]

    async def query_terms(self, query: str) -> tuple[str, ...]:
        async with self._slots:
            job = asyncio.create_task(asyncio.to_thread(self._tokens, query[:2000]))
            try:
                tokens = await asyncio.shield(job)
            except asyncio.CancelledError:
                await job
                raise
        return tuple(term for term in dict.fromkeys(reversed(tokens)) if len(term) <= 64)[:24]

    async def tokenize_documents(self, texts):
        """Segment one bounded authorized page for the persistent local index."""
        async with self._slots:
            job = asyncio.create_task(
                asyncio.to_thread(lambda: tuple(" ".join(self._tokens(text)) for text in texts))
            )
            try:
                return await asyncio.shield(job)
            except asyncio.CancelledError:
                await job
                raise

    async def rank(
        self, query: str, candidates: tuple[ChatMessage, ...], *, limit: int
    ) -> tuple[ChatMessage, ...]:
        return await self.rank_queries((query,), candidates, limit=limit)

    async def rank_queries(self, queries, candidates, *, limit):
        """One private FTS corpus; bounded multi-query reciprocal-rank fusion."""
        async with self._slots:
            job = asyncio.create_task(
                asyncio.to_thread(self._rank_queries, tuple(queries[:3]), candidates, limit)
            )
            try:
                return await asyncio.shield(job)
            except asyncio.CancelledError:
                # Keep the slot until the bounded worker releases its private index.
                await job
                raise

    def _rank(self, query, candidates, limit):
        # Preserve the existing internal single-query entry point.
        return self._rank_queries((query,), candidates, limit)

    def _rank_queries(self, queries, candidates, limit):
        if not candidates or limit < 1:
            return ()
        matches = []
        for query in queries[:3]:
            terms = list(dict.fromkeys(reversed(self._tokens(query[:2000]))))[:_MAX_QUERY_TERMS]
            # A literal phrase never permits chat text to become MATCH syntax.
            match = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)
            matches.append(match)
        if not any(matches):
            return ()
        # Permission filtering precedes this corpus. Nothing is persisted or logged.
        with closing(sqlite3.connect(":memory:")) as connection:
            connection.execute(
                "CREATE VIRTUAL TABLE recall USING fts5(tokens, tokenize='unicode61')"
            )
            connection.executemany(
                "INSERT INTO recall(rowid, tokens) VALUES (?, ?)",
                (
                    (index, " ".join(self._tokens(item.text)))
                    for index, item in enumerate(candidates, start=1)
                ),
            )
            scores = {}
            for query_index, match in enumerate(matches):
                if not match:
                    continue
                rows = connection.execute(
                    "SELECT rowid FROM recall WHERE recall MATCH ? "
                    "ORDER BY bm25(recall), rowid LIMIT ?",
                    (match, min(len(candidates), max(limit * 4, 32))),
                ).fetchall()
                # The current question has twice the weight of each prior utterance.
                weight = 2 if query_index == 0 else 1
                for rank, row in enumerate(rows, start=1):
                    scores[row[0]] = scores.get(row[0], 0.0) + weight / (60 + rank)
        ordered = sorted(scores, key=lambda identity: (-scores[identity], identity))[:limit]
        return tuple(candidates[identity - 1] for identity in ordered)
