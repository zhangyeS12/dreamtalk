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

    async def rank(
        self, query: str, candidates: tuple[ChatMessage, ...], *, limit: int
    ) -> tuple[ChatMessage, ...]:
        async with self._slots:
            job = asyncio.create_task(asyncio.to_thread(self._rank, query, candidates, limit))
            try:
                return await asyncio.shield(job)
            except asyncio.CancelledError:
                # Keep the slot until the bounded worker releases its private in-memory index.
                await job
                raise

    def _rank(
        self, query: str, candidates: tuple[ChatMessage, ...], limit: int
    ) -> tuple[ChatMessage, ...]:
        terms = list(dict.fromkeys(reversed(self._tokens(query))))[:_MAX_QUERY_TERMS]
        if not terms or not candidates:
            return ()
        # Each term is a literal FTS phrase; chat text never becomes MATCH syntax.
        match = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)
        # A per-query corpus avoids ranking against another owner's private history.
        # No durable index, embeddings, source-text logs or chat-content cache are created.
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
            rows = connection.execute(
                "SELECT rowid FROM recall WHERE recall MATCH ? "
                "ORDER BY bm25(recall), rowid LIMIT ?",
                (match, limit),
            ).fetchall()
        return tuple(candidates[row[0] - 1] for row in rows)
