"""Optional media and its diagnostics must not abort an otherwise valid text reply."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from livingworld.application.chat_media import ChatMediaService, MediaError, MediaSettings


class UnavailableDiagnostics:
    def emit(self, *args, **kwargs):
        raise OSError("synthetic full diagnostic disk")


def test_unavailable_library_and_diagnostics_fail_closed_without_raising():
    store = SimpleNamespace(prompt_context=AsyncMock(side_effect=OSError("synthetic failure")))
    providers = SimpleNamespace(search=AsyncMock())
    service = ChatMediaService(store, providers, UnavailableDiagnostics())
    context = asyncio.run(service.context(None, None))
    assert context["media_allowed"] is False
    assert context["library_available"] is False
    assert context["library_sticker_count"] is None
    providers.search.assert_not_called()


def test_failed_optional_attachment_and_logging_do_not_abort_text_path():
    store = SimpleNamespace(select_for_reply=AsyncMock(side_effect=OSError("synthetic failure")))
    providers = SimpleNamespace(search=AsyncMock())
    service = ChatMediaService(store, providers, UnavailableDiagnostics())
    assert asyncio.run(service.resolve(None, None, object())) is None
    providers.search.assert_not_called()


def test_caption_failure_is_terminal_and_does_not_overwrite_description():
    store = SimpleNamespace(
        settings=AsyncMock(return_value=MediaSettings()),
        claim_caption=AsyncMock(return_value=(b"synthetic image", "image/png")),
        finish_caption=AsyncMock(),
        fail_caption=AsyncMock(),
    )
    provider = SimpleNamespace(caption=AsyncMock(side_effect=RuntimeError("private-canary")))
    service = ChatMediaService(store, provider, UnavailableDiagnostics())
    with pytest.raises(MediaError, match="^media_caption_failed$"):
        asyncio.run(service.caption("synthetic-world", "synthetic-asset"))
    provider.caption.assert_awaited_once()
    store.fail_caption.assert_awaited_once()
    store.finish_caption.assert_not_called()
