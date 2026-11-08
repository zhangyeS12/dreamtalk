import httpx
import pytest
from livingworld.application.chat_media import MediaError
from livingworld.infrastructure.mobile_media_search import MAX_RESPONSE, search


def test_mobile_search_uses_only_one_engine_and_preserves_filters():
    calls = []

    def handler(request):
        calls.append(request)
        assert request.url.host == "duckduckgo.com"
        if request.url.path == "/":
            return httpx.Response(200, text="vqd='safe-token'")
        assert request.url.params["p"] == "1"
        assert request.url.params["f"] == ",,,type:clipart,,license:Share"
        return httpx.Response(
            200,
            json={
                "results": [
                    {"image": "https://example.invalid/image.png", "url": "https://example.invalid"}
                ]
            },
        )

    rows = search("public synthetic query", "sticker", transport=httpx.MockTransport(handler))
    assert len(calls) == 2 and len(rows) == 1


def test_mobile_search_rejects_unbounded_response_without_fallback():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, content=b"x" * (MAX_RESPONSE + 1))

    with pytest.raises(MediaError):
        search("query", "image", transport=httpx.MockTransport(handler))
    assert len(calls) == 1
