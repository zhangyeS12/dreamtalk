"""Android transport for the existing single DuckDuckGo image-search route.

Protocol reference: deedy5/ddgs DuckduckgoImages (MIT), inspected 2026-11-07.
Independent HTTPX implementation; no additional native search runtime is bundled.
"""

import json
import re

import httpx

from livingworld.application.chat_media import MediaError

MAX_RESPONSE = 512 * 1024


def search(query, kind, *, transport=None):
    def bounded(client, url, params):
        with client.stream("GET", url, params=params) as response:
            response.raise_for_status()
            data = bytearray()
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if len(data) > MAX_RESPONSE:
                    raise MediaError("media_search_response_invalid")
            return bytes(data)

    with httpx.Client(
        timeout=6,
        follow_redirects=False,
        trust_env=False,
        transport=transport,
        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://duckduckgo.com/"},
    ) as client:
        html = bounded(client, "https://duckduckgo.com/", {"q": query})
        token = re.search(rb"vqd=['\"]([a-zA-Z0-9_-]{1,128})['\"]", html)
        if not token:
            raise MediaError("media_search_unavailable")
        filters = ["", "", "", "type:clipart" if kind == "sticker" else "", "", "license:Share"]
        raw = bounded(
            client,
            "https://duckduckgo.com/i.js",
            {
                "o": "json",
                "q": query,
                "l": "cn-zh",
                "vqd": token.group(1).decode(),
                "p": "1",
                "ct": "AT",
                "f": ",".join(filters),
            },
        )
        try:
            rows = json.loads(raw)["results"]
            if not isinstance(rows, list):
                raise ValueError()
            return [
                row
                for row in rows[:5]
                if isinstance(row, dict) and isinstance(row.get("image"), str)
            ]
        except (ValueError, KeyError, TypeError):
            raise MediaError("media_search_response_invalid") from None
