"""Bounded DDGS retrieval; search snippets are evidence, never executable commands."""

import asyncio
import logging
from datetime import UTC, datetime
from ipaddress import ip_address
from urllib.parse import urlsplit

from livingworld.application.content_builder import BuilderError, Evidence


class DDGSContentResearch:
    async def research(self, query: str, kind: str) -> tuple[Evidence, ...]:
        try:
            return await asyncio.to_thread(self._search, query, kind)
        except Exception:
            raise BuilderError("builder_search_failed") from None

    @staticmethod
    def _search(query, kind):
        from ddgs import DDGS

        # Library INFO diagnostics may include search text; keep them out of Core logs.
        logging.getLogger("ddgs").setLevel(logging.CRITICAL)
        suffix = " 人物 背景 性格" if kind == "character" else " 世界观 地点 势力"
        query = query.replace("生成一个", "").replace("角色卡", "").replace("世界书", "")
        rows = DDGS(timeout=8).text(
            query.strip() + suffix,
            max_results=8,
            backend="bing,brave,duckduckgo",
            safesearch="moderate",
        )
        results, seen = [], set()
        for row in rows[:16]:
            url = str(row.get("href", ""))[:2048]
            try:
                parsed = urlsplit(url)
                if (
                    parsed.scheme not in ("https", "http")
                    or not parsed.hostname
                    or (parsed.username or parsed.password or parsed.port not in (None, 80, 443))
                ):
                    continue
                host = parsed.hostname.casefold().rstrip(".")
                if (
                    host in ("localhost", "localhost.localdomain")
                    or "." not in host
                    or host.endswith((".local", ".localhost", ".internal"))
                ):
                    continue
                try:
                    if not ip_address(host).is_global:
                        continue
                except ValueError:
                    pass
            except ValueError:
                continue
            if url in seen:
                continue
            title, body = str(row.get("title", ""))[:300], str(row.get("body", ""))[:1000]
            if not title.strip() or not body.strip():
                continue
            seen.add(url)
            results.append(
                Evidence(
                    id=f"S{len(results) + 1}",
                    title=title,
                    url=url,
                    excerpt=body,
                    retrieved_at=datetime.now(UTC).isoformat(),
                )
            )
            if len(results) == 8:
                break
        return tuple(results)
